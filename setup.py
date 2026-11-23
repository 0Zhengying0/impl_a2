"""Setuptools package for ROS 2 Humble ament_python build."""
from glob import glob
from os.path import join
from setuptools import setup

package_name = "erasebot_camera"

setup(
    name=package_name,
    version="0.2.0",
    package_dir={"": "src"},
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="EraseBot Team",
    maintainer_email="change-me@example.com",
    description="RealSense D435 ROS 2 image capture and OpenCV erasure inspection.",
    license="Proprietary",
    entry_points={"console_scripts": [
        "camera_inspection_node = erasebot_camera.ros2_node:main"
    ]},
)
