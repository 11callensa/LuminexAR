/*
 * head_tracker.c
 *
 * Streams the XREAL Air glasses' head orientation over UDP, using the
 * nrealAirLinuxDriver interface library (git submodule).
 *
 * One JSON message is sent per IMU update:
 *   {"type":"HEAD_ORIENTATION","orientation":[w,x,y,z]}
 *
 * Usage:
 *   xrealAirHeadTracker [host] [port]       (defaults: 127.0.0.1 5008)
 *
 * Stops cleanly on Ctrl+C / SIGTERM.
 */

#include "device_imu.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#define DEFAULT_HOST "127.0.0.1"
#define DEFAULT_PORT 5008

static volatile sig_atomic_t running = 1;
static int sock = -1;
static struct sockaddr_in dest;

static void handle_signal(int sig)
{
	(void)sig;
	running = 0;
}

static void on_imu_event(uint64_t timestamp,
                         device_imu_event_type event,
                         const device_imu_ahrs_type* ahrs)
{
	(void)timestamp;

	switch (event) {
		case DEVICE_IMU_EVENT_INIT:
			puts("IMU Initialized");
			fflush(stdout);
			break;
		case DEVICE_IMU_EVENT_UPDATE: {
			device_imu_quat_type q = device_imu_get_orientation(ahrs);
			char msg[128];
			int len = snprintf(msg, sizeof(msg),
			                   "{\"type\":\"HEAD_ORIENTATION\",\"orientation\":[%.6f,%.6f,%.6f,%.6f]}",
			                   q.w, q.x, q.y, q.z);
			if (len > 0)
				sendto(sock, msg, (size_t)len, 0, (struct sockaddr*)&dest, sizeof(dest));
			break;
		}
		default:
			break;
	}
}

int main(int argc, char** argv)
{
	const char* host = (argc > 1) ? argv[1] : DEFAULT_HOST;
	int port = (argc > 2) ? atoi(argv[2]) : DEFAULT_PORT;

	signal(SIGINT, handle_signal);
	signal(SIGTERM, handle_signal);

	sock = socket(AF_INET, SOCK_DGRAM, 0);
	if (sock < 0) {
		puts("Failed to create UDP socket");
		return 1;
	}

	memset(&dest, 0, sizeof(dest));
	dest.sin_family = AF_INET;
	dest.sin_port = htons((uint16_t)port);
	if (inet_pton(AF_INET, host, &dest.sin_addr) != 1) {
		printf("Invalid host address: %s\n", host);
		close(sock);
		return 1;
	}

	device_imu_type dev;
	if (device_imu_open(&dev, on_imu_event) != DEVICE_IMU_ERROR_NO_ERROR) {
		puts("Failed to open IMU device");
		close(sock);
		return 1;
	}

	device_imu_clear(&dev);
	printf("Streaming head orientation to %s:%d\n", host, port);
	fflush(stdout);

	while (running && device_imu_read(&dev, 100) == DEVICE_IMU_ERROR_NO_ERROR)
		;

	puts("Shutting down cleanly...");
	device_imu_close(&dev);
	close(sock);
	return 0;
}