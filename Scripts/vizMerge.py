#!/usr/bin/env python3

import argparse
from PIL import Image
from pathlib import Path


def parse_layer(arg, default_opacity):
    if ":" in arg:
        path, opacity = arg.rsplit(":", 1)
        opacity = int(opacity)
    else:
        path = arg
        opacity = default_opacity

    if not (0 <= opacity <= 100):
        raise ValueError(f"Opacity must be 0–100 (got {opacity})")

    return path, opacity / 100.0


def main():
    parser = argparse.ArgumentParser(
        description="Merge PNG layers onto a background image"
    )
    parser.add_argument("--background", required=True, help="Background image")
    parser.add_argument("--output", required=True, help="Output image")
    parser.add_argument(
        "--default-opacity",
        type=int,
        default=50,
        help="Default opacity in percent (0–100), used if not specified per layer"
    )
    parser.add_argument(
        "layers",
        nargs="+",
        help="layer.png[:opacity]"
    )

    args = parser.parse_args()

    if not (0 <= args.default_opacity <= 100):
        parser.error("--default-opacity must be between 0 and 100")

    background = Image.open(args.background).convert("RGBA")
    max_dim = 1000  # downscale constant
    ratio = min(max_dim / background.width, max_dim / background.height, 1)
    new_size = (int(background.width * ratio), int(background.height * ratio))
    background = background.resize(new_size, Image.LANCZOS)
    #background = background.convert("L")  # grayscale
        


    for layer_arg in args.layers:
        try:
            path, opacity = parse_layer(layer_arg, args.default_opacity)
        except ValueError as e:
            print(f"Warning: {e}")
            continue

        if not Path(path).exists():
            print(f"Warning: layer not found, skipping: {path}")
            continue

        overlay = Image.open(path).convert("RGBA")

        if opacity < 1.0:
            alpha = overlay.getchannel("A")
            alpha = alpha.point(lambda p: int(p * opacity))
            overlay.putalpha(alpha)

        background.paste(overlay, (0, 0), overlay)

    # JPG output handling
    if args.output.lower().endswith(".jpg"):
        background = background.convert("RGB")

    background.save(args.output)


if __name__ == "__main__":
    main()