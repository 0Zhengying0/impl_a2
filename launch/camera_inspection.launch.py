"""Start the Camera node; start the RealSense ROS 2 driver separately."""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    config = Path(get_package_share_directory("erasebot_camera")) / "config" / "camera.yaml"
    return LaunchDescription([
        Node(package="erasebot_camera", executable="camera_inspection_node",
             name="erasebot_camera", output="screen", parameters=[str(config)])
    ])
