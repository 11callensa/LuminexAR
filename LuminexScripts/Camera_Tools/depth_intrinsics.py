import ArducamDepthCamera as ac

from shared import cameras


cam = ac.ArducamCamera()

ret = cam.open(ac.Connection.CSI, cameras.depth_camera_index())

if ret != 0:
    print("Failed to open camera:", ret)
    exit()


print("Camera opened")


fx = cam.getControl(ac.Control.INTRINSIC_FX)
fy = cam.getControl(ac.Control.INTRINSIC_FY)
cx = cam.getControl(ac.Control.INTRINSIC_CX)
cy = cam.getControl(ac.Control.INTRINSIC_CY)


print("Intrinsics:")
print("fx =", fx)
print("fy =", fy)
print("cx =", cx)
print("cy =", cy)


cam.close()