cmake_minimum_required(VERSION 3.10)
project(cape_tof CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
# -march=native lets GCC use the Pi 5's Cortex-A76 instructions (NEON etc.)
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native -DNDEBUG")
add_compile_options(-Wno-psabi)

# ---------------------------------------------------------------------------
# CAPE sources (git submodule, left untouched)
# ---------------------------------------------------------------------------
# Default: look for a CAPE folder in this folder's parents, so the program can
# live anywhere inside the repo.
set(_default_cape "")
set(_dir "${CMAKE_CURRENT_SOURCE_DIR}")
foreach(_i RANGE 6)
  if(EXISTS "${_dir}/CAPE/CAPE/CAPE.cpp")
    set(_default_cape "${_dir}/CAPE/CAPE")
    break()
  endif()
  get_filename_component(_dir "${_dir}" DIRECTORY)
endforeach()
set(CAPE_DIR "${_default_cape}" CACHE PATH "Path to the CAPE/CAPE source folder")
message(STATUS "Using CAPE from: ${CAPE_DIR}")
if(NOT EXISTS "${CAPE_DIR}/CAPE.cpp")
  message(FATAL_ERROR
    "CAPE sources not found in ${CAPE_DIR}.\n"
    "Run: git submodule update --init   (from the top of your repo)\n"
    "or pass -DCAPE_DIR=/path/to/CAPE/CAPE")
endif()

# CAPE hard-codes a few thresholds tuned for a Kinect. A patched copy of its
# sources is written into the build folder so they can be changed while the
# program runs. The submodule itself is never modified.
set(_patched "${CMAKE_CURRENT_BINARY_DIR}/cape_patched")
set(_cape_files CAPE.cpp CAPE.h PlaneSeg.cpp PlaneSeg.h CylinderSeg.cpp CylinderSeg.h
                Histogram.cpp Histogram.h Params.h)

function(cape_patch text_var from to file)
  string(FIND "${${text_var}}" "${from}" _pos)
  if(_pos EQUAL -1)
    message(FATAL_ERROR "Could not patch ${file}: '${from}' not found. Has the CAPE submodule changed?")
  endif()
  string(REPLACE "${from}" "${to}" _new "${${text_var}}")
  set(${text_var} "${_new}" PARENT_SCOPE)
endfunction()

foreach(f ${_cape_files})
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CAPE_DIR}/${f}")
  file(READ "${CAPE_DIR}/${f}" txt)
  if(f STREQUAL "Params.h")
    # Make the noise model adjustable and add the other tunables.
    cape_patch(txt "const double DEPTH_SIGMA_COEFF" "inline double DEPTH_SIGMA_COEFF" ${f})
    cape_patch(txt "const double DEPTH_SIGMA_MARGIN" "inline double DEPTH_SIGMA_MARGIN" ${f})
    string(APPEND txt
      "\n// Added by cape_tof (adjustable at run time)\n"
      "inline double PLANE_SCORE_MIN = 100;  // min flatness of a merged plane\n"
      "inline int    HIST_BINS       = 20;   // normal-direction histogram bins per axis\n"
      "inline int    MIN_SEED_CELLS  = 5;    // cells sharing a direction needed to start a plane\n")
  elseif(f STREQUAL "CAPE.cpp")
    # Accept any number here, in case the file was edited by hand before.
    string(REGEX MATCH "new_ps\\.score *> *[0-9.]+" _m "${txt}")
    if(NOT _m)
      message(FATAL_ERROR "Could not patch CAPE.cpp: plane score check not found. Has the CAPE submodule changed?")
    endif()
    string(REGEX REPLACE "new_ps\\.score *> *[0-9.]+" "new_ps.score>PLANE_SCORE_MIN" txt "${txt}")
    cape_patch(txt "Histogram H(20);" "Histogram H(HIST_BINS);" ${f})
    cape_patch(txt "seed_candidates.size()<5" "(int)seed_candidates.size()<MIN_SEED_CELLS" ${f})
  endif()
  file(WRITE "${_patched}/${f}.tmp" "${txt}")
  configure_file("${_patched}/${f}.tmp" "${_patched}/${f}" COPYONLY)  # only rewrites if changed
endforeach()

# ---------------------------------------------------------------------------
find_package(OpenCV REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(ArducamDepthCamera REQUIRED)

add_executable(cape_tof
  cape_tof.cpp
  ${_patched}/CAPE.cpp
  ${_patched}/PlaneSeg.cpp
  ${_patched}/CylinderSeg.cpp
  ${_patched}/Histogram.cpp
)

target_include_directories(cape_tof PRIVATE ${_patched} ${OpenCV_INCLUDE_DIRS} ${EIGEN3_INCLUDE_DIR})
target_link_libraries(cape_tof PRIVATE ${OpenCV_LIBS} ArducamDepthCamera::ArducamDepthCamera)