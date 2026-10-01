extends Control
@export var sys_bar: Control
@export var gyro_bar: Control
@export var accel_bar: Control
@export var mag_bar: Control

var gyro_level := 0
var accel_level := 0
var mag_level := 0

func update_status(sys: int, gyro: int, accel: int, mag: int):
	gyro_level = gyro
	accel_level = accel
	mag_level = mag

	sys_bar.set_level(sys)
	gyro_bar.set_level(gyro)
	accel_bar.set_level(accel)
	mag_bar.set_level(mag)

func is_fully_calibrated() -> bool:
	return gyro_level == 3 and accel_level == 3 and mag_level == 3
