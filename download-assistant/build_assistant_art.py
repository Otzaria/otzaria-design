"""Generates the artwork of Otzaria's Windows download assistant (installer/download_assistant.iss).

Output (one flat folder, see --out): every PNG of the assistant, named `<asset>_<scale>.png` — the UI kit
(caption buttons, buttons, 3-slice cards, radio/check, icon tiles, step dots, progress bar, field frames,
badges) for every DPI scale in SCALES, and the book-opening frames of the welcome page and the faded
title blocks (Hebrew `title_N`, English `title_en_N`) only at BOOK_SRC_SCALE / TITLE_SRC_SCALE (Inno's
TBitmapImage shrinks them with Stretch) —
plus `assistant_art.isi`, an Inno Setup include with #define constants (frame
count, every asset's 100% size, the scale list, the welcome-sequence timings). The Inno code must take
its numbers from that include, so art and code cannot drift. Everything is drawn supersampled and
downsampled: the book and title with LANCZOS, the UI kit with an exact box filter (LANCZOS leaves light
halos at hard edges). Every scale is rendered from a high-resolution master. Every PNG is truecolor
RGBA: Inno's VCL keeps only on/off transparency for palette PNGs. Light theme only.

Inputs are read only from `sources/` next to this script (the logo and the Fluent icon fonts); fill it
once from an Otzaria checkout and the local pub cache with --collect-sources. Text is set in Segoe UI,
read from the Windows fonts folder at render time (it may not be redistributed), so rendering needs Windows.

    python build_assistant_art.py --out <dir>             # default <dir>: ./out
    python build_assistant_art.py --out <dir> --preview [<dir>]   # also GIFs + contact sheet (./preview)
    python build_assistant_art.py --collect-sources [--otzaria <repo>]   # default repo: ../../otzaria
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


def rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


# =====================================================================================================
# Tunables. Sizes and positions are in 100%-DPI units; colours are sRGB.
# =====================================================================================================

ART_VERSION = "1.4.0"
SCALES = (100, 125, 150, 175, 200, 250)
# The book and the title ship only at this scale; Inno shrinks them for every other scale (SPLINE16,
# measured 44.5-46.8 dB vs native frames). Only shrink: enlarging 200 -> 250 measured 34.9 dB.
BOOK_SRC_SCALE = TITLE_SRC_SCALE = max(SCALES)
SUPERSAMPLE = 4

# --- palette: the Otzaria app's light theme (AppThemeData.light of seed #2C1B02, measured)
PAGE = rgb("#F6EDE5")             # panelBackground: window/page
TITLE_BAR = rgb("#F3E6DA")        # topBarBackground (surfaceContainerHigh)
TITLE_BAR_BORDER = rgb("#E1D4C8")
CAPTION_HOVER = rgb("#EDE4DC")
CAPTION_GLYPH = rgb("#1A1918")
CLOSE_HOVER = rgb("#C42B1C")      # Windows 11 convention, white glyph
CARD = rgb("#FFF8F4")             # AppSurfaces.card (surface); AppCard has no border and no elevation
CARD_SEL = rgb("#FEF0E3")         # cardSelectionOverlay (secondaryContainer@30) over the card
OUTLINE_VARIANT = rgb("#D3C4B4")  # dividers, idle step dots
OUTLINE = rgb("#817567")          # outlined button, text field border, faint text
PRIMARY = rgb("#805610")
PRIMARY_HOVER = rgb("#8A6423")    # onPrimary@8 over primary
PRIMARY_PRESSED = rgb("#8F6A2D")  # onPrimary@12 over primary
ON_PRIMARY = rgb("#FFFFFF")
DISABLED = rgb("#DDD3CC")         # onSurface@12 over the page
DISABLED_TEXT = rgb("#A59D95")
TEXT = rgb("#201B13")             # onSurface
MUTED = rgb("#4F4539")            # onSurfaceVariant
FAINT = OUTLINE
TILE = rgb("#FBDEBC")             # secondaryContainer
TILE_GLYPH = rgb("#56442A")       # onSecondaryContainer
TONAL, ON_TONAL = TILE, TILE_GLYPH  # FilledButton.tonal fill and label
TRACK = TILE
ERROR = rgb("#BA1A1A")
WHITE = rgb("#FFFFFF")
FIELD = rgb("#FFFFFF")            # surfaceContainerLowest
GLOW = rgb("#E9B96A")
HOVER_ALPHA, PRESSED_ALPHA = 0.08, 0.12   # M3 state layers of primary
SHADOW = (0, 0, 0)
CARD_SHADOW = 0                   # shadow below the card body, inside the asset (AppCard has none)

# --- texts baked into images (title block) or drawn only in the preview
TITLE = "מסייע ההורדות של אוצריא"
SUBTITLE = "ספרייה תורנית חינמית"
TITLE_PX, SUBTITLE_PX = 23, 14
TITLE_EN = "Otzaria Download Assistant"   # title_en_N, left to right
SUBTITLE_EN = "Free Torah Library"
TITLE_EN_PX, SUBTITLE_EN_PX = 21, 15      # Latin optically matched to the Hebrew lines (same title width)
TITLE_ORNAMENT_GAP = 14          # from each text's ink to the ornament's centre line
PREVIEW_NOTE = ("כלי זה אינו מתקין את אוצריא — הוא מוריד את הקבצים", "ומכין מהם התקנה, גם למחשב בלי אינטרנט.")
PREVIEW_BUTTON = "בואו נתחיל"
PREVIEW_NOTE_EN = ("This tool doesn't install Otzaria. It downloads the files",
                   "and prepares an installation, even for an offline computer.")
PREVIEW_BUTTON_EN = "Let's get started"

# --- window and asset geometry (mirrored into assistant_art.isi)
WINDOW = (400, 660)
MARGIN = 24
BOOK_SIZE = 220
TITLE_SIZE = (352, 100)
MARK_SIZE, LOGO_SIZE = 16, 56
CAPTION_SIZE = (46, 32)        # window_manager's WindowCaption buttons; also the title bar height
BUTTONS = {"primary": (160, 40), "wide": (352, 44), "ghost": (120, 40), "outline": (120, 40),
           "tonal": (120, 40), "tonalwide": (352, 40)}
RADIUS = 8                        # buttons, cards, fields, icon tiles (the app uses 8 everywhere)
CARD_W, CARD_CAP, CARD_MID = 352, 16, 1
TOGGLE_SIZE = 20
ICON_TILE, ICON_GLYPH = 40, 24
DOT_SIZE, DOT_CUR_W = 6, 20
BAR_CAP_W, BAR_MID_W, BAR_H = 4, 1, 8
FIELD_SIZE = (352, 44)
BADGE_SIZE = 72

# --- welcome sequence (ms and units)
BOOK_FRAMES = 24
BOOK_FPS = 24
PAGE_FADE_MS = 150
BOOK_TOP = 236                # the book opens centred below the title bar...
BOOK_RISE = 130               # ...then rises to top 106 (easeOutCubic)
RISE_MS = 650
RISE_START_FRAME = 17         # the rise starts as the halves touch down, so the motion flows on
TITLE_TOP = 340
TITLE_SLIDE = 8
TITLE_FADE_MS = 400
TITLE_STEPS = 8
FOOTER_FADE_MS = 250
NOTE_TOP = 498
BUTTON_TOP = 568
PREVIEW_HOLD_MS = 2000

# --- book animation: the closed book faces the viewer with its fore-edge, then opens to both sides
BOOK_W = 176.0              # open logo width inside the frame
BOOK_CY = 104.0             # its vertical centre
BLOCK = 12.5                # thickness of each half (page stack + board)
BOARD = 2.6                 # cover board thickness at the fore-edge
EDGE_LAYER = 0.4            # page layers drawn through the thickness
CAMERA = 6.0                # camera distance in half-book widths (smaller = stronger perspective)
LAND_FRAME = 20             # the halves pass flat by OVERSHOOT here, then settle on the last frame
OVERSHOOT = 3.0             # degrees
GLINT_FRAMES = 7            # a sparkle runs down the gilded edge in the first frames
MASTER = 10                 # master pixels per unit (SUPERSAMPLE x the largest scale)
SCENE_LIGHT = (-0.15, -0.3, 0.94)
SHADOW_SLANT = (0.0, 0.3)   # ground offset of a cast shadow per unit of height
INK = (46, 28, 8)
GLINT = (255, 240, 196)
GOLD_RAMP = (
    (0.00, (70, 32, 2)), (0.14, (110, 63, 10)), (0.30, (140, 98, 38)), (0.46, (166, 126, 56)),
    (0.60, (192, 154, 76)), (0.74, (218, 187, 104)), (0.88, (241, 221, 146)), (1.00, (255, 246, 205)),
)
IVORY, GILT = (242, 231, 202), (214, 176, 100)

# --- icons: Fluent System Icons (the app's icon set)
FLUENT_DISMISS = ("Regular", 62312)       # dismiss_16
FLUENT_CHECK = ("Filled", 62101)          # checkmark_24
FLUENT_OFFLINE = ("Regular", 61018)       # wifi_off_24
FLUENT_PAUSE = ("Regular", 62882)         # pause_24
ICONS = {                                     # (style, codepoint, design size): icon name
    "this_pc": ("Regular", 62298, 24),        # desktop_24
    "other_pc": ("Regular", 58506, 24),       # desktop_arrow_right_24
    "windows": None,                          # four panes, drawn
    "macos": ("Regular", 58522, 24),          # desktop_mac_24
    "linux": ("Regular", 61039, 20),          # window_console_20
    "android": ("Regular", 62945, 24),        # phone_24
    "arch_x64": ("Regular", 62300, 24),       # developer_board_24
    "arch_arm": ("Regular", 58541, 20),       # developer_board_lightning_20
    "fmt_deb": ("Regular", 57788, 24),        # box_24
    "fmt_rpm": ("Regular", 62262, 24),        # cube_24
    "fmt_portable": ("Regular", 62518, 24),   # folder_zip_24
    "preset_full": ("Regular", 62675, 24),    # library_24
    "preset_full_indexed": ("Otzaria", 0xE030, 24),  # OtzariaIcons.search_in_the_library_24_regular
    "preset_basic": ("Regular", 63742, 24),   # book_24
    "preset_update": ("Regular", 61841, 24),  # arrow_sync_24
    "preset_custom": ("Regular", 62856, 24),  # options_24
    "folder": ("Regular", 62511, 24),         # folder_open_24
    "component": ("Regular", 59882, 24),      # puzzle_piece_24
}

# --- inputs
HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
LOGO_FILE = "iconnew.png"
# The app's UI font. Read from the system at render time: Segoe UI may not be redistributed.
SYSTEM_FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
UI_FONT, UI_FONT_SEMIBOLD = "segoeui.ttf", "seguisb.ttf"
FLUENT_PACKAGE = "fluentui_system_icons-1.1.273"
# The app's own icon font (git dependency otzaria_icons, at the ref pinned in Otzaria's pubspec.yaml).
OTZARIA_ICONS_PACKAGE = "otzaria_icons-5a614a7046c17e4321af31066cd9f0feae7c2e47"
ICON_FONTS = {"Otzaria": "otzaria_icons.otf"}  # style -> font file; other styles are Fluent
COLLECT = {  # sources/<name>: path inside the Otzaria repo, or (pub package, path[, "git"])
    LOGO_FILE: "assets/icon/iconnew.png",
    "FluentSystemIcons-Regular.ttf": (FLUENT_PACKAGE, "lib/fonts/FluentSystemIcons-Regular.ttf"),
    "FluentSystemIcons-Filled.ttf": (FLUENT_PACKAGE, "lib/fonts/FluentSystemIcons-Filled.ttf"),
    "otzaria_icons.otf": (OTZARIA_ICONS_PACKAGE, "lib/fonts/otzaria_icons.otf", "git"),
}
ASSET_PREFIXES = ("book_", "title_", "mark_", "logo_", "cap_", "btn_", "card_", "radio_", "check_",
                  "ico_", "dot_", "bar_", "field_", "badge_")

# =====================================================================================================


def px(value: float, scale: int) -> int:
    """100%-units to device pixels, rounding half up like Inno's ScaleX (MulDiv)."""
    return max(1, math.floor(value * scale / 100 + 0.5))


def mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def rgba(color: tuple, alpha: int = 255) -> tuple:
    return tuple(int(c) for c in color[:3]) + (int(alpha),)


def ease_in_out(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def ease_out_cubic(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


class Canvas:
    """A supersampled drawing surface for one asset at one scale.

    The size is snapped to whole device pixels first, so edges drawn at 0 and at the full size stay
    crisp after downsampling. `u` is supersampled pixels per 100%-unit.
    """

    def __init__(self, w: float, h: float, scale: int, background: tuple | None = None):
        self.scale = scale
        self.w, self.h = px(w, scale), px(h, scale)
        self.u = scale / 100 * SUPERSAMPLE
        self.img = Image.new("RGBA", (self.w * SUPERSAMPLE, self.h * SUPERSAMPLE),
                             rgba(background) if background else (0, 0, 0, 0))

    @property
    def W(self) -> int:
        return self.img.width

    @property
    def H(self) -> int:
        return self.img.height

    def dev(self, value: float) -> int:
        """A stroke width snapped to whole device pixels, in supersampled pixels."""
        return px(value, self.scale) * SUPERSAMPLE

    def rrect(self, box: tuple, radius: float, color: tuple, alpha: int = 255) -> None:
        """Rounded rectangle; `box` is half-open [x0, y0, x1, y1) in supersampled pixels."""
        x0, y0, x1, y1 = box
        if x1 - x0 < 1 or y1 - y0 < 1:
            return
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        r = max(0.0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
        ImageDraw.Draw(layer).rounded_rectangle((x0, y0, x1 - 1, y1 - 1), radius=r, fill=rgba(color, alpha))
        self.img.alpha_composite(layer)

    def ring(self, box: tuple, radius: float, width: int, line: tuple, fill: tuple | None) -> None:
        x0, y0, x1, y1 = box
        self.rrect(box, radius, line)
        inner = (x0 + width, y0 + width, x1 - width, y1 - width)
        if fill is None:
            cut = Image.new("L", self.img.size, 0)
            ImageDraw.Draw(cut).rounded_rectangle((inner[0], inner[1], inner[2] - 1, inner[3] - 1),
                                                  radius=max(0.0, radius - width), fill=255)
            alpha = np.asarray(self.img.getchannel("A"), np.float32) * (1 - np.asarray(cut, np.float32) / 255)
            self.img.putalpha(Image.fromarray(alpha.astype(np.uint8)))
        else:
            self.rrect(inner, max(0.0, radius - width), fill)

    def ellipse(self, box: tuple, color: tuple, alpha: int = 255) -> None:
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        x0, y0, x1, y1 = box
        ImageDraw.Draw(layer).ellipse((x0, y0, x1 - 1, y1 - 1), fill=rgba(color, alpha))
        self.img.alpha_composite(layer)

    def paste(self, im: Image.Image, cx: float, cy: float) -> None:
        self.img.alpha_composite(im, (round(cx - im.width / 2), round(cy - im.height / 2)))

    def result(self, resample: int | None = None) -> Image.Image:
        """Box-filtered by default (exact pixel coverage): LANCZOS rings at hard edges into light halos.
        Averaged in float with premultiplied alpha, so a translucent fill keeps its exact colour."""
        if resample is not None:
            return self.img.resize((self.w, self.h), resample)
        a = np.asarray(self.img, np.float64).reshape(self.h, SUPERSAMPLE, self.w, SUPERSAMPLE, 4)
        alpha = a[..., 3].sum((1, 3))
        color = (a[..., :3] * a[..., 3:]).sum((1, 3)) / np.maximum(alpha, 1e-9)[..., None]
        out = np.dstack([color, alpha / SUPERSAMPLE ** 2])
        return Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), "RGBA")


# ---------------------------------------------------------------- glyphs, text, logo

_fonts: dict = {}


def ui_font(size: float, semibold: bool = False) -> ImageFont.FreeTypeFont:
    """Segoe UI from the Windows fonts folder (the app's and Inno's UI font)."""
    name = UI_FONT_SEMIBOLD if semibold else UI_FONT
    if not (SYSTEM_FONTS / name).exists():
        raise SystemExit(f"{name} not found in {SYSTEM_FONTS}: render on Windows (Segoe UI is not redistributable).")
    return font(name, size, folder=SYSTEM_FONTS)


def font(name: str, size: float, weight: int | None = None, folder: Path = SOURCES) -> ImageFont.FreeTypeFont:
    key = (folder, name, round(size), weight)
    if key not in _fonts:
        f = ImageFont.truetype(str(folder / name), max(1, round(size)))
        if weight is not None:
            f.set_variation_by_axes([weight])
        _fonts[key] = f
    return _fonts[key]


def glyph(icon: tuple, size: float, color: tuple) -> Image.Image:
    """An icon glyph (Fluent, or the app's own font per ICON_FONTS), `size` supersampled pixels for its em square."""
    style, codepoint = icon
    f = font(ICON_FONTS.get(style, f"FluentSystemIcons-{style}.ttf"), size)
    side = math.ceil(size * 1.5)
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).text((side / 2, side / 2), chr(codepoint), font=f, fill=255, anchor="mm")
    out = Image.new("RGBA", mask.size, rgba(color, 0))
    out.putalpha(mask)
    return out


