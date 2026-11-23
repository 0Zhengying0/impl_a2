"""ROS 2 Humble bridge for fixed-pose RealSense whiteboard inspection.

The RealSense ROS 2 driver publishes the image. The separate Franka
controller owns all robot motion; this node never controls pylibfranka.
"""
import json
from pathlib import Path

import cv2
from cv_bridge import CvBridge, CvBridgeError
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .frame_buffer import FrameBuffer
from .service import CameraInspector
from .detection import make_overlay


class CameraInspectionNode(Node):
    """Subscribe to RGB and offer fresh snapshot + inspect services."""

    def __init__(self) -> None:
        super().__init__("erasebot_camera")
        self.declare_parameter("image_topic", "/camera/camera/color/image_raw")
        self.declare_parameter("output_dir", str(Path.home() / "erasebot_camera_output"))
        self.declare_parameter("snapshot_timeout_sec", 3.0)
        self.declare_parameter("roi", [-1, -1, -1, -1])
        self.declare_parameter("expected_mask_path", "")

        self._bridge = CvBridge()
        self._frames = FrameBuffer()
        self._images = {}
        self._inspector = CameraInspector()
        self._callbacks = ReentrantCallbackGroup()
        topic = self.get_parameter("image_topic").value
        self._subscription = self.create_subscription(
            Image, topic, self._on_image, qos_profile_sensor_data,
            callback_group=self._callbacks)
        self._result_pub = self.create_publisher(String, "~/result_json", 10)
        self._services = [
            self.create_service(Trigger, f"~/capture_{stage}",
                                self._capture_callback(stage), callback_group=self._callbacks)
            for stage in ("empty", "drawn", "erased")
        ]
        self._services.append(self.create_service(
            Trigger, "~/inspect", self._on_inspect, callback_group=self._callbacks))
        self.get_logger().info(f"Subscribed to RGB topic: {topic}")

    def _on_image(self, message: Image) -> None:
        try:
            bgr = self._bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            self._frames.push(bgr)
        except (CvBridgeError, ValueError) as error:
            self.get_logger().error(f"RGB frame conversion failed: {error}")

    def _output_dir(self) -> Path:
        path = Path(self.get_parameter("output_dir").value).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _capture_callback(self, stage: str):
        def capture(_request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
            try:
                timeout = float(self.get_parameter("snapshot_timeout_sec").value)
                image = self._frames.wait_for_next(timeout)
                destination = self._output_dir() / f"{stage}.png"
                if not cv2.imwrite(str(destination), image):
                    raise OSError(f"Cannot write image: {destination}")
                self._images[stage] = image
                response.success = True
                response.message = str(destination)
                self.get_logger().info(f"Captured {stage}: {destination}")
            except (TimeoutError, OSError, ValueError) as error:
                response.success = False
                response.message = str(error)
                self.get_logger().warning(f"Capture failed ({stage}): {error}")
            return response
        return capture

    def _roi(self):
        roi = list(self.get_parameter("roi").value)
        if roi == [-1, -1, -1, -1]:
            return None
        if len(roi) != 4:
            raise ValueError("roi must contain 4 pixel coordinates")
        return tuple(int(value) for value in roi)

    def _prior(self):
        path = self.get_parameter("expected_mask_path").value
        if not path:
            return None
        prior = cv2.imread(str(Path(path).expanduser()), cv2.IMREAD_GRAYSCALE)
        if prior is None:
            raise FileNotFoundError(f"Cannot load expected mask: {path}")
        return prior

    def _on_inspect(self, _request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        try:
            missing = [s for s in ("empty", "drawn", "erased") if s not in self._images]
            if missing:
                raise ValueError("Missing snapshots: " + ", ".join(missing))
            result = self._inspector.inspect(
                self._images["empty"], self._images["drawn"], self._images["erased"],
                roi=self._roi(), expected_mask=self._prior())
            output = self._output_dir()
            payload = result.to_dict()
            (output / "result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            if result.residual_mask is not None:
                if not cv2.imwrite(str(output / "residual_mask.png"), result.residual_mask):
                    raise OSError("Cannot write residual mask")
            overlay = make_overlay(self._images["erased"], result)
            if not cv2.imwrite(str(output / "overlay.png"), overlay):
                raise OSError("Cannot write overlay")
            message = json.dumps(payload)
            self._result_pub.publish(String(data=message))
            response.success = result.status in ("CLEAN", "RESIDUAL")
            response.message = message
            self.get_logger().info(f"Inspection result: {result.status}")
        except (OSError, ValueError, cv2.error) as error:
            response.success = False
            response.message = json.dumps({"status": "ERROR", "reason": str(error)})
            self.get_logger().error(f"Inspection failed: {error}")
        return response


def main(args=None):
    rclpy.init(args=args)
    node = CameraInspectionNode()
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
