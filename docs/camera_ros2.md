# ROS 2 Humble Camera integration

**Architecture:** RealSense D435 ROS 2 driver -> color sensor_msgs/Image topic -> erasebot_camera (cv_bridge/OpenCV) -> Trigger services and JSON status topic. The FR3 controller remains a separate pylibfranka component; Camera never moves the robot.

## Install on Ubuntu 22.04 / ROS 2 Humble

Use the system Python provided by ROS 2, not a separate Conda NumPy environment.

```bash
sudo apt update
sudo apt install ros-humble-realsense2-camera ros-humble-cv-bridge ros-humble-rclpy ros-humble-sensor-msgs ros-humble-std-msgs ros-humble-std-srvs python3-opencv python3-numpy python3-colcon-common-extensions
source /opt/ros/humble/setup.bash
mkdir -p ~/erasebot_ws/src
cd ~/erasebot_ws/src
git clone https://github.com/0Zhengying0/impl_a2.git
cd impl_a2
git checkout feature/camera-ros2  # until PR is merged
cd ~/erasebot_ws
colcon build --symlink-install --packages-select erasebot_camera
source install/setup.bash
```

If already cloned, link or move the repository into the workspace's src folder. Replace the maintainer email placeholder in package.xml and setup.py during team integration.

## Run in three terminals

**1. Start the RealSense ROS 2 driver:**

```bash
source /opt/ros/humble/setup.bash
ros2 launch realsense2_camera rs_launch.py enable_color:=true enable_depth:=false
ros2 topic list | grep color/image_raw
```

The color topic often appears as /camera/camera/color/image_raw, but some configurations use /camera/color/image_raw. Check with ros2 topic list. Edit config/camera.yaml and rebuild/relaunch if the topic differs.

**2. Run inspection node:**

```bash
source /opt/ros/humble/setup.bash
source ~/erasebot_ws/install/setup.bash
ros2 launch erasebot_camera camera_inspection.launch.py
```

**3. Call the services after the controller confirms the fixed Inspection Pose and stopped motion:**

```bash
source /opt/ros/humble/setup.bash
source ~/erasebot_ws/install/setup.bash
ros2 service call /erasebot_camera/capture_empty std_srvs/srv/Trigger '{}'
# Draw, then return to inspection pose
ros2 service call /erasebot_camera/capture_drawn std_srvs/srv/Trigger '{}'
# Erase, then return to inspection pose
ros2 service call /erasebot_camera/capture_erased std_srvs/srv/Trigger '{}'
ros2 service call /erasebot_camera/inspect std_srvs/srv/Trigger '{}'
ros2 topic echo /erasebot_camera/result_json
```

## Interfaces

| Endpoint | Type | Description |
|---|---|---|
| image_topic (configurable) | sensor_msgs/msg/Image | RGB image input |
| /erasebot_camera/capture_empty | std_srvs/srv/Trigger | Capture empty image |
| /erasebot_camera/capture_drawn | std_srvs/srv/Trigger | Capture pre-erasure image |
| /erasebot_camera/capture_erased | std_srvs/srv/Trigger | Capture post-erasure image |
| /erasebot_camera/inspect | std_srvs/srv/Trigger | Analyze and return JSON in message |
| /erasebot_camera/result_json | std_msgs/msg/String | Publish the same JSON for Web UI |

Capture services wait for a **new frame after the request**, using MultiThreadedExecutor. The controller must still ensure the arm is stopped before calling. In the inspect response, success=true means a conclusive inspection was performed, including both CLEAN and RESIDUAL. Read JSON status to decide whether erasure is complete. UNCERTAIN/ERROR return success=false.

Images and result.json / overlay.png / residual_mask.png (if available) are saved in ~/erasebot_camera_output.

To set an optional ROI (image pixel coordinates, not robot coordinates):

```bash
ros2 param set /erasebot_camera roi '[100,80,540,400]'
ros2 param set /erasebot_camera roi '[-1,-1,-1,-1]'  # reset to full image
```

The optional expected_mask_path ROS parameter accepts a PNG generated from DrawBot strokes after applying a verified board-to-pixel homography. It is not required for Basic.

## Validation and boundaries

Offline: python3 -m pytest -q tests/test_frame_buffer.py tests/test_camera_detection.py

The OpenCV detector is unchanged; no YOLO or SAM is needed. A true ROS 2/D435 runtime and FR3 test must be performed on the lab computer. The code does not perform hand-eye calibration or image registration. Do not run direct pyrealsense2 access simultaneously with the RealSense ROS 2 driver.
