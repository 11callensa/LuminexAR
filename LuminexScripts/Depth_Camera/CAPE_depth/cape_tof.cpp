/*
 * cape_tof.cpp
 *
 * Live flat-surface detection for the Arducam ToF camera on a Raspberry Pi,
 * using CAPE (Proenca & Gao, IROS 2018, https://github.com/pedropro/CAPE).
 * No neural networks: CAPE fits planes to small grid cells of the depth image
 * and merges neighbouring cells with matching plane equations.
 *
 * Pipeline per frame:
 *   depth -> rotate 180 (camera is mounted upside down) -> drop low-confidence
 *   pixels -> median filter -> temporal smoothing -> CAPE -> match planes to
 *   the previous frames (stable IDs, short hold when a plane drops out)
 *   -> send planes over UDP -> (optionally) draw filled, outlined regions.
 *
 * UDP output (default 127.0.0.1:5007, same format as the old surface_visualiser.py):
 *   {"planes":[{"id":3,"centroid":[x,y,z],"normal":[nx,ny,nz],"corners_flat":[x1,y1,z1,...]}]}
 *   Coordinates are in the RGB camera's frame (ToF offset applied), in metres
 *   by default (--units mm for millimetres). x right, y down, z forward.
 *   Normals face the camera. Corners lie exactly on the fitted plane.
 *   One message is sent every frame, with an empty list when nothing is found.
 *
 * All tuning values can be changed live with the sliders in the "Controls"
 * window. Press 'c' to print the command line that reproduces them.
 *
 * Keys: q/Esc quit | c print settings | p print plane equations | s screenshot
 *
 * Run from Godot with --headless (no windows), plus any tuned settings.
 */

#include "ArducamTOFCamera.hpp"

#include <opencv2/core.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgproc.hpp>
#include <Eigen/Dense>

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "CAPE.h"

using namespace Arducam;

// ---------------------------------------------------------------------------
// Tunable settings. Every one has a command-line flag and a live slider.
// ---------------------------------------------------------------------------
struct Settings {
    int patch = 8;          // cell size in pixels. Bigger = steadier, smaller = finds smaller surfaces
    int conf = 30;          // ignore pixels whose confidence is below this
    int smooth = 6;         // temporal smoothing 0 (off) .. 9 (heavy)
    int median = 1;         // 1 = 3x3 median filter on depth, 0 = off
    int noise_mm = 20;      // how rough (mm) a cell may be and still count as flat
    int flatness = 30;      // min flatness score of a merged surface (CAPE original: 100)
    int angle_deg = 15;     // max angle between neighbouring cells to merge them
    int min_seed = 3;       // cells that must agree on a direction to start a surface (CAPE: 5)
    int bins = 12;          // direction histogram bins per axis (CAPE: 20). Fewer = more tolerant
    int hold = 4;           // keep showing a surface for this many frames after it drops out
    int confirm = 2;        // a new surface must be seen this many frames before it is shown
    int range_mm = 4000;    // camera range mode: 2000 or 4000
    int min_area_px = 150;  // don't draw outlines smaller than this (pixels)
    int scale = 0;          // display zoom, 0 = automatic
    bool headless = false;  // no window, print stats only
    bool rotate180 = true;  // camera is mounted upside down
    // UDP output
    bool udp = true;
    std::string udp_host = "127.0.0.1";
    int udp_port = 5007;
    int max_planes = 3;     // send at most this many surfaces (largest first), 0 = all
    bool units_mm = false;  // false = metres, true = millimetres
    // Camera device. Its /dev/videoN number depends on what was plugged in first, so by
    // default it is found by the name the Pi 5's CSI driver gives the camera's main
    // channel (keep in sync with depth_camera_node_name in shared/cameras.json).
    std::string camera_name = "rp1-cfe-csi2_ch0";
    int camera_index = -1;  // -1 = find by camera_name
};

// Physical offset from the ToF camera to the RGB camera used for stylus
// tracking (metres), so both data streams share one frame. The ToF sits
// 14.5 mm ABOVE the RGB camera, same horizontal position, no depth offset.
static const double CAMERA_OFFSET_TOF_TO_RGB_M[3] = {0.0, -0.0145, 0.0};

