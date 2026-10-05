#!/usr/bin/env python3
"""
remove_black_bg.py
------------------
Remove black (or near-black) backgrounds from PNG app icons and ICO favicons,
replacing them with full transparency.

Supports:
  - .png  — standard app icons
  - .ico  — favicons (all embedded size frames are processed)

Usage:
    # Single file (PNG or ICO)
    python remove_black_bg.py favicon.ico

    # Multiple files
    python remove_black_bg.py icon.png favicon.ico

    # Entire folder (processes both .png and .ico)
    python remove_black_bg.py --folder ./icons

    # Save to a separate output folder instead of overwriting
    python remove_black_bg.py --folder ./icons --output ./icons_fixed

    # Tune sensitivity (0–255, default=30)
    python remove_black_bg.py favicon.ico --threshold 50
"""

import argparse
import sys
from pathlib import Path
from PIL import Image
import numpy as np


def remove_black_background(img: Image.Image, threshold: int = 30) -> Image.Image:
    """
    Replace pixels that are 'close enough' to black with full transparency.

    How it works:
      1. Convert image to RGBA so we have an alpha channel to write to.
      2. Build a boolean mask: pixels where R, G, and B are ALL below
         `threshold` are considered 'black'.
      3. Set those pixels' alpha to 0 (transparent).

    threshold: 0 = only pure black (#000000); 255 = everything becomes transparent.
               30 is a safe default for app icons with solid black backgrounds.
    """
    rgba = img.convert("RGBA")
    data = np.array(rgba, dtype=np.uint8)   # shape: (H, W, 4)

    r, g, b = data[:, :, 0], data[:, :, 1], data[:, :, 2]

    # Mask: every channel must be <= threshold (near-black)
    black_mask = (r <= threshold) & (g <= threshold) & (b <= threshold)

    # Zero out alpha for those pixels
    data[:, :, 3][black_mask] = 0

    return Image.fromarray(data, "RGBA")


def process_ico(src: Path, dst: Path, threshold: int) -> bool:
    """
    ICO files are containers — they hold multiple copies of the same icon
    at different sizes (e.g. 16x16, 32x32, 48x48, 256x256).
    We must process every frame and save them all back into one .ico,
    otherwise browsers pick the wrong size or lose frames entirely.
    """
    img = Image.open(src)
    frames = []
    sizes = []

    try:
        while True:
            sizes.append(img.size)
            frames.append(remove_black_background(img.copy(), threshold))
            img.seek(img.tell() + 1)
    except EOFError:
        pass  # reached the last frame — normal exit

    dst.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        dst,
        format="ICO",
        sizes=sizes,
        append_images=frames[1:],
    )
    print(f"  ✓  {src.name}  →  {dst}  ({len(frames)} frame(s))")
    return True


def process_png(src: Path, dst: Path, threshold: int) -> bool:
    img = Image.open(src)
    result = remove_black_background(img, threshold)
    dst.parent.mkdir(parents=True, exist_ok=True)
    result.save(dst, format="PNG")
    print(f"  ✓  {src.name}  →  {dst}")
    return True


def process_file(src: Path, dst: Path, threshold: int) -> bool:
    try:
        if src.suffix.lower() == ".ico":
            return process_ico(src, dst, threshold)
        else:
            return process_png(src, dst, threshold)
    except Exception as e:
        print(f"  ✗  {src.name}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Remove black backgrounds from PNG app icons."
    )
    parser.add_argument("files", nargs="*", help="PNG file(s) to process")
    parser.add_argument("--folder", "-f", help="Process all PNGs inside this folder")
    parser.add_argument(
        "--output", "-o",
        help="Output folder (default: overwrite originals)",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=int, default=30,
        help="Black sensitivity 0–255 (default: 30). Higher = remove darker grays too.",
    )
    args = parser.parse_args()

    if args.threshold < 0 or args.threshold > 255:
        parser.error("--threshold must be between 0 and 255")

    targets: list[tuple[Path, Path]] = []   # (source, destination)

    # --- collect files ---
    if args.folder:
        folder = Path(args.folder)
        if not folder.is_dir():
            sys.exit(f"Error: '{folder}' is not a directory.")
        files_in_folder = sorted(folder.glob("*.png")) + sorted(folder.glob("*.ico"))
        if not files_in_folder:
            sys.exit(f"No PNG or ICO files found in '{folder}'.")
        for src in files_in_folder:
            if args.output:
                dst = Path(args.output) / src.name
            else:
                dst = src          # overwrite in-place
            targets.append((src, dst))

    for filepath in args.files:
        src = Path(filepath)
        if not src.is_file():
            print(f"  ✗  '{src}' not found – skipped.", file=sys.stderr)
            continue
        if args.output:
            dst = Path(args.output) / src.name
        else:
            dst = src
        targets.append((src, dst))

    if not targets:
        parser.print_help()
        sys.exit(1)

    print(f"\nRemoving black backgrounds (threshold={args.threshold}) …\n")
    ok = sum(process_file(s, d, args.threshold) for s, d in targets)
    print(f"\nDone: {ok}/{len(targets)} file(s) processed successfully.")


if __name__ == "__main__":
    main()
