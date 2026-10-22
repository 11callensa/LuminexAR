/*
 * display_mode.c
 *
 * Switches the XREAL Air glasses between 2D and side-by-side stereo (3D),
 * the same switch as holding the volume-up button. The glasses come up in 2D
 * every time they wake, so the launcher runs this before starting the app.
 *
 * Usage:
 *   xrealAirDisplayMode [3d|2d]       (default: 3d = 3840x1080 60 Hz SBS)
 *
 * Exits 0 once the glasses are in the requested mode (or already were).
 */

#include "device_mcu.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char** argv)
{
	const char* requested = (argc > 1) ? argv[1] : "3d";
	uint8_t target;
	if (strcmp(requested, "3d") == 0) {
		target = DEVICE_MCU_DISPLAY_MODE_3840x1080_60_SBS;
	} else if (strcmp(requested, "2d") == 0) {
		target = DEVICE_MCU_DISPLAY_MODE_1920x1080_60;
	} else {
		printf("Usage: %s [3d|2d]\n", argv[0]);
		return 2;
	}

	device_mcu_type dev;
	if (device_mcu_open(&dev, NULL) != DEVICE_MCU_ERROR_NO_ERROR) {
		puts("Failed to open the glasses' control device (are they plugged in and awake?)");
		return 1;
	}

	// device_mcu_open reads the current mode, so only switch when it differs.
	int result = 0;
	if (dev.disp_mode == target) {
		printf("Glasses already in %s mode\n", requested);
	} else {
		dev.disp_mode = target;
		if (device_mcu_update_display_mode(&dev) == DEVICE_MCU_ERROR_NO_ERROR) {
			printf("Switched glasses to %s mode\n", requested);
		} else {
			puts("Failed to switch display mode");
			result = 1;
		}
	}

	device_mcu_close(&dev);
	return result;
}