struct Slider { const char* name; int* value; int min; int max; const char* flag; };

static std::vector<Slider> sliders(Settings& S)
{
    return {
        {"Cell size px", &S.patch, 4, 20, "--patch"},
        {"Confidence", &S.conf, 0, 255, "--conf"},
        {"Smoothing 0-9", &S.smooth, 0, 9, "--smooth"},
        {"Median on/off", &S.median, 0, 1, "--median"},
        {"Noise mm", &S.noise_mm, 2, 80, "--noise"},
        {"Flatness min", &S.flatness, 5, 200, "--flatness"},
        {"Merge angle deg", &S.angle_deg, 3, 35, "--angle"},
        {"Seed cells min", &S.min_seed, 2, 10, "--min-seed"},
        {"Direction bins", &S.bins, 6, 30, "--bins"},
        {"Hold frames", &S.hold, 0, 20, "--hold"},
        {"Confirm frames", &S.confirm, 1, 10, "--confirm"},
    };
}

static std::atomic<bool> g_stop{false};
static void onSignal(int) { g_stop = true; }

static void usage(const char* prog, Settings& S)
{
    std::cout << "Usage: " << prog << " [options]\n";
    for (auto& s : sliders(S))
        std::cout << "  " << std::left << std::setw(12) << s.flag << " N   " << s.name
                  << " (" << s.min << "-" << s.max << ", default " << *s.value << ")\n";
    std::cout << "  --range N      camera range mode 2000 or 4000 (default 4000)\n"
              << "  --min-area N   smallest outline drawn, pixels (default 150)\n"
              << "  --scale N      display zoom (default automatic)\n"
              << "  --headless     no window, print stats to the terminal\n"
              << "  --no-rotate    camera is NOT mounted upside down\n"
              << "  --udp-host IP  where to send planes (default 127.0.0.1)\n"
              << "  --udp-port N   UDP port (default 5007)\n"
              << "  --no-udp       don't send planes\n"
              << "  --max-planes N send at most N surfaces, largest first (default 3, 0 = all)\n"
              << "  --units m|mm   units of sent coordinates (default m)\n"
              << "  --camera-name S  find the camera by video device name (default " << S.camera_name << ")\n"
              << "  --camera-index N open /dev/videoN directly instead of finding it by name\n";
}

// Returns the N of the lowest /dev/videoN whose driver-given name matches, or -1.
static int findVideoIndex(const std::string& name, const std::string& sysfs_dir = "/sys/class/video4linux")
{
    int best = -1;
    std::error_code ec;
    for (const auto& entry : std::filesystem::directory_iterator(sysfs_dir, ec)) {
        const std::string dev = entry.path().filename().string();
        if (dev.rfind("video", 0) != 0) continue;
        std::ifstream file(entry.path() / "name");
        std::string node_name;
        std::getline(file, node_name);
        if (node_name != name) continue;
        int index = std::atoi(dev.c_str() + 5);
        if (best == -1 || index < best) best = index;
    }
    return best;
}

static bool parseArgs(int argc, char** argv, Settings& S)
{
    auto sl = sliders(S);
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "-h" || a == "--help") { usage(argv[0], S); std::exit(0); }
        if (a == "--headless") { S.headless = true; continue; }
        if (a == "--no-rotate") { S.rotate180 = false; continue; }
        if (a == "--no-udp") { S.udp = false; continue; }
        if (i + 1 >= argc) { std::cerr << "Missing value for " << a << "\n"; return false; }
        if (a == "--udp-host") { S.udp_host = argv[++i]; continue; }
        if (a == "--camera-name") { S.camera_name = argv[++i]; continue; }
        if (a == "--units") {
            std::string u = argv[++i];
            if (u != "m" && u != "mm") { std::cerr << "--units must be m or mm\n"; return false; }
            S.units_mm = (u == "mm");
            continue;
        }
        int v = std::atoi(argv[++i]);
        bool found = false;
        for (auto& s : sl)
            if (a == s.flag) { *s.value = std::clamp(v, s.min, s.max); found = true; }
        if (a == "--range") { S.range_mm = v; found = true; }
        if (a == "--min-area") { S.min_area_px = v; found = true; }
        if (a == "--scale") { S.scale = v; found = true; }
        if (a == "--udp-port") { S.udp_port = v; found = true; }
        if (a == "--camera-index") { S.camera_index = std::max(0, v); found = true; }
        if (a == "--max-planes") { S.max_planes = std::max(0, v); found = true; }
        if (!found) { std::cerr << "Unknown option: " << a << "\n"; return false; }
    }
    return true;
}

