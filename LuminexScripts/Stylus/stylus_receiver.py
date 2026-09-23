import asyncio
import signal
from bleak import BleakScanner, BleakClient
import socket

SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab"
CHARACTERISTIC_UUID = "87654321-4321-4321-4321-ba0987654321"

UDP_IP = "127.0.0.1"
UDP_PORT = 5005

udp_socket = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM
)

stylus_state = {
    "w": 1.0,
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,

    "wheel": 0,
    "wheel_click": False,
    "mode_button": False,

    "sys_cal": 0,
    "gyro_cal": 0,
    "accel_cal": 0,
    "mag_cal": 0
}


async def notification_handler(sender, data):
    try:
        message = data.decode()

        parts = message.split(";")

        quaternion = (parts[0].replace("Q:", "").split(","))

        stylus_state["w"] = float(quaternion[0])
        stylus_state["x"] = float(quaternion[1])
        stylus_state["y"] = float(quaternion[2])
        stylus_state["z"] = float(quaternion[3])

        stylus_state["wheel"] = int(parts[1].replace("W:", ""))
        stylus_state["wheel_click"] = bool(int(parts[2].replace("WC:", "")))
        stylus_state["mode_button"] = bool(int(parts[3].replace("MB:", "")))

        cal_parts = parts[4].replace("CAL:", "").split(",")
        stylus_state["sys_cal"] = int(cal_parts[0])
        stylus_state["gyro_cal"] = int(cal_parts[1])
        stylus_state["accel_cal"] = int(cal_parts[2])
        stylus_state["mag_cal"] = int(cal_parts[3])

        packet = (
            "STATE;"
            f"{stylus_state['w']},"
            f"{stylus_state['x']},"
            f"{stylus_state['y']},"
            f"{stylus_state['z']};"
            f"{stylus_state['wheel']};"
            f"{int(stylus_state['wheel_click'])};"
            f"{int(stylus_state['mode_button'])};"
            f"{stylus_state['sys_cal']},"
            f"{stylus_state['gyro_cal']},"
            f"{stylus_state['accel_cal']},"
            f"{stylus_state['mag_cal']}"
        )

        udp_socket.sendto(
            packet.encode(),
            (UDP_IP, UDP_PORT)
        )

    except Exception as e:
        print("Packet error:")
        print(data)
        print(e)


def disconnected(client):
    print("Stylus disconnected")

    udp_socket.sendto(
        b"DISCONNECTED",
        (UDP_IP, UDP_PORT)
    )


async def main():
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def request_shutdown():
        print("Shutdown signal received, disconnecting cleanly...")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, request_shutdown)

    print("Scanning...")

    devices = await BleakScanner.discover()
    target = None

    for device in devices:

        print(device.name, device.address)

        if device.name == "SpatialStylus":
            target = device

    if target is None:
        print("Couldn't find stylus.")
        return

    print("Connecting...")

    async with BleakClient(target.address, disconnected_callback=disconnected) as client:
        print("Connected!")

        udp_socket.sendto(
            b"CONNECTED",
            (UDP_IP, UDP_PORT)
        )

        await client.start_notify(CHARACTERISTIC_UUID, notification_handler)

        print("Receiving data...")

        await shutdown_event.wait()

        await client.stop_notify(CHARACTERISTIC_UUID)

    print("Disconnected cleanly.")


asyncio.run(main())