#!/usr/bin/env python3
"""
Generate favicon assets from logo.svg for base.html (lines 16-19).
Outputs: apple-touch-icon.png (180x180), favicon-32x32.png, favicon-16x16.png,
         safari-pinned-tab.svg
Requires: cairosvg (pip install cairosvg)
"""
import os

try:
    import cairosvg
except ImportError:
    raise SystemExit("Install cairosvg: pip install cairosvg")

# Paths relative to project root
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_SVG = os.path.join(BASE, "static", "images_new", "logos", "logo.svg")
ICON_SQUARE_SVG = os.path.join(BASE, "static", "images", "favicon", "favicon-icon-square.svg")
OUT_DIR = os.path.join(BASE, "static", "images", "favicon")

# Use square icon SVG if present (cropped logo), else full logo
SOURCE_SVG = ICON_SQUARE_SVG if os.path.isfile(ICON_SQUARE_SVG) else LOGO_SVG

SIZES = [
    ("apple-touch-icon.png", 180, 180),
    ("favicon-32x32.png", 32, 32),
    ("favicon-16x16.png", 16, 16),
]

SAFARI_PINNED_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="46" height="46" viewBox="0 0 46 46" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M21.1378 13.8209V32.1572C21.1378 32.6018 21.9918 33.2769 22.412 33.2769H26.4654V39.5306H21.7946C20.7752 39.5306 18.8563 38.6598 18.025 38.0514C15.6251 36.293 14.9122 34.0294 14.8045 31.1574C14.6968 28.2566 14.8909 25.2982 14.8075 22.3913H10.1368L10.0215 22.276V16.8719L10.1368 16.7566H14.8075V13.9392L14.9228 13.8239H21.1363L21.1378 13.8209Z" fill="currentColor"/>
  <path d="M29.2448 5.71338V16.5611L29.1295 16.6779H23.6866V11.2722H18.2832V5.71338H29.2448Z" fill="currentColor"/>
  <path d="M37.4123 4.59973V40.6745H37.0723V4.59973H37.4123Z" fill="currentColor"/>
</svg>
"""


def main():
    if not os.path.isfile(SOURCE_SVG):
        raise SystemExit(f"Source SVG not found: {SOURCE_SVG}")
    os.makedirs(OUT_DIR, exist_ok=True)

    for name, w, h in SIZES:
        out_path = os.path.join(OUT_DIR, name)
        cairosvg.svg2png(url=SOURCE_SVG, write_to=out_path, output_width=w, output_height=h)
        print(f"Wrote {out_path}")

    safari_path = os.path.join(OUT_DIR, "safari-pinned-tab.svg")
    with open(safari_path, "w") as f:
        f.write(SAFARI_PINNED_SVG)
    print(f"Wrote {safari_path}")


if __name__ == "__main__":
    main()