static std::string commandLine(Settings& S)
{
    std::ostringstream o;
    o << "./build/cape_tof";
    for (auto& s : sliders(S)) o << " " << s.flag << " " << *s.value;
    if (S.range_mm != 4000) o << " --range " << S.range_mm;
    if (S.max_planes != 3) o << " --max-planes " << S.max_planes;
    return o.str();
}

// The SDK reports intrinsics multiplied by 100.
static bool readIntrinsic(ArducamTOFCamera& tof, Control c, float& out)
{
    int v = 0;
    if (tof.getControl(c, &v) != 0 || v <= 0) return false;
    out = v / 100.0f;
    return true;
}

static const cv::Vec3b kPalette[] = {
    {60, 180, 75},  {48, 130, 245}, {25, 225, 255}, {180, 30, 145}, {240, 240, 70},
    {230, 50, 240}, {60, 245, 210}, {212, 190, 250}, {128, 128, 0}, {255, 190, 220},
    {40, 110, 170}, {200, 250, 255}, {0, 0, 128},   {195, 255, 170}, {0, 128, 128},
    {75, 25, 230},
};
static const int kPaletteSize = sizeof(kPalette) / sizeof(kPalette[0]);

// ---------------------------------------------------------------------------
// Everything that depends on the cell size / merge angle. Rebuilt when those change.
// ---------------------------------------------------------------------------
struct Pipeline {
    int P = 0, W = 0, H = 0, angle = 0;
    std::vector<float> ray_x, ray_y;
    std::vector<int> cell_map;
    Eigen::MatrixXf cloud;
    std::unique_ptr<CAPE> cape;

    void build(int cam_w, int cam_h, int patch, int angle_deg,
               float fx, float fy, float cx, float cy)
    {
        P = patch;
        angle = angle_deg;
        W = (cam_w / P) * P;  // CAPE needs whole cells: crop right/bottom edge if needed
        H = (cam_h / P) * P;
        const int ncx = W / P;
        ray_x.resize(W);
        ray_y.resize(H);
        for (int c = 0; c < W; ++c) ray_x[c] = (c - cx) / fx;
        for (int r = 0; r < H; ++r) ray_y[r] = (r - cy) / fy;
        cell_map.resize(W * H);
        for (int r = 0; r < H; ++r)
            for (int c = 0; c < W; ++c)
                cell_map[r * W + c] = ((r / P) * ncx + (c / P)) * P * P + (r % P) * P + (c % P);
        cloud.resize(W * H, 3);
        float cos_a = std::cos(angle_deg * float(M_PI) / 180.0f);
        cape.reset(new CAPE(H, W, P, P, /*cylinder_detection=*/false, cos_a, /*max_merge_dist=*/50.0f));
    }
};

// ---------------------------------------------------------------------------
// Surfaces tracked across frames so each keeps its ID/colour and doesn't flicker.
// ---------------------------------------------------------------------------
struct Track {
    int id;
    Eigen::Vector3d n;   // unit normal
    double d;            // n.X + d = 0, mm (d > 0 = distance from camera)
    int first_seen, last_seen, hits;
    cv::Mat mask;        // pixels of the surface when last seen
};