def hebrew(text: str) -> str:
    """Visual order of a Hebrew line (Pillow without raqm lays text out left to right)."""
    return text[::-1]


def text_image(text: str, f: ImageFont.FreeTypeFont, color: tuple, rtl: bool = True) -> Image.Image:
    """A line of text, tightly cropped; info['baseline'] is the baseline's y. Hebrew (rtl) is reversed
    into visual order; Latin is kerned glyph by glyph and cropped to its ink, so it centres on the ink."""
    visual = hebrew(text) if rtl else text
    l, t, r, b = f.getbbox(visual, anchor="ls")
    pad = 4
    if rtl:
        im = Image.new("RGBA", (r - l + pad * 2, b - t + pad * 2), rgba(color, 0))
        ImageDraw.Draw(im).text((pad - l, pad - t), visual, font=f, fill=rgba(color), anchor="ls")
    else:
        kern, x = latin_kerning(f.path), 0.0
        mask = Image.new("L", (r - l + pad * 2 + f.size, b - t + pad * 2), 0)
        d = ImageDraw.Draw(mask)
        for ch, nxt in zip(text, text[1:] + " "):
            d.text((pad - l + x, pad - t), ch, font=f, fill=255, anchor="ls")
            x += f.getlength(ch) + kern(ch, nxt) * f.size
        x0, _, x1, _ = mask.getbbox()
        mask = mask.crop((x0 - pad, 0, x1 + pad, mask.height))
        im = Image.new("RGBA", mask.size, rgba(color, 0))
        im.putalpha(mask)
    im.info["baseline"] = pad - t
    return im


_kerning: dict = {}


def latin_kerning(path: str):
    """(a, b) -> em offset from the font's GPOS 'kern' for Latin, as DirectWrite sets the same text.
    Pillow without raqm applies no kerning (Segoe UI's "To" is -0.1 em)."""
    if path not in _kerning:
        tt = TTFont(path, lazy=True)
        cmap, gpos, upm = tt.getBestCmap(), tt["GPOS"].table, tt["head"].unitsPerEm
        latn = next(s.Script.DefaultLangSys for s in gpos.ScriptList.ScriptRecord if s.ScriptTag == "latn")
        subtables = []
        for record in (gpos.FeatureList.FeatureRecord[i] for i in latn.FeatureIndex):
            if record.FeatureTag == "kern":
                for lookup in (gpos.LookupList.Lookup[i] for i in record.Feature.LookupListIndex):
                    subtables += [s.ExtSubTable if lookup.LookupType == 9 else s for s in lookup.SubTable]

        def pair(a: str, b: str) -> float:
            ga, gb = cmap.get(ord(a)), cmap.get(ord(b))
            for st in subtables:
                if st.LookupType != 2 or ga not in st.Coverage.glyphs:
                    continue
                if st.Format == 1:
                    values = [r.Value1 for r in st.PairSet[st.Coverage.glyphs.index(ga)].PairValueRecord
                              if r.SecondGlyph == gb]
                else:
                    c1, c2 = st.ClassDef1.classDefs.get(ga, 0), st.ClassDef2.classDefs.get(gb, 0)
                    values = [st.Class1Record[c1].Class2Record[c2].Value1]
                advance = getattr(values[0], "XAdvance", 0) if values else 0
                if advance:
                    return advance / upm
            return 0.0

        _kerning[path] = pair
    return _kerning[path]


_logo: Image.Image | None = None


def logo_source() -> Image.Image:
    global _logo
    if _logo is None:
        im = Image.open(SOURCES / LOGO_FILE).convert("RGBA")
        _logo = im.crop(im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox())
    return _logo


def logo_fit(size: int, pad: float = 0.0) -> Image.Image:
    src = logo_source()
    k = size * (1 - 2 * pad) / max(src.size)
    im = src.resize((max(1, round(src.width * k)), max(1, round(src.height * k))), Image.LANCZOS)
    if size <= 64:
        im = im.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=0))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    return out


# ---------------------------------------------------------------- book opening
#
# Units of the BOOK_SIZE frame; the camera looks at the open book from CAMERA half-widths away. Each
# half is a slab hinged at the spine (behind, on the centre line): φ=90 points straight at the viewer,
# so the closed book shows only its fore-edge; φ=0 lies flat, its page face being that half of the logo.

def unit(v) -> np.ndarray:
    a = np.asarray(v, np.float64)
    return a / np.linalg.norm(a)


def ramp(t, stops: tuple) -> np.ndarray:
    xs = [s for s, _ in stops]
    return np.stack([np.interp(t, xs, [c[ch] for _, c in stops]) for ch in range(3)], axis=-1)


def homography(dst: list, src: list) -> list:
    """PERSPECTIVE coefficients mapping the output points `dst` back to the texture points `src`."""
    rows, rhs = [], []
    for (x, y), (sx, sy) in zip(dst, src):
        rows.append([x, y, 1, 0, 0, 0, -sx * x, -sx * y])
        rows.append([0, 0, 0, x, y, 1, -sy * x, -sy * y])
        rhs += [sx, sy]
    return np.linalg.solve(np.array(rows, np.float64), np.array(rhs, np.float64)).tolist()


def quad_area(pts: list) -> float:
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))


def gold_mask(im: Image.Image) -> np.ndarray:
    a = np.asarray(im, np.float32) / 255
    top = a[..., :3].max(-1)
    sat = (top - a[..., :3].min(-1)) / np.maximum(top, 1e-3)
    return np.clip((sat - 0.2) / 0.2, 0, 1) * a[..., 3]


def solid(mask: Image.Image, color) -> Image.Image:
    layer = Image.new("RGBA", mask.size, rgba(color, 0))
    layer.putalpha(mask)
    return layer


def edge_profile(height: float) -> tuple[np.ndarray, Image.Image]:
    """One half's fore-edge, from the seam (b=0) to the cover board (b=BLOCK): the colour of each page
    layer, and the face-on texture built from the same layers (gilded page edges, gold board)."""
    n = round(BLOCK / EDGE_LAYER)
    rng = np.random.default_rng(7)
    b = (np.arange(n) + 0.5) * EDGE_LAYER
    pages = BLOCK - BOARD
    across = np.clip(b / pages, 0, 1)
    g = 0.55 + 0.3 * np.clip(np.sin(np.pi * across), 0, 1) ** 0.6 + rng.uniform(-0.1, 0.1, n)
    colors = (np.array(IVORY, np.float32)[None] * (1 - g[:, None]) + np.array(GILT, np.float32)[None] * g[:, None])
    quire = (np.arange(n) % 3 == 2) * rng.uniform(0.08, 0.16, n)    # every few pages a finer dark line
    colors *= (1 - 0.3 * np.exp(-b / 0.5) - quire)[:, None]
    board = b > pages
    colors[board] = ramp(0.32 + 0.6 * np.sin(np.pi * (b[board] - pages) / BOARD) ** 0.7, GOLD_RAMP)

    t = MASTER
    w, h = round(BLOCK * t), round(height * t)
    col = np.minimum((np.arange(w) + 0.5) / t / EDGE_LAYER, n - 1).astype(int)
    frac = ((np.arange(w) + 0.5) / t / EDGE_LAYER) % 1
    rows = colors[col] * (1 - 0.14 * np.exp(-(frac / 0.18) ** 2) * ~board[col])[:, None]
    y = (np.arange(h, dtype=np.float32) + 0.5) / h
    sheen = 1 + 0.12 * np.exp(-((y - 0.28) / 0.14) ** 2) - 0.1 * y
    rgb = rows[None, :, :] * sheen[:, None, None]
    shape = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shape).rounded_rectangle((-w, 0, w - 1, h - 1), radius=3 * t, fill=255)
    tex = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.asarray(shape)]).astype(np.uint8), "RGBA")
    return colors, tex


class Book:
    """Textures and geometry shared by all opening frames."""

    def __init__(self) -> None:
        self.logo = logo_source()
        self.k = BOOK_W / self.logo.width                 # units per logo pixel
        self.spine_px = self.logo.width // 2
        self.half = BOOK_W / 2
        self.height = self.logo.height * self.k
        self.top = BOOK_CY - self.height / 2
        alpha = np.asarray(self.logo.getchannel("A"))
        # The fore-edge face spans the outermost column, so it lines up with the layered sides.
        rows = np.where(alpha[:, 3] > 128)[0]
        self.edge_top, self.edge_bottom = self.top + rows[0] * self.k, self.top + (rows[-1] + 1) * self.k
        rows = np.where(alpha[:, round(self.logo.width * 0.066)] > 128)[0]
        y = np.arange(self.logo.height, dtype=np.float32)
        self.beyond_boards = np.clip(np.maximum(rows[0] - y, y - rows[-1]) / 12, 0, 1)
        self.pages = {s: self.logo.crop((0, 0, self.spine_px, self.logo.height)) if s < 0 else
                      self.logo.crop((self.spine_px, 0, self.logo.width, self.logo.height)) for s in (-1, 1)}
        self.gold = {s: gold_mask(im) for s, im in self.pages.items()}
        self.layer_colors, self.edge = edge_profile(self.edge_bottom - self.edge_top)


