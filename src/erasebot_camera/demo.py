"""Offline demo: python -m erasebot_camera.demo --synthetic or --empty ..."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from .service import CameraInspector


def create_synthetic_example(folder: Path) -> tuple[Path, Path, Path]:
    """Generate reproducible fake whiteboard shots for smoke-testing only."""
    folder.mkdir(parents=True, exist_ok=True)
    baseline = np.full((300, 450, 3), 245, dtype=np.uint8)
    drawn = baseline.copy()
    cv2.putText(drawn, "IMPL", (40, 175), cv2.FONT_HERSHEY_SIMPLEX,
                2.7, (25, 25, 25), 6, cv2.LINE_AA)
    erased = baseline.copy()
    erased[:, 145:220] = (0.35 * drawn[:, 145:220] + 0.65 * baseline[:, 145:220]).astype(np.uint8)
    paths = tuple(folder / f"{name}.png" for name in ("empty", "drawn", "erased"))
    for path, image in zip(paths, (baseline, drawn, erased)):
        cv2.imwrite(str(path), image)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline whiteboard erasure inspection")
    parser.add_argument("--empty", type=Path)
    parser.add_argument("--drawn", type=Path)
    parser.add_argument("--erased", type=Path)
    parser.add_argument("--roi", type=int, nargs=4, metavar=("X1", "Y1", "X2", "Y2"))
    parser.add_argument("--expected-mask", type=Path)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("camera_output"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.synthetic:
        empty, drawn, erased = create_synthetic_example(args.out)
    else:
        if any(p is None for p in (args.empty, args.drawn, args.erased)):
            parser.error("Provide --empty, --drawn and --erased, or use --synthetic")
        empty, drawn, erased = args.empty, args.drawn, args.erased
    result = CameraInspector().inspect_files(
        empty, drawn, erased, roi=args.roi,
        expected_mask_path=args.expected_mask,
        overlay_path=args.out / "overlay.png",
    )
    (args.out / "result.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    if result.residual_mask is not None:
        cv2.imwrite(str(args.out / "residual_mask.png"), result.residual_mask)
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