int main(int argc, char** argv)
{
    Settings S;
    if (!parseArgs(argc, argv, S)) { usage(argv[0], S); return 1; }
    std::signal(SIGINT, onSignal);
    std::signal(SIGTERM, onSignal);

    // ------------------------------------------------------------------ camera
    ArducamTOFCamera tof;
    int camera_index = S.camera_index >= 0 ? S.camera_index : findVideoIndex(S.camera_name);
    if (camera_index < 0) {
        std::cerr << "No video device named " << S.camera_name << " (is the ToF camera connected?)\n";
        return 1;
    }
    std::cout << "Opening ToF camera at /dev/video" << camera_index << "\n";
    if (tof.open(Connection::CSI, camera_index)) { std::cerr << "Failed to open camera\n"; return 1; }
    if (tof.start(FrameType::DEPTH_FRAME)) { std::cerr << "Failed to start camera\n"; tof.close(); return 1; }
    tof.setControl(Control::RANGE, S.range_mm);
    int range_mm = S.range_mm;
    tof.getControl(Control::RANGE, &range_mm);

    auto info = tof.getCameraInfo();
    const int cam_w = info.width, cam_h = info.height;

    float fx, fy, cx, cy;
    if (!(readIntrinsic(tof, Control::INTRINSIC_FX, fx) && readIntrinsic(tof, Control::INTRINSIC_FY, fy) &&
          readIntrinsic(tof, Control::INTRINSIC_CX, cx) && readIntrinsic(tof, Control::INTRINSIC_CY, cy))) {
        float diag = std::sqrt(float(cam_w * cam_w + cam_h * cam_h));
        fx = fy = (diag / 2.0f) / std::tan(35.0f * float(M_PI) / 180.0f);  // ~70 deg diagonal FOV
        cx = cam_w / 2.0f;
        cy = cam_h / 2.0f;
        std::cerr << "Warning: could not read intrinsics from the camera, using an approximation.\n";
    }
    if (S.rotate180) {  // image is rotated 180 degrees before use, so the principal point moves too
        cx = (cam_w - 1) - cx;
        cy = (cam_h - 1) - cy;
    }
    std::cout << "Camera " << cam_w << "x" << cam_h << ", range " << range_mm << " mm, fx=" << fx
              << " fy=" << fy << " cx=" << cx << " cy=" << cy << "\n";

    // ------------------------------------------------------------- UDP
    int sock = -1;
    sockaddr_in dest{};
    if (S.udp) {
        sock = socket(AF_INET, SOCK_DGRAM, 0);
        dest.sin_family = AF_INET;
        dest.sin_port = htons(uint16_t(S.udp_port));
        if (sock < 0 || inet_pton(AF_INET, S.udp_host.c_str(), &dest.sin_addr) != 1) {
            std::cerr << "Failed to set up UDP output to " << S.udp_host << ":" << S.udp_port << "\n";
            tof.stop();
            tof.close();
            return 1;
        }
        std::cout << "Sending planes to " << S.udp_host << ":" << S.udp_port << " in "
                  << (S.units_mm ? "mm" : "metres") << "\n";
    }

    // ------------------------------------------------------------- state
    Pipeline pipe;
    cv::Mat depth_raw(cam_h, cam_w, CV_32F), depth_f, depth_avg(cam_h, cam_w, CV_32F, 0.0f);
    float unit_scale = 0.0f;  // 1 if the SDK gives mm, 1000 if metres (detected on first frame)

    std::vector<Track> tracks;
    int next_id = 1, frame_no = 0;
    std::vector<PlaneSeg> planes;
    std::vector<CylinderSeg> cylinders;

    const std::string win = "Planes (CAPE)", ctl = "Controls";
    if (!S.headless) {
        cv::namedWindow(win, cv::WINDOW_AUTOSIZE);
        cv::namedWindow(ctl, cv::WINDOW_NORMAL);
        cv::resizeWindow(ctl, 420, 40 * int(sliders(S).size()));
        for (auto& s : sliders(S)) {
            cv::createTrackbar(s.name, ctl, nullptr, s.max);
            cv::setTrackbarMin(s.name, ctl, s.min);
            cv::setTrackbarPos(s.name, ctl, *s.value);
        }
    }

    using clock = std::chrono::steady_clock;
    auto fps_t0 = clock::now();
    int fps_frames = 0;
    double fps = 0.0, cape_ms_avg = 0.0;

    while (!g_stop) {
        // ---- read sliders
        if (!S.headless)
            for (auto& s : sliders(S)) *s.value = std::clamp(cv::getTrackbarPos(s.name, ctl), s.min, s.max);
        DEPTH_SIGMA_MARGIN = S.noise_mm;
        PLANE_SCORE_MIN = S.flatness;
        MIN_SEED_CELLS = S.min_seed;
        HIST_BINS = S.bins;
        if (pipe.P != S.patch || pipe.angle != S.angle_deg)
            pipe.build(cam_w, cam_h, S.patch, S.angle_deg, fx, fy, cx, cy);
        const int W = pipe.W, H = pipe.H, N = W * H;

        // ---- grab a frame
        ArducamFrameBuffer* frame = tof.requestFrame(200);
        if (frame == nullptr) continue;
        FrameFormat fmt;
        frame->getFormat(FrameType::DEPTH_FRAME, fmt);
        if (fmt.width != cam_w || fmt.height != cam_h) {
            std::cerr << "Unexpected frame size " << fmt.width << "x" << fmt.height << "\n";
            tof.releaseFrame(frame);
            continue;
        }
        cv::Mat d_in(cam_h, cam_w, CV_32F, frame->getData(FrameType::DEPTH_FRAME));
        cv::Mat c_in(cam_h, cam_w, CV_32F, frame->getData(FrameType::CONFIDENCE_FRAME));

        if (unit_scale == 0.0f) {  // metres or millimetres?
            cv::Mat valid = (d_in > 0) & (c_in >= S.conf);
            if (cv::countNonZero(valid) > cam_w * cam_h / 10) {
                double m = cv::mean(d_in, valid)[0];
                unit_scale = m < 20.0 ? 1000.0f : 1.0f;
                std::cout << "Depth units: " << (unit_scale == 1.0f ? "mm" : "metres (converting to mm)") << "\n";
            } else {
                tof.releaseFrame(frame);
                continue;
            }
        }

        // ---- clean the depth: rotate, invalid -> 0, then median, then temporal smoothing
        const float zmax = float(range_mm);
        cv::Mat conf;
        d_in.convertTo(depth_raw, CV_32F, unit_scale);
        c_in.copyTo(conf);
        tof.releaseFrame(frame);
        if (S.rotate180) {
            cv::rotate(depth_raw, depth_raw, cv::ROTATE_180);
            cv::rotate(conf, conf, cv::ROTATE_180);
        }
        depth_raw.setTo(0, (conf < S.conf) | (depth_raw > zmax) | (depth_raw != depth_raw));

        if (S.median) cv::medianBlur(depth_raw, depth_f, 3);
        else depth_f = depth_raw;

        if (S.smooth > 0) {
            const float a = 1.0f - S.smooth / 10.0f;  // weight of the new frame
            const float jump = 60.0f;                 // bigger change = real motion: don't blur it
            for (int r = 0; r < cam_h; ++r) {
                float* z = depth_f.ptr<float>(r);
                float* avg = depth_avg.ptr<float>(r);
                for (int c = 0; c < cam_w; ++c) {
                    if (z[c] <= 0.0f) continue;  // invalid now: keep the average, output 0
                    if (avg[c] <= 0.0f || std::fabs(z[c] - avg[c]) > jump) avg[c] = z[c];
                    else avg[c] += a * (z[c] - avg[c]);
                    z[c] = avg[c];
                }
            }
        }

        // ---- organized point cloud in CAPE's cell order
        float* X = pipe.cloud.data();
        float* Y = X + N;
        float* Z = Y + N;
        for (int r = 0; r < H; ++r) {
            const float* z = depth_f.ptr<float>(r);
            const int* map_row = &pipe.cell_map[r * W];
            const float ry = pipe.ray_y[r];
            for (int c = 0; c < W; ++c) {
                int id = map_row[c];
                X[id] = pipe.ray_x[c] * z[c];
                Y[id] = ry * z[c];
                Z[id] = z[c];
            }
        }

        // ---- CAPE
        cv::Mat_<uchar> seg(H, W, uchar(0));
        planes.clear();
        cylinders.clear();
        int n_planes = 0, n_cyl = 0;
        auto t0 = clock::now();
        pipe.cape->process(pipe.cloud, n_planes, n_cyl, seg, planes, cylinders);
        double cape_ms = std::chrono::duration<double, std::milli>(clock::now() - t0).count();
        cape_ms_avg = cape_ms_avg == 0.0 ? cape_ms : 0.9 * cape_ms_avg + 0.1 * cape_ms;
        ++frame_no;

        // ---- match detections to tracked surfaces (greedy, best matches first)
        struct Cand { double cost; int det, trk; };
        std::vector<Cand> cands;
        for (int i = 0; i < n_planes; ++i) {
            Eigen::Vector3d n(planes[i].normal[0], planes[i].normal[1], planes[i].normal[2]);
            for (int t = 0; t < (int)tracks.size(); ++t) {
                double ang = std::acos(std::clamp(n.dot(tracks[t].n), -1.0, 1.0)) * 180.0 / M_PI;
                double dd = std::fabs(planes[i].d - tracks[t].d);
                if (ang < 12.0 && dd < 80.0) cands.push_back({ang / 12.0 + dd / 80.0, i, t});
            }
        }
        std::sort(cands.begin(), cands.end(), [](const Cand& a, const Cand& b) { return a.cost < b.cost; });
        std::vector<int> det_track(n_planes, -1);
        std::vector<bool> trk_used(tracks.size(), false);
        for (auto& c : cands) {
            if (det_track[c.det] >= 0 || trk_used[c.trk]) continue;
            det_track[c.det] = c.trk;
            trk_used[c.trk] = true;
        }
        for (int i = 0; i < n_planes; ++i) {
            Eigen::Vector3d n(planes[i].normal[0], planes[i].normal[1], planes[i].normal[2]);
            cv::Mat mask = (seg == (i + 1));
            if (det_track[i] < 0) {
                tracks.push_back({next_id++, n, planes[i].d, frame_no, frame_no, 1, mask});
            } else {
                Track& t = tracks[det_track[i]];
                t.n = (0.6 * t.n + 0.4 * n).normalized();
                t.d = 0.6 * t.d + 0.4 * planes[i].d;
                t.last_seen = frame_no;
                t.hits++;
                t.mask = mask;
            }
        }
        // forget surfaces not seen for a while (kept a little longer than 'hold' so IDs survive)
        tracks.erase(std::remove_if(tracks.begin(), tracks.end(),
                                    [&](const Track& t) { return frame_no - t.last_seen > S.hold + 15; }),
                     tracks.end());
        // tracks are drawn if confirmed and seen recently; also drop masks from an older cell size
        std::vector<const Track*> shown;
        for (auto& t : tracks)
            if (t.hits >= S.confirm && frame_no - t.last_seen <= S.hold && t.mask.size() == cv::Size(W, H))
                shown.push_back(&t);

        // ---- send surfaces over UDP
        if (S.udp) {
            const double k = S.units_mm ? 1.0 : 0.001;  // internal mm -> output units
            const double m_to_out = S.units_mm ? 1000.0 : 1.0;  // offset is in metres
            const double off[3] = {CAMERA_OFFSET_TOF_TO_RGB_M[0] * m_to_out,
                                   CAMERA_OFFSET_TOF_TO_RGB_M[1] * m_to_out,
                                   CAMERA_OFFSET_TOF_TO_RGB_M[2] * m_to_out};
            struct Out { double area; std::string json; };
            std::vector<Out> outs;
            for (auto* t : shown) {
                // largest outer outline of this surface
                std::vector<std::vector<cv::Point>> cs;
                cv::findContours(t->mask.clone(), cs, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);
                int best = -1;
                double best_area = 0;
                for (size_t k2 = 0; k2 < cs.size(); ++k2) {
                    double a = std::fabs(cv::contourArea(cs[k2]));
                    if (a > best_area) { best_area = a; best = int(k2); }
                }
                if (best < 0 || best_area < S.min_area_px) continue;

                // centroid = mean of the surface's valid 3D points (mm)
                Eigen::Vector3d sum(0, 0, 0);
                long cnt = 0;
                for (int r = 0; r < H; ++r) {
                    const uchar* m = t->mask.ptr<uchar>(r);
                    const float* z = depth_f.ptr<float>(r);
                    for (int c = 0; c < W; ++c)
                        if (m[c] && z[c] > 0.0f) {
                            sum += Eigen::Vector3d(pipe.ray_x[c] * z[c], pipe.ray_y[r] * z[c], z[c]);
                            ++cnt;
                        }
                }
                if (cnt == 0) continue;
                Eigen::Vector3d centroid = sum / double(cnt);

                // normal facing the camera
                Eigen::Vector3d n = t->n;
                double d = t->d;
                if (n.dot(centroid) > 0) { n = -n; d = -d; }

                // simplified outline; each corner projected onto the plane along its pixel ray
                std::vector<cv::Point> approx;
                cv::approxPolyDP(cs[best], approx, 0.02 * cv::arcLength(cs[best], true), true);
                std::ostringstream js;
                js << std::fixed << std::setprecision(S.units_mm ? 2 : 5);
                js << "{\"id\":" << t->id << ",\"centroid\":[" << centroid[0] * k + off[0] << ","
                   << centroid[1] * k + off[1] << "," << centroid[2] * k + off[2] << "],";
                js << std::setprecision(5) << "\"normal\":[" << n[0] << "," << n[1] << "," << n[2] << "],";
                js << std::setprecision(S.units_mm ? 2 : 5) << "\"corners_flat\":[";
                bool first = true;
                for (auto& p : approx) {
                    int u = std::clamp(p.x, 0, W - 1), v = std::clamp(p.y, 0, H - 1);
                    Eigen::Vector3d ray(pipe.ray_x[u], pipe.ray_y[v], 1.0);
                    double denom = n.dot(ray);
                    Eigen::Vector3d X;
                    if (std::fabs(denom) > 1e-6 && -d / denom > 0) X = ray * (-d / denom);
                    else X = ray * centroid[2];  // ray nearly parallel to the plane: fall back
                    if (!first) js << ",";
                    first = false;
                    js << X[0] * k + off[0] << "," << X[1] * k + off[1] << "," << X[2] * k + off[2];
                }
                js << "]}";
                outs.push_back({best_area, js.str()});
            }
            std::sort(outs.begin(), outs.end(), [](const Out& a, const Out& b) { return a.area > b.area; });
            if (S.max_planes > 0 && (int)outs.size() > S.max_planes) outs.resize(S.max_planes);
            std::string msg = "{\"planes\":[";
            for (size_t i = 0; i < outs.size(); ++i) msg += (i ? "," : "") + outs[i].json;
            msg += "]}";
            sendto(sock, msg.data(), msg.size(), 0, (sockaddr*)&dest, sizeof(dest));
        }

        // ---- stats
        ++fps_frames;
        double el = std::chrono::duration<double>(clock::now() - fps_t0).count();
        if (el >= 1.0) {
            fps = fps_frames / el;
            fps_frames = 0;
            fps_t0 = clock::now();
            if (S.headless)
                std::cout << std::fixed << std::setprecision(1) << "fps " << fps << " | CAPE " << cape_ms_avg
                          << " ms | detected " << n_planes << " | shown " << shown.size() << "\n";
        }
        if (S.headless) continue;

        // ---- draw: depth in grey (near = bright), surfaces filled and outlined
        cv::Mat grey, bg;
        depth_f(cv::Rect(0, 0, W, H)).convertTo(grey, CV_8U, -200.0 / zmax, 230.0);
        grey.setTo(0, depth_f(cv::Rect(0, 0, W, H)) == 0);
        cv::cvtColor(grey, bg, cv::COLOR_GRAY2BGR);
        cv::Mat fill = bg.clone();
        for (auto* t : shown) {
            cv::Vec3b col = kPalette[t->id % kPaletteSize];
            fill.setTo(cv::Scalar(col[0], col[1], col[2]), t->mask);
        }
        cv::addWeighted(fill, 0.55, bg, 0.45, 0.0, bg);

        int scale = S.scale > 0 ? S.scale : std::max(1, 720 / W);
        cv::Mat view;
        cv::resize(bg, view, cv::Size(W * scale, H * scale), 0, 0, cv::INTER_NEAREST);

        for (auto* t : shown) {
            cv::Vec3b col = kPalette[t->id % kPaletteSize];
            std::vector<std::vector<cv::Point>> cs;
            std::vector<cv::Vec4i> hier;
            cv::findContours(t->mask.clone(), cs, hier, cv::RETR_CCOMP, cv::CHAIN_APPROX_SIMPLE);
            double best_area = 0;
            cv::Point label_at(-1, -1);
            for (size_t k = 0; k < cs.size(); ++k) {
                bool is_hole = hier[k][3] >= 0;
                double area = std::fabs(cv::contourArea(cs[k]));
                if (area < (is_hole ? S.min_area_px / 2 : S.min_area_px)) continue;
                std::vector<cv::Point> sc;
                for (auto& p : cs[k]) sc.emplace_back(p.x * scale + scale / 2, p.y * scale + scale / 2);
                std::vector<std::vector<cv::Point>> one{sc};
                cv::polylines(view, one, true, cv::Scalar(0, 0, 0), 4, cv::LINE_AA);
                cv::polylines(view, one, true, cv::Scalar(col[0], col[1], col[2]), 2, cv::LINE_AA);
                if (!is_hole && area > best_area) {
                    cv::Moments m = cv::moments(cs[k]);
                    if (m.m00 > 0) {
                        best_area = area;
                        label_at = cv::Point(int(m.m10 / m.m00 * scale), int(m.m01 / m.m00 * scale));
                    }
                }
            }
            if (label_at.x >= 0) {
                std::ostringstream txt;
                txt << "P" << t->id << " " << std::fixed << std::setprecision(2) << t->d / 1000.0 << "m";
                int base = 0;
                cv::Size ts = cv::getTextSize(txt.str(), cv::FONT_HERSHEY_SIMPLEX, 0.5, 3, &base);
                label_at.x = std::clamp(label_at.x - ts.width / 2, 4, std::max(4, view.cols - ts.width - 4));
                label_at.y = std::clamp(label_at.y, 24 + ts.height + 4, std::max(24 + ts.height + 4, view.rows - 6));
                cv::putText(view, txt.str(), label_at, cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 0, 0), 3, cv::LINE_AA);
                cv::putText(view, txt.str(), label_at, cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(255, 255, 255), 1, cv::LINE_AA);
            }
        }

        std::ostringstream st;
        st << std::fixed << std::setprecision(1) << fps << " fps | CAPE " << cape_ms_avg
           << " ms | detected " << n_planes << " | shown " << shown.size();
        cv::rectangle(view, cv::Point(0, 0), cv::Point(view.cols, 24), cv::Scalar(0, 0, 0), -1);
        cv::putText(view, st.str(), cv::Point(8, 17), cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(255, 255, 255), 1, cv::LINE_AA);
        cv::imshow(win, view);

        int key = cv::waitKey(1) & 0xFF;
        if (key == 'q' || key == 27) break;
        if (key == 'c') std::cout << commandLine(S) << "\n";
        if (key == 's') {
            auto t = std::chrono::duration_cast<std::chrono::seconds>(
                         std::chrono::system_clock::now().time_since_epoch()).count();
            std::string fn = "planes_" + std::to_string(t) + ".png";
            cv::imwrite(fn, view);
            std::cout << "Saved " << fn << "\n";
        }
        if (key == 'p') {
            std::cout << shown.size() << " surfaces (n.X + d = 0, mm):\n";
            for (auto* t : shown)
                std::cout << "  P" << t->id << " n=(" << std::setprecision(3) << t->n[0] << ", " << t->n[1]
                          << ", " << t->n[2] << ") d=" << std::setprecision(1) << std::fixed << t->d << "\n";
        }
    }

    std::cout << "Settings used:\n  " << commandLine(S) << "\n";
    tof.stop();
    tof.close();
    if (sock >= 0) close(sock);
    if (!S.headless) cv::destroyAllWindows();
    return 0;
}