def opening_angle(i: int) -> float:
    """Angle of each half above flat in frame i: slow start, quick middle, a small dip that settles."""
    if i <= LAND_FRAME:
        q = i / LAND_FRAME
        return 90.0 - (90.0 + OVERSHOOT) * q * q * q * (q * (6 * q - 15) + 10)
    q = (i - LAND_FRAME) / (BOOK_FRAMES - 1 - LAND_FRAME)
    return -OVERSHOOT * (1 - ease_in_out(q))


def lit(tex: Image.Image, factor: float, extra: np.ndarray | None = None) -> Image.Image:
    """`tex` shaded by `factor` (toward warm brown, not grey) plus an optional additive light."""
    a = np.asarray(tex, np.float32).copy()
    tint = 1 - (1 - factor) * np.array([1.0, 1.07, 1.2], np.float32) if factor < 1 else np.full(3, factor, np.float32)
    rgb = a[..., :3] * np.clip(tint, 0, None)
    if extra is not None:
        rgb += extra
    a[..., :3] = np.clip(rgb, 0, 255)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def ground_layer(book: Book, phi: float, size: int) -> Image.Image:
    """Warm halo that grows as the book opens, and a soft contact shadow under its footprint."""
    opened = 1 - max(0.0, math.sin(math.radians(phi)))
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / (size / BOOK_SIZE)
    # Elliptical, and fully transparent before it reaches the frame's edges.
    q = np.hypot((xx - BOOK_SIZE / 2) / 108, (yy - BOOK_CY) / 101) / (0.62 + 0.38 * opened)
    s = np.clip((q - 0.3) / 0.7, 0, 1)
    halo = (0.18 + 0.28 * opened) * (1 - s * s * (3 - 2 * s))
    reach = BLOCK + (book.half - BLOCK) * math.cos(math.radians(max(phi, 0.0)))
    bottom = book.top + book.height
    q = ((xx - BOOK_SIZE / 2) / (reach + 6)) ** 2 + ((yy - (bottom - 4.5)) / 6.5) ** 2
    contact = (0.16 + 0.1 * opened) * np.clip(1 - q, 0, 1) ** 2
    alpha = halo + contact * (1 - halo)
    rgb = (np.array(GLOW, np.float32) * halo[..., None]
           + np.array(INK, np.float32) * (contact * (1 - halo))[..., None]) / np.maximum(alpha, 1e-6)[..., None]
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8), "RGBA")


