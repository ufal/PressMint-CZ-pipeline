import argparse

from pathlib import Path
from ultralytics import YOLO
import json



# --------------------
# PARAMETERS
# --------------------

IMAGE_EXTENSIONS = {".jpg", ".png", ".tif", ".tiff"}

# --------------------
# ARGPARSE
# --------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description=""
    )

    parser.add_argument(
        "-m", "--model",
        required=True,
        type=Path,
        help="Yolo model for region detection and annotation"
    )

    parser.add_argument(
        "-i", "--images",
        required=True,
        type=Path,
        help="Directory containing page images"
    )

    parser.add_argument(
        "-o", "--output",
        required=True,
        type=Path,
        help="Output PDF file"
    )

    parser.add_argument(
        "-d", "--device",
        choices=["cpu", "gpu"],
        default="cpu",
        type=str,
        help="Device to use (default: cpu)"
    )

    parser.add_argument(
        "-u", "--uuidpath",
        default="",
        type=str,
        help="Original dosument uuid_path"
    )
    return parser.parse_args()


def yoloResult2listOfRegions(yolo_result):
    boxes = yolo_result.__dict__['boxes'].xyxy
    classes = yolo_result.__dict__['boxes'].cls
    scores = yolo_result.__dict__['boxes'].conf
    return [
             {
               "bbox_xyxy": box.tolist(),
               "confidence": float(score),
               "class_id": int(cls),
               "class_name": yolo_result.__dict__['names'][int(cls)]
             }
             for box, cls, score in zip(boxes, classes, scores)
    ]

# --------------------
# MAIN
# --------------------
def main():
    args = parse_args()
    model = YOLO(args.model)
    

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    
    with open(args.output, "w", encoding="utf-8") as f:
      for img_path in sorted(args.images.glob("*.jpg")):
        results = model(str(img_path))
        regions = yoloResult2listOfRegions(results[0])
        for region in regions:
          record = {
                    "image": 
                      {
                        "uuid-path": f"{args.uuidpath}/{img_path.stem}",
                        "uuid": img_path.stem,
                        "height": results[0].orig_shape[0],
                        "width": results[0].orig_shape[1],
                      },
                    **region
                }
          f.write(json.dumps(record, ensure_ascii=False) + "\n")

# --------------------
# ENTRY POINT
# --------------------
if __name__ == "__main__":
    main()
