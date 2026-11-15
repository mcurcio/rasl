"""Draws rasl's pixel-art logo on a grid and writes it as SVG.

The logo is a pixel light bulb next to the word "rasl" in a chunky pixel font, with a strip of
LEDs under the word whose colours step through a hue sweep. The icon is the bulb on its own,
square, with a short LED strip under it. Each SVG has one <path> per colour, one rectangle per
horizontal run of pixels, a viewBox in grid units and shape-rendering="crispEdges": no fonts,
no external references, no raster data.

The SVGs in docs/assets/ are this script's output. Change the logo here, then run

    python3 tools/logo.py

from the repository root (standard library only). The output is deterministic.

Outputs:
    docs/assets/logo.svg       the README header, for light backgrounds
    docs/assets/logo-dark.svg  the same, for dark backgrounds (only the ink colour changes)
    docs/assets/icon.svg       a square mark, for a favicon or avatar
"""

import colorsys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets"

INK = "#1b1f2a"  # letters, outlines and the bulb's base on a light background
INK_DARK = "#e6edf3"  # the same on a dark background
GLASS = "#ffd23f"  # the lit bulb
GLASS_HI = "#fff4b8"  # the bulb's highlight
GLASS_LO = "#f29e1f"  # the bulb's shaded side
FILAMENT = "#d2541b"  # the glowing filament
METAL = "#8b93a1"  # the base's threads; reads on white and on #0d1117

Grid = dict[tuple[int, int], str]


def hue_sweep(n: int) -> list[str]:
    """n colours stepping evenly through hue from red to violet (HSV, s=0.85, v=0.95), as hex."""
    out = []
    for i in range(n):
        r, g, b = colorsys.hsv_to_rgb(i * 0.8 / (n - 1), 0.85, 0.95)
        out.append(f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}")
    return out


# Lowercase glyphs: three-pixel stems, two-pixel bars. "#" is ink. x-height 9 rows; "l" rises 4
# rows above it.
GLYPHS = {
    "r": [
        "###.#####.",
        "##########",
        "#####..###",
        "####......",
        "###.......",
        "###.......",
        "###.......",
        "###.......",
        "###.......",
    ],
    "a": [
        ".########.",
        "##########",
        ".......###",
        "..########",
        ".#########",
        "###....###",
        "###....###",
        "##########",
        ".#####.###",
    ],
    "s": [
        ".#########",
        "##########",
        "###.......",
        "#########.",
        ".#########",
        ".......###",
        ".......###",
        "##########",
        "#########.",
    ],
    "l": ["####.", "####."] + [".###."] * 10 + [".####"],
}
GAP = 2  # columns between letters


def blit(g: Grid, rows: list[str], x0: int, y0: int, colour: str) -> None:
    """Paint the "#" cells of rows into g with their top-left corner at (x0, y0)."""
    for dy, row in enumerate(rows):
        for dx, cell in enumerate(row):
            if cell == "#":
                g[(x0 + dx, y0 + dy)] = colour


# The bulb, 11 wide by 15 tall. g: glass, h: highlight, s: shade, f: filament, o: outline (ink),
# m: metal thread, b: base (ink).
BULB = [
    "...ooooo...",
    "..oggggso..",
    ".ohhggggso.",
    "ohhggggggso",
    "ohggfffggso",
    "oggfgggfgso",
    "ogggfgfggso",
    ".oggfgfgso.",
    "..oggfgso..",
    "...ogfgo...",
    "...obbbo...",
    "...mmmmm...",
    "...bbbbb...",
    "...mmmmm...",
    "....bbb....",
]
RAYS = [(-2, 4), (-3, 4), (12, 4), (13, 4), (5, -2), (5, -3), (0, 0), (-1, -1), (10, 0), (11, -1)]


def bulb(g: Grid, x0: int, y0: int, ink: str) -> None:
    """Paint the bulb with its top-left corner at (x0, y0), with short rays around it."""
    colours = {"g": GLASS, "h": GLASS_HI, "s": GLASS_LO, "f": FILAMENT, "o": ink, "m": METAL, "b": ink}
    for dy, row in enumerate(BULB):
        for dx, cell in enumerate(row):
            if cell in colours:
                g[(x0 + dx, y0 + dy)] = colours[cell]
    for dx, dy in RAYS:
        g[(x0 + dx, y0 + dy)] = GLASS_LO


def led_strip(g: Grid, x0: int, y: int, count: int) -> int:
    """Paint count 2x2 LEDs, 1 column apart, on a 1-pixel wire under them; return the strip's width."""
    width = count * 3 - 1
    for x in range(x0, x0 + width):
        g[(x, y + 2)] = METAL
    for i, colour in enumerate(hue_sweep(count)):
        for dx in range(2):
            for dy in range(2):
                g[(x0 + i * 3 + dx, y + dy)] = colour
    return width


def logo(ink: str) -> Grid:
    """The bulb, the word "rasl" to its right, and an LED strip as wide as the word under it.

    The bulb's last row sits on the letters' baseline.
    """
    g: Grid = {}
    bulb_top = 3
    bulb(g, 3, bulb_top, ink)
    baseline = bulb_top + len(BULB) - 1
    left = x = 21
    for ch in "rasl":
        rows = GLYPHS[ch]
        blit(g, rows, x, baseline - len(rows) + 1, ink)
        x += max(len(r) for r in rows) + GAP
    word_w = x - GAP - left
    count = (word_w + 1) // 3
    led_strip(g, left + (word_w - (count * 3 - 1)) // 2, baseline + 2, count)
    return g


def icon(ink: str) -> Grid:
    """The bulb alone with a four-LED strip as wide as the bulb under it, centred in a 25 x 25 square.

    With its rays the bulb is 17 pixels wide; with the strip the drawing is 23 tall.
    """
    g: Grid = {}
    x0, y0 = 7, 4
    bulb(g, x0, y0, ink)
    led_strip(g, x0, y0 + len(BULB) + 2, 4)
    return g


def svg(grid: Grid, w: int | None = None, h: int | None = None, scale: int = 6) -> str:
    """The grid as SVG: one <path> per colour, one rectangle per horizontal run.

    The viewBox starts at (0, 0) and is w by h grid units; by default it fits the drawn pixels plus a
    one-pixel margin. The width and height attributes are the viewBox times scale, in CSS pixels.
    """
    if w is None:
        w = max(x for x, _ in grid) + 2
    if h is None:
        h = max(y for _, y in grid) + 2
    by_colour: dict[str, list[tuple[int, int]]] = {}
    for (x, y), c in grid.items():
        by_colour.setdefault(c, []).append((x, y))
    paths = []
    for c in sorted(by_colour):
        pts = sorted(by_colour[c], key=lambda p: (p[1], p[0]))
        d = []
        i = 0
        while i < len(pts):
            x, y = pts[i]
            j = i
            while j + 1 < len(pts) and pts[j + 1] == (pts[j][0] + 1, y):
                j += 1
            d.append(f"M{x} {y}h{j - i + 1}v1h-{j - i + 1}z")
            i = j + 1
        paths.append(f'<path fill="{c}" d="{"".join(d)}"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w * scale}" '
        f'height="{h * scale}" shape-rendering="crispEdges">' + "".join(paths) + "</svg>\n"
    )


def main() -> None:
    """Write logo.svg, logo-dark.svg and icon.svg to docs/assets/."""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "logo.svg").write_text(svg(logo(INK)))
    (OUT / "logo-dark.svg").write_text(svg(logo(INK_DARK)))
    (OUT / "icon.svg").write_text(svg(icon(INK), 25, 25, scale=8))


if __name__ == "__main__":
    main()