def render_book(book: Book, i: int) -> Image.Image:
    """Frame i of the opening at MASTER pixels per unit; the last frame is exactly the logo."""
    phi = opening_angle(i)
    M = round(BOOK_SIZE * MASTER)
    small = M // 4
    frame = ground_layer(book, phi, small).resize((M, M), Image.BICUBIC)
    k, W, top, bottom = book.k, book.half, book.top, book.top + book.height
    if i == BOOK_FRAMES - 1:
        left = BOOK_SIZE / 2 - W
        frame.alpha_composite(book.logo.transform(
            (M, M), Image.AFFINE, (1 / (MASTER * k), 0, -left / k, 0, 1 / (MASTER * k), -top / k), Image.BICUBIC))
        return frame

    ph = math.radians(phi)
    lift = max(0.0, math.sin(ph))
    cx, cy, dist = BOOK_SIZE / 2, BOOK_CY, CAMERA * W
    light = unit(SCENE_LIGHT)
    rest_light = 0.45 + 0.55 * light[2]
    sx, sy = SHADOW_SLANT
    corners = [(0, top), (W, top), (W, bottom), (0, bottom)]
    face_alpha = 1 - ease_in_out((86 - phi) / 8)      # the face-on fore-edge hands over to the layers
    # The logo's pages rise above its boards; a closed book has them tucked in, so they grow as it opens.
    rows = 1 - book.beyond_boards * (1 - ease_in_out((82 - phi) / 26))

    def project(p, scale=MASTER) -> tuple:
        s = dist / (dist - p[2])
        return ((cx + (p[0] - cx) * s) * scale, (cy + (p[1] - cy) * s) * scale)

    def light_factor(normal) -> float:
        return min(1.04, (0.45 + 0.55 * max(0.0, float(normal @ light))) / rest_light)

    shadows, drawn = [], []
    for side in (-1, 1):
        along = np.array([side * math.cos(ph), 0.0, math.sin(ph)])       # spine -> fore-edge
        normal = np.array([-side * math.sin(ph), 0.0, math.cos(ph)])     # out of the page face

        def point(a, y, b=0.0):
            return np.array([cx, y, 0.0]) + a * along - b * normal

        tex = book.pages[side]
        if rows.min() < 1:
            arr = np.asarray(tex).copy()
            arr[..., 3] = (arr[..., 3] * rows[:, None]).astype(np.uint8)
            tex = Image.fromarray(arr, "RGBA")
        silhouette = tex.getchannel("A")
        src = [(tex.width * (a / W if side > 0 else 1 - a / W), (y - top) / book.height * tex.height) for a, y in corners]
        layers = []

        # The slab's sides: the page silhouette repeated through the thickness, one copy per page layer.
        if 0.02 < lift < 0.9995:
            band = Image.new("RGBA", (M // 2, M // 2), (0, 0, 0, 0))
            tone = light_factor(along)
            for j in range(len(book.layer_colors) - 1, -1, -1):
                pts = [project(point(a, y, (j + 0.5) * EDGE_LAYER), MASTER / 2) for a, y in corners]
                if abs(quad_area(pts)) > 1:
                    sil = silhouette.transform(band.size, Image.PERSPECTIVE, homography(pts, src), Image.BILINEAR)
                    band.alpha_composite(solid(sil, book.layer_colors[j] * tone))
            layers.append(band.resize((M, M), Image.BICUBIC))

        edge = book.edge
        e_corners = [(0, book.edge_top), (BLOCK, book.edge_top), (BLOCK, book.edge_bottom), (0, book.edge_bottom)]
        e_pts = [project(point(W, y, b)) for b, y in e_corners]
        e_ref = [((cx + side * b) * MASTER, y * MASTER) for b, y in e_corners]
        if face_alpha > 0.002 and (quad_area(e_pts) > 0) == (quad_area(e_ref) > 0) and abs(quad_area(e_pts)) > MASTER * MASTER:
            e_src = [(edge.width * b / BLOCK, (y - book.edge_top) / (book.edge_bottom - book.edge_top) * edge.height)
                     for b, y in e_corners]
            extra = None
            if i < GLINT_FRAMES:
                q = i / (GLINT_FRAMES - 1)
                gy = (np.arange(edge.height, dtype=np.float32) / edge.height - (q * 1.3 - 0.15)) / 0.09
                extra = (np.array(GLINT, np.float32) * (0.75 * math.sin(math.pi * q) * np.exp(-gy * gy))[:, None, None]
                         * np.ones((1, edge.width, 1), np.float32))
            face = lit(edge, light_factor(along), extra)
            if face_alpha < 1:
                face.putalpha(face.getchannel("A").point(lambda v: round(v * face_alpha)))
            layers.append(face.transform((M, M), Image.PERSPECTIVE, homography(e_pts, e_src), Image.BICUBIC))

        pts = [project(point(a, y)) for a, y in corners]
        flat = [((cx + side * a) * MASTER, y * MASTER) for a, y in corners]
        if (quad_area(pts) > 0) == (quad_area(flat) > 0) and abs(quad_area(pts)) > MASTER * MASTER:
            h, w = tex.height, tex.width
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            a_norm = xx / w if side > 0 else 1 - xx / w                  # 0 at the spine, 1 at the fore-edge
            p = 1 - min(1.0, max(0.0, phi / 90))
            band = np.exp(-((a_norm * 0.8 + yy / h * 0.3 - (1.25 - 1.45 * p)) / 0.13) ** 2)
            glint = 0.42 * math.sin(math.pi * p) * band * book.gold[side]
            arr = np.asarray(lit(tex, light_factor(normal), np.array(GLINT, np.float32) * glint[..., None]), np.float32).copy()
            # Gutter shadow, and the narrow V of a nearly closed book lets little light in.
            arr[..., :3] *= ((1 - 0.3 * lift * np.exp(-(a_norm * W / 16) ** 1.5)) * (1 - 0.45 * lift ** 16))[..., None]
            face = Image.fromarray(arr.astype(np.uint8), "RGBA")
            layers.append(face.transform((M, M), Image.PERSPECTIVE, homography(pts, src), Image.BICUBIC))
        drawn += layers

        # A plane through the slab (spine at the page face, fore-edge at the back) so a standing half
        # still casts a shadow as wide as its thickness.
        caster = [point(a, y, BLOCK * a / W) for a, y in corners]
        shadows.append(([((p[0] + sx * p[2]) * MASTER / 4, (p[1] + sy * p[2]) * MASTER / 4) for p in caster], src, silhouette))

    if lift > 0.01:
        mask = Image.new("L", (small, small), 0)
        for pts, src, silhouette in shadows:
            if abs(quad_area(pts)) > 2:
                part = silhouette.transform((small, small), Image.PERSPECTIVE, homography(pts, src), Image.BILINEAR)
                mask = ImageChops.lighter(mask, part)
        mask = mask.filter(ImageFilter.GaussianBlur((1.0 + 0.08 * W * lift) * MASTER / 4)).resize((M, M), Image.BICUBIC)
        opacity = 0.3 * lift ** 0.6
        frame.alpha_composite(solid(mask.point(lambda v: round(v * opacity)), INK))

    for layer in drawn:
        frame.alpha_composite(layer)
    return frame


_masters: list[Image.Image] = []


def book_masters() -> list[Image.Image]:
    if not _masters:
        book = Book()
        _masters.extend(render_book(book, i) for i in range(BOOK_FRAMES))
    return _masters


def book_frames(scale: int) -> list[Image.Image]:
    size = px(BOOK_SIZE, scale)
    return [m.resize((size, size), Image.LANCZOS) for m in book_masters()]


# ---------------------------------------------------------------- title block

def title_frames(scale: int, english: bool = False) -> list[Image.Image]:
    """Title, a small gold ornament and the subtitle, centred as a group; frame n has alpha step n."""
    c = Canvas(*TITLE_SIZE, scale)
    u = c.u
    if english:
        title = text_image(TITLE_EN, ui_font(TITLE_EN_PX * u, semibold=True), TEXT, rtl=False)
        sub = text_image(SUBTITLE_EN, ui_font(SUBTITLE_EN_PX * u), MUTED, rtl=False)
    else:
        title = text_image(TITLE, ui_font(TITLE_PX * u, semibold=True), TEXT)
        sub = text_image(SUBTITLE, ui_font(SUBTITLE_PX * u), MUTED)
    t_box, s_box = title.getchannel("A").getbbox(), sub.getchannel("A").getbbox()
    # Latin descenders hang below the group, as the eye centres on the baseline.
    t_h, s_h = t_box[3] - t_box[1], (sub.info["baseline"] if english else s_box[3]) - s_box[1]
    gap = TITLE_ORNAMENT_GAP * u
    top = (c.H - (t_h + 2 * gap + s_h)) / 2
    c.img.alpha_composite(title, (round(c.W / 2 - title.width / 2), round(top - t_box[1])))
    ornament(c, c.W / 2, top + t_h + gap)
    c.img.alpha_composite(sub, (round(c.W / 2 - sub.width / 2), round(top + t_h + 2 * gap - s_box[1])))
    full = c.result(Image.LANCZOS)    # sharper text stems than the box filter
    out = []
    for n in range(TITLE_STEPS):
        a = ease_in_out((n + 1) / TITLE_STEPS)
        im = full.copy()
        im.putalpha(full.getchannel("A").point(lambda v: round(v * a)))
        out.append(im)
    return out


def ornament(c: Canvas, cx: float, cy: float) -> None:
    """A gold divider: a small diamond with hairlines fading out to both sides."""
    u = c.u
    layer = Image.new("RGBA", c.img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    gold = (178, 136, 62)
    for side in (-1, 1):
        n = 24
        for i in range(n):
            x0 = cx + side * (6 + 34 * i / n) * u
            x1 = cx + side * (6 + 34 * (i + 1) / n) * u
            a = round(255 * (1 - i / n) ** 1.4)
            d.rectangle((min(x0, x1), cy - 0.5 * u, max(x0, x1), cy + 0.5 * u), fill=rgba(gold, a))
    r = 2.6 * u
    d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=rgba(gold))
    c.img.alpha_composite(layer)


# ---------------------------------------------------------------- UI kit

def state_layer(base: tuple, alpha: float) -> tuple:
    """An M3 state layer: primary at `alpha` over `base`."""
    return mix(base, PRIMARY, alpha)


def caption(kind: str, hover: bool, scale: int) -> Image.Image:
    """Windows 11 caption buttons on the title bar colour, 10-unit glyphs."""
    bg = (CLOSE_HOVER if kind == "close" else CAPTION_HOVER) if hover else TITLE_BAR
    c = Canvas(*CAPTION_SIZE, scale, bg)
    color = WHITE if (hover and kind == "close") else CAPTION_GLYPH
    if kind == "close":
        c.paste(glyph(FLUENT_DISMISS, 14.3 * c.u, color), c.W / 2, c.H / 2)
    else:
        # Whole device pixels, centred by matching parity: a glyph line centred on H/2 smears over two grey rows.
        thick, length = max(1, scale // 100), 10 * scale / 100
        n = 2 * round((length - c.w % 2) / 2) + c.w % 2
        x, y = (c.w - n) // 2, (c.h - thick + 1) // 2
        c.rrect((x * SUPERSAMPLE, y * SUPERSAMPLE, (x + n) * SUPERSAMPLE, (y + thick) * SUPERSAMPLE), 0, color)
    return c.result()


def button(size: tuple, scale: int, fill: tuple, alpha: float = 1.0, line: tuple | None = None) -> Image.Image:
    """An M3 button shape (radius 8, flat) with transparent corners, so one image serves the page and
    the dialog. Text and outlined buttons keep their state layer translucent. Inno draws the label."""
    c = Canvas(*size, scale)
    box, radius = (0, 0, c.W, c.H), RADIUS * c.u
    if line:
        width = c.dev(1)
        c.ring(box, radius, width, line, None)
        box, radius = (width, width, c.W - width, c.H - width), radius - width
    if alpha:
        c.rrect(box, radius, fill, round(alpha * 255))
    return c.result()


def buttons(scale: int) -> dict[str, Image.Image]:
    out = {}
    for name in ("primary", "wide"):
        for state, color in (("n", PRIMARY), ("h", PRIMARY_HOVER), ("p", PRIMARY_PRESSED), ("d", DISABLED)):
            out[f"btn_{name}_{state}"] = button(BUTTONS[name], scale, color)
    # The app's tonal buttons take a white state layer (measured), not the M3 onSecondaryContainer one.
    tonal = (("n", TONAL), ("h", mix(TONAL, WHITE, HOVER_ALPHA)), ("p", mix(TONAL, WHITE, PRESSED_ALPHA)),
             ("d", DISABLED))
    for name in ("tonal", "tonalwide"):
        for state, color in tonal:
            out[f"btn_{name}_{state}"] = button(BUTTONS[name], scale, color)
    for state, alpha in (("n", 0), ("h", HOVER_ALPHA), ("p", PRESSED_ALPHA)):
        out[f"btn_ghost_{state}"] = button(BUTTONS["ghost"], scale, PRIMARY, alpha)
    for state, alpha, line in (("n", 0, OUTLINE), ("h", HOVER_ALPHA, OUTLINE),
                               ("p", PRESSED_ALPHA, OUTLINE), ("d", 0, DISABLED)):
        out[f"btn_outline_{state}"] = button(BUTTONS["outline"], scale, PRIMARY, alpha, line)
    return out


def cards(scale: int) -> dict[str, Image.Image]:
    """3-slice AppCards: a flat fill, no border; selection is shown by the radio and the fill. t/b caps
    and the 1-unit middle are cut from one render, so their edges line up exactly at every scale."""
    out = {}
    states = {"n": CARD, "h": state_layer(CARD, HOVER_ALPHA), "s": CARD_SEL, "sh": state_layer(CARD_SEL, HOVER_ALPHA)}
    cap, mid = px(CARD_CAP, scale), px(CARD_MID, scale)
    for state, fill in states.items():
        c = Canvas(CARD_W, CARD_CAP * 2 + 8, scale)
        body = c.H
        if CARD_SHADOW:
            body -= c.dev(CARD_SHADOW)
            shade = Image.new("L", c.img.size, 0)
            ImageDraw.Draw(shade).rounded_rectangle((0, c.dev(1), c.W - 1, body - 1 + c.dev(1)), radius=RADIUS * c.u, fill=255)
            shade = shade.filter(ImageFilter.GaussianBlur(0.9 * c.u)).point(lambda v: round(v * 0.13))
            c.img.alpha_composite(solid(shade, SHADOW))
        c.rrect((0, 0, c.W, body), RADIUS * c.u, fill)
        full = c.result()
        out[f"card_{state}_t"] = full.crop((0, 0, full.width, cap))
        out[f"card_{state}_m"] = full.crop((0, cap, full.width, cap + 1)).resize((full.width, mid), Image.NEAREST)
        out[f"card_{state}_b"] = full.crop((0, full.height - cap, full.width, full.height))
    return out


def toggles(scale: int) -> dict[str, Image.Image]:
    """Material 3 radio (20, 2-unit ring, 10-unit dot) and checkbox (18, radius 2), real alpha."""
    out = {}
    for on in (False, True):
        c = Canvas(TOGGLE_SIZE, TOGGLE_SIZE, scale)
        u, W = c.u, c.W
        color = PRIMARY if on else MUTED
        c.ring((0, 0, W, W), W / 2, round(2 * u), color, None)
        if on:
            c.ellipse((W / 2 - 5 * u, W / 2 - 5 * u, W / 2 + 5 * u, W / 2 + 5 * u), PRIMARY)
        out[f"radio_{'on' if on else 'off'}"] = c.result()

        c = Canvas(TOGGLE_SIZE, TOGGLE_SIZE, scale)
        box = (round(1 * u), round(1 * u), W - round(1 * u), W - round(1 * u))
        if on:
            c.rrect(box, 2 * u, PRIMARY)
            layer = Image.new("RGBA", c.img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            tick = [(5.4 * u, 10.2 * u), (8.4 * u, 13.2 * u), (14.6 * u, 7.0 * u)]
            stroke = 2 * u
            d.line(tick, fill=rgba(WHITE), width=round(stroke), joint="curve")
            for x, y in (tick[0], tick[-1]):
                d.ellipse((x - stroke / 2, y - stroke / 2, x + stroke / 2, y + stroke / 2), fill=rgba(WHITE))
            c.img.alpha_composite(layer)
        else:
            c.ring(box, 2 * u, round(2 * u), MUTED, None)
        out[f"check_{'on' if on else 'off'}"] = c.result()
    return out


def windows_mark(size: float, color: tuple) -> Image.Image:
    side = round(size)
    im = Image.new("RGBA", (side, side), rgba(color, 0))
    d = ImageDraw.Draw(im)
    gap = side * 0.09
    cell = (side - gap) / 2
    for i in range(2):
        for j in range(2):
            x0, y0 = i * (cell + gap), j * (cell + gap)
            d.rounded_rectangle((x0, y0, x0 + cell - 1, y0 + cell - 1), radius=side * 0.06, fill=rgba(color))
    return im


def icon_tiles(scale: int) -> dict[str, Image.Image]:
    out = {}
    for name, icon in ICONS.items():
        c = Canvas(ICON_TILE, ICON_TILE, scale)
        c.rrect((0, 0, c.W, c.H), RADIUS * c.u, TILE)
        if icon is None:
            g = windows_mark(15 * c.u, TILE_GLYPH)
        else:
            style, codepoint, design = icon
            g = glyph((style, codepoint), ICON_GLYPH * 24 / design * c.u, TILE_GLYPH)
        c.paste(g, c.W / 2, c.H / 2)
        out[f"ico_{name}"] = c.result()
    return out


def dots(scale: int) -> dict[str, Image.Image]:
    out = {}
    for name, w, color in (("on", DOT_SIZE, mix(PAGE, PRIMARY, 0.5)), ("cur", DOT_CUR_W, PRIMARY),
                           ("off", DOT_SIZE, OUTLINE_VARIANT)):
        c = Canvas(w, DOT_SIZE, scale)
        c.rrect((0, 0, c.W, c.H), c.H / 2, color)
        out[f"dot_{name}"] = c.result()
    return out


def bars(scale: int) -> dict[str, Image.Image]:
    """Progress bar 3-slices with real alpha (the fill is drawn over the track)."""
    out = {}
    cap, mid = px(BAR_CAP_W, scale), px(BAR_MID_W, scale)
    for name, color in (("track", TRACK), ("fill", PRIMARY)):
        c = Canvas(BAR_CAP_W * 2 + 2, BAR_H, scale)
        c.rrect((0, 0, c.W, c.H), c.H / 2, color)
        full = c.result()
        out[f"bar_{name}_l"] = full.crop((0, 0, cap, full.height))
        out[f"bar_{name}_m"] = full.crop((cap, 0, cap + 1, full.height)).resize((mid, full.height), Image.NEAREST)
        out[f"bar_{name}_r"] = full.crop((full.width - cap, 0, full.width, full.height))
    return out


def fields(scale: int) -> dict[str, Image.Image]:
    out = {}
    for name, line, width in (("n", OUTLINE, 1), ("f", PRIMARY, 2)):
        c = Canvas(*FIELD_SIZE, scale)
        c.ring((0, 0, c.W, c.H), RADIUS * c.u, c.dev(width), line, FIELD)
        out[f"field_{name}"] = c.result()
    return out


def badges(scale: int) -> dict[str, Image.Image]:
    """Result badges: a solid disc inside a faint ring of the same ink; offline and paused are the calm ones."""
    out = {}
    for name, ring, disc in (("ok", PRIMARY, PRIMARY), ("err", ERROR, ERROR), ("offline", MUTED, TILE), ("paused", MUTED, TILE)):
        c = Canvas(BADGE_SIZE, BADGE_SIZE, scale)
        u, W = c.u, c.W
        c.ellipse((0, 0, W, W), ring, 28)
        d = 8 * u
        c.ellipse((d, d, W - d, W - d), disc)
        if name == "ok":
            c.paste(glyph(FLUENT_CHECK, 32 * u, WHITE), W / 2, W / 2 + 0.5 * u)
        elif name == "err":
            c.rrect((round(W / 2 - 2.4 * u), round(22 * u), round(W / 2 + 2.4 * u), round(41 * u)), 2.4 * u, WHITE)
            c.ellipse((W / 2 - 2.9 * u, 45 * u, W / 2 + 2.9 * u, 50.8 * u), WHITE)
        elif name == "offline":
            c.paste(glyph(FLUENT_OFFLINE, 34 * u, MUTED), W / 2, W / 2)
        else:
            c.paste(glyph(FLUENT_PAUSE, 34 * u, MUTED), W / 2, W / 2)
        out[f"badge_{name}"] = c.result()
    return out


def marks(scale: int) -> dict[str, Image.Image]:
    return {"mark": logo_fit(px(MARK_SIZE, scale)), "logo": logo_fit(px(LOGO_SIZE, scale), 0.03)}


# ---------------------------------------------------------------- output

def assets_for(scale: int) -> dict[str, Image.Image]:
    out: dict[str, Image.Image] = {}
    if scale == BOOK_SRC_SCALE:
        for i, im in enumerate(book_frames(scale)):
            out[f"book_{i:02d}"] = im
    if scale == TITLE_SRC_SCALE:
        for i, im in enumerate(title_frames(scale)):
            out[f"title_{i}"] = im
        for i, im in enumerate(title_frames(scale, english=True)):
            out[f"title_en_{i}"] = im
    out.update(marks(scale))
    for kind in ("close", "min"):
        out[f"cap_{kind}"] = caption(kind, False, scale)
        out[f"cap_{kind}h"] = caption(kind, True, scale)
    for build in (buttons, cards, toggles, icon_tiles, dots, bars, fields, badges):
        out.update(build(scale))
    return out


def save_png(im: Image.Image, path: Path) -> None:
    # Truecolor RGBA only: Inno's VCL keeps just on/off transparency for palette PNGs.
    assert im.mode == "RGBA", f"{path.name} is {im.mode}"
    im.save(path, optimize=True)
    with open(path, "rb") as f:
        assert f.read(26)[25] == 6, f"{path.name} was not written as PNG colour type 6 (RGBA)"


BAYER = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
                  [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
                  [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                  [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]], np.float32) / 64 - 0.5


def _nearest(pixels: np.ndarray, palette: np.ndarray) -> np.ndarray:
    norms = (palette * palette).sum(1)
    out = np.empty(len(pixels), np.int64)
    for s in range(0, len(pixels), 65536):
        chunk = pixels[s:s + 65536]
        out[s:s + 65536] = np.argmin(norms[None, :] - 2 * chunk @ palette.T, axis=1)
    return out


def isi_text() -> str:
    def size(name, wh):
        return [f"#define AA_{name}_W {wh[0]}", f"#define AA_{name}_H {wh[1]}"]

    def tcolor(rgb):
        return "0x%02X%02X%02X" % (rgb[2], rgb[1], rgb[0])

    lines = [
        "; Generated by build_assistant_art.py - do not edit; change the script and regenerate.",
        f'#define AA_ART_VERSION "{ART_VERSION}"',
        f'#define AA_SCALES "{",".join(map(str, SCALES))}"',
        f"#define AA_SCALE_COUNT {len(SCALES)}",
        "; book_NN and title_N exist only at these scales; shown with Stretch at AA_BOOK_W/H, AA_TITLE_W/H",
        f"#define AA_BOOK_SRC_SCALE {BOOK_SRC_SCALE}",
        f"#define AA_TITLE_SRC_SCALE {TITLE_SRC_SCALE}",
        "; title_en_N: the English title block, same size, steps and scale as title_N",
        "#define AA_TITLE_EN 1",
        "; welcome sequence (ms, 100% units)",
        f"#define AA_BOOK_FRAMES {BOOK_FRAMES}",
        f"#define AA_BOOK_FPS {BOOK_FPS}",
        f"#define AA_BOOK_FRAME_MS {round(1000 / BOOK_FPS)}",
        f"#define AA_PAGE_FADE_MS {PAGE_FADE_MS}",
        f"#define AA_BOOK_TOP {BOOK_TOP}",
        f"#define AA_BOOK_RISE {BOOK_RISE}",
        f"#define AA_RISE_MS {RISE_MS}",
        f"#define AA_RISE_START_FRAME {RISE_START_FRAME}",
        f"#define AA_TITLE_TOP {TITLE_TOP}",
        f"#define AA_TITLE_SLIDE {TITLE_SLIDE}",
        f"#define AA_TITLE_FADE_MS {TITLE_FADE_MS}",
        f"#define AA_TITLE_STEPS {TITLE_STEPS}",
        f"#define AA_NOTE_TOP {NOTE_TOP}",
        f"#define AA_START_BUTTON_TOP {BUTTON_TOP}",
        "; asset sizes at 100%",
        f"#define AA_RADIUS {RADIUS}",
        *size("BOOK", (BOOK_SIZE, BOOK_SIZE)),
        *size("TITLE", TITLE_SIZE),
        f"#define AA_MARK_SIZE {MARK_SIZE}",
        f"#define AA_TITLE_BAR_H {CAPTION_SIZE[1]}",
        f"#define AA_LOGO_SIZE {LOGO_SIZE}",
        *size("CAP", CAPTION_SIZE),
        *(line for name, wh in BUTTONS.items() for line in size(f"BTN_{name.upper()}", wh)),
        f"#define AA_CARD_W {CARD_W}",
        f"#define AA_CARD_CAP_H {CARD_CAP}",
        f"#define AA_CARD_MID_H {CARD_MID}",
        f"#define AA_CARD_SHADOW {CARD_SHADOW}",
        f"#define AA_TOGGLE_SIZE {TOGGLE_SIZE}",
        f"#define AA_ICON_SIZE {ICON_TILE}",
        f'#define AA_ICON_NAMES "{",".join(ICONS)}"',
        f"#define AA_DOT_SIZE {DOT_SIZE}",
        f"#define AA_DOT_CUR_W {DOT_CUR_W}",
        f"#define AA_BAR_CAP_W {BAR_CAP_W}",
        f"#define AA_BAR_MID_W {BAR_MID_W}",
        f"#define AA_BAR_H {BAR_H}",
        *size("FIELD", FIELD_SIZE),
        f"#define AA_BADGE_SIZE {BADGE_SIZE}",
        "; palette as Inno TColor values (0xBBGGRR)",
    ]
    palette = {"PAGE": PAGE, "TITLE_BAR": TITLE_BAR, "TITLE_BAR_BORDER": TITLE_BAR_BORDER,
               "CAPTION_HOVER": CAPTION_HOVER, "CAPTION_GLYPH": CAPTION_GLYPH, "CARD": CARD, "CARD_SEL": CARD_SEL,
               "DIVIDER": OUTLINE_VARIANT, "OUTLINE": OUTLINE, "PRIMARY": PRIMARY, "ON_PRIMARY": ON_PRIMARY,
               "DISABLED": DISABLED, "DISABLED_TEXT": DISABLED_TEXT, "TEXT": TEXT, "MUTED": MUTED, "FAINT": FAINT,
               "TILE": TILE, "TILE_GLYPH": TILE_GLYPH, "ERROR": ERROR, "FIELD": FIELD, "ON_TONAL": ON_TONAL}
    lines += [f"#define AA_CLR_{name} {tcolor(rgb)}" for name, rgb in palette.items()]
    return "\n".join(lines) + "\n"


def write_assets(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        if old.name.startswith(ASSET_PREFIXES):
            old.unlink()
    total = count = 0
    for scale in SCALES:
        for name, im in assets_for(scale).items():
            path = out_dir / f"{name}_{scale}.png"
            save_png(im, path)
            total += path.stat().st_size
            count += 1
        print(f"  {scale}%", flush=True)
    (out_dir / "assistant_art.isi").write_text(isi_text(), encoding="ascii")
    print(f"{count} PNGs, {total / 1048576:.2f} MB -> {out_dir}")


def collect_sources(otzaria: Path) -> None:
    pub = Path(os.environ.get("PUB_CACHE") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Pub" / "Cache")
    SOURCES.mkdir(exist_ok=True)
    for name, origin in COLLECT.items():
        if isinstance(origin, tuple):
            src = (pub / "git" if origin[2:] == ("git",) else pub / "hosted" / "pub.dev") / origin[0] / origin[1]
        else:
            src = otzaria / origin
        shutil.copyfile(src, SOURCES / name)
        print(f"  {name} <- {src}")


# ---------------------------------------------------------------- preview (not shipped)

def load_art(art: Path, name: str, scale: int) -> Image.Image:
    """An asset as the assistant shows it at `scale`. The book and title are shrunk from their source
    scale like Inno's Stretch (SPLINE16 there; LANCZOS here is within ~48 dB of it, invisible in a preview)."""
    if name.startswith("book_"):
        (w, h), src = (BOOK_SIZE, BOOK_SIZE), BOOK_SRC_SCALE
    elif name.startswith("title_"):
        (w, h), src = TITLE_SIZE, TITLE_SRC_SCALE
    else:
        (w, h), src = (0, 0), scale
    im = Image.open(art / f"{name}_{src}.png").convert("RGBA")
    return im if src == scale else im.resize((px(w, scale), px(h, scale)), Image.LANCZOS)


def welcome_frames(art: Path, scale: int, english: bool = False) -> list[tuple[Image.Image, int]]:
    """The welcome sequence as the Inno code plays it, sampled at ~30 fps: (frame, duration ms).
    English is laid out left to right: caption on the left, minimize and close at the right edge."""
    k = scale / 100
    rtl = not english
    caption_text, note, start = ((TITLE_EN, PREVIEW_NOTE_EN, PREVIEW_BUTTON_EN) if english
                                 else (TITLE, PREVIEW_NOTE, PREVIEW_BUTTON))

    def load(name: str) -> Image.Image:
        return load_art(art, name, scale)

    def at(v: float) -> int:
        return round(v * k)

    win = Image.new("RGBA", (px(WINDOW[0], scale), px(WINDOW[1], scale)), rgba(PAGE))
    bar = ImageDraw.Draw(win)
    bar.rectangle((0, 0, win.width - 1, px(CAPTION_SIZE[1], scale) - 1), fill=rgba(TITLE_BAR))
    bar.rectangle((0, px(CAPTION_SIZE[1], scale), win.width - 1, px(CAPTION_SIZE[1] + 1, scale) - 1),
                  fill=rgba(TITLE_BAR_BORDER))
    # RTL: close at the left edge, minimize beside it, the caption on the right; LTR mirrors it.
    cap_w, bar_h = px(CAPTION_SIZE[0], scale), px(CAPTION_SIZE[1], scale)
    win.alpha_composite(load("cap_close"), (0 if rtl else win.width - cap_w, 0))
    win.alpha_composite(load("cap_min"), (cap_w if rtl else win.width - 2 * cap_w, 0))
    label = text_image(caption_text, ui_font(12 * k), TEXT, rtl)
    ink = label.getchannel("A").getbbox()
    win.alpha_composite(label, (win.width - at(12) - ink[2] if rtl else at(12) - ink[0],
                                round((bar_h - (ink[3] - ink[1])) / 2) - ink[1]))

    footer = Image.new("RGBA", win.size, (0, 0, 0, 0))
    for i, line in enumerate(note):
        t = text_image(line, ui_font(12 * k), MUTED, rtl)
        footer.alpha_composite(t, ((win.width - t.width) // 2, at(NOTE_TOP + 18 * i) - t.info["baseline"] + at(13)))
    button = load("btn_wide_n")
    footer.alpha_composite(button, (at(MARGIN), at(BUTTON_TOP)))
    t = text_image(start, ui_font(14 * k, True), ON_PRIMARY, rtl)
    footer.alpha_composite(t, ((win.width - t.width) // 2, at(BUTTON_TOP) + (button.height - t.height) // 2))

    books = [load(f"book_{i:02d}") for i in range(BOOK_FRAMES)]
    titles = [load(f"title_{'en_' if english else ''}{i}") for i in range(TITLE_STEPS)]
    t_book = PAGE_FADE_MS
    t_rise = t_book + RISE_START_FRAME * 1000 / BOOK_FPS
    t_title = max(t_rise + RISE_MS, t_book + BOOK_FRAMES * 1000 / BOOK_FPS)
    t_footer = t_title + TITLE_FADE_MS
    t_end = t_footer + FOOTER_FADE_MS

    def compose(ms: float) -> Image.Image:
        im = win.copy()
        if ms >= t_book:
            i = min(BOOK_FRAMES - 1, int((ms - t_book) * BOOK_FPS / 1000))
            top = BOOK_TOP - BOOK_RISE * ease_out_cubic((ms - t_rise) / RISE_MS)
            im.alpha_composite(books[i], ((im.width - books[i].width) // 2, at(top)))
        if ms >= t_title:
            p = (ms - t_title) / TITLE_FADE_MS
            n = min(TITLE_STEPS - 1, int(p * TITLE_STEPS))
            im.alpha_composite(titles[n], (at(MARGIN), at(TITLE_TOP + TITLE_SLIDE * (1 - ease_out_cubic(p)))))
        if ms >= t_footer:
            a = ease_in_out((ms - t_footer) / FOOTER_FADE_MS)
            f = footer.copy()
            f.putalpha(footer.getchannel("A").point(lambda v: round(v * a)))
            im.alpha_composite(f)
        return im.convert("RGB")

    frames, step, n = [], 1000 / 30, 0
    while n * step < t_end:
        frames.append((compose(n * step), round((n + 1) * step, -1) - round(n * step, -1)))
        n += 1
    frames.append((compose(t_end), PREVIEW_HOLD_MS))
    return frames


def save_gif(frames: list[tuple[Image.Image, int]], path: Path) -> None:
    """One palette for all frames and ordered dithering, so the static page never shimmers."""
    sample = np.vstack([np.asarray(f, np.float32).reshape(-1, 3)[::7] for f, _ in frames[::3]])
    seed = Image.fromarray(sample[None].astype(np.uint8), "RGB").quantize(256, method=Image.Quantize.MEDIANCUT)
    pal = np.asarray(seed.getpalette("RGB"), np.float32).reshape(-1, 3)[:256]
    picks = sample[np.random.default_rng(2).choice(len(sample), min(len(sample), 80000), replace=False)]
    for _ in range(6):
        idx = _nearest(picks, pal)
        counts = np.bincount(idx, minlength=len(pal))
        for ch in range(3):
            sums = np.bincount(idx, weights=picks[:, ch], minlength=len(pal))
            pal[:, ch] = np.where(counts > 0, sums / np.maximum(counts, 1), pal[:, ch])
    flat = np.clip(np.round(pal), 0, 255).astype(np.uint8).tobytes()
    images = []
    for f, _ in frames:
        a = np.asarray(f, np.float32)
        h, w = a.shape[:2]
        noise = np.tile(BAYER, (h // 8 + 1, w // 8 + 1))[:h, :w].reshape(-1, 1) * 3.0
        idx = _nearest(np.clip(a.reshape(-1, 3) + noise, 0, 255), pal)
        im = Image.fromarray(idx.reshape(h, w).astype(np.uint8), "P")
        im.putpalette(flat)
        images.append(im)
    images[0].save(path, save_all=True, append_images=images[1:], duration=[d for _, d in frames],
                   loop=0, optimize=False, disposal=1)


def contact_sheet(art: Path, path: Path, scale: int = 200) -> None:
    """Every asset at `scale` on the page colour, labelled."""
    label_font = ui_font(22)
    width, gap = 2700, 36
    items: list[tuple[str, Image.Image]] = []

    def load(name: str) -> Image.Image:
        return load_art(art, name, scale)

    for i in range(BOOK_FRAMES):
        items.append((f"book_{i:02d}", load(f"book_{i:02d}")))
    for prefix in ("title_", "title_en_"):
        for i in range(TITLE_STEPS):
            items.append((f"{prefix}{i}", load(f"{prefix}{i}")))
    for name in ("mark", "logo", "cap_close", "cap_closeh", "cap_min", "cap_minh"):
        items.append((name, load(name)))
    for kind, states in (("primary", "nhpd"), ("wide", "nhpd"), ("ghost", "nhp"), ("outline", "nhpd"),
                         ("tonal", "nhpd"), ("tonalwide", "nhpd")):
        for s in states:
            items.append((f"btn_{kind}_{s}", load(f"btn_{kind}_{s}")))
    for s in ("n", "h", "s", "sh"):
        t, m, b = load(f"card_{s}_t"), load(f"card_{s}_m"), load(f"card_{s}_b")
        body = px(40, scale)
        card = Image.new("RGBA", (t.width, t.height + body + b.height))
        card.alpha_composite(t, (0, 0))
        for y in range(t.height, t.height + body, m.height):
            card.alpha_composite(m, (0, y))
        card.alpha_composite(b, (0, t.height + body))
        tile, radio = load("ico_this_pc"), load("radio_on" if "s" in s else "radio_off")
        card.alpha_composite(radio, (card.width - px(16, scale) - radio.width, (card.height - radio.height) // 2))
        card.alpha_composite(tile, (card.width - px(48, scale) - tile.width, (card.height - tile.height) // 2))
        items.append((f"card_{s} (t + m x{body // m.height} + b)", card))
    for name in ("radio_off", "radio_on", "check_off", "check_on"):
        items.append((name, load(name)))
    for name in ICONS:
        items.append((f"ico_{name}", load(f"ico_{name}")))
    for name in ("dot_on", "dot_cur", "dot_off"):
        items.append((name, load(name)))
    bar = Image.new("RGBA", (px(352, scale), px(BAR_H, scale)))
    for part, length in (("track", 352), ("fill", 150)):
        l, m, r = load(f"bar_{part}_l"), load(f"bar_{part}_m"), load(f"bar_{part}_r")
        bar.alpha_composite(l, (0, 0))
        for x in range(l.width, px(length, scale) - r.width, m.width):
            bar.alpha_composite(m, (x, 0))
        bar.alpha_composite(r, (px(length, scale) - r.width, 0))
    items.append(("bar (track + fill 3-slices)", bar))
    for name in ("field_n", "field_f", "badge_ok", "badge_err", "badge_offline", "badge_paused"):
        items.append((name, load(name)))

    def cell(item: tuple[str, Image.Image]) -> int:
        return max(item[1].width, round(label_font.getlength(item[0])) + 12)

    rows: list[list[tuple[str, Image.Image]]] = [[]]
    x = gap
    for item in items:
        if x + cell(item) + gap > width and rows[-1]:
            rows.append([])
            x = gap
        rows[-1].append(item)
        x += cell(item) + gap
    height = gap + sum(max(im.height for _, im in row) + 40 + gap for row in rows)
    sheet = Image.new("RGBA", (width, height), rgba(PAGE))
    d = ImageDraw.Draw(sheet)
    y = gap
    for row in rows:
        x = gap
        tallest = max(im.height for _, im in row)
        for name, im in row:
            sheet.alpha_composite(im, (x, y))
            d.text((x, y + tallest + 8), name, font=label_font, fill=rgba(FAINT))
            x += cell((name, im)) + gap
        y += tallest + 40 + gap
    sheet.convert("RGB").save(path, optimize=True)


def write_preview(art: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for scale, name, english in ((100, "welcome.gif", False), (200, "welcome@2x.gif", False),
                                 (100, "welcome_en.gif", True), (200, "welcome_en@2x.gif", True)):
        save_gif(welcome_frames(art, scale, english), out_dir / name)
    contact_sheet(art, out_dir / "contact_sheet.png")
    print(f"preview -> {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE / "out", help="output folder for the PNGs and the .isi")
    ap.add_argument("--preview", type=Path, nargs="?", const=HERE / "preview", help="also write GIFs and a contact sheet")
    ap.add_argument("--collect-sources", action="store_true", help="copy the inputs into sources/ and exit")
    ap.add_argument("--otzaria", type=Path, default=HERE.parent.parent / "otzaria", help="Otzaria checkout for --collect-sources")
    args = ap.parse_args()
    if args.collect_sources:
        collect_sources(args.otzaria)
        return
    write_assets(args.out.resolve())
    if args.preview:
        write_preview(args.out.resolve(), args.preview.resolve())


if __name__ == "__main__":
    main()
