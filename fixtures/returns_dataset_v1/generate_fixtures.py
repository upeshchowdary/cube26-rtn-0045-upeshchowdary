"""Generate synthetic returns-manager test fixtures (dev/testing only, never eval data).

Every image is a flat-icon style rendering, not a photograph, and carries a visible
"SYNTHETIC TEST FIXTURE" watermark plus unit/SKU/state captions so it can never be
mistaken for real product evidence (see F-008, which documents why a prior batch of
unlabeled placeholder images had to be removed). Re-run this script to regenerate the
image set deterministically; nothing here is hand-drawn or sourced from the web.

Usage: python3 generate_fixtures.py
"""

from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_DIR = Path(__file__).parent / "images"
W, H = 900, 700
BG = (245, 245, 240)
INK = (30, 30, 35)
RED = (176, 30, 30)
GREEN = (40, 120, 60)
STEEL = (150, 156, 163)
YELLOW = (235, 190, 60)
BLUE = (60, 90, 150)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_TITLE = _font(26)
FONT_LABEL = _font(18)
FONT_WATERMARK = _font(15)


def new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.new = ImageDraw.Draw(img)
    return img, draw


def watermark(draw: ImageDraw.ImageDraw) -> None:
    text = "SYNTHETIC TEST FIXTURE — NOT REAL PRODUCT EVIDENCE"
    for y in range(40, H, 90):
        for x in range(-100, W, 340):
            draw.text((x, y), text, font=FONT_WATERMARK, fill=(210, 210, 205))


def header(draw: ImageDraw.ImageDraw, unit_id: str, sku: str, state_label: str, state_color) -> None:
    draw.rectangle([0, 0, W, 64], fill=(20, 22, 26))
    draw.text((20, 10), f"{unit_id}  ·  {sku}", font=FONT_TITLE, fill=(255, 255, 255))
    draw.rectangle([W - 260, 12, W - 20, 52], outline=state_color, width=3)
    draw.text((W - 245, 20), state_label, font=FONT_LABEL, fill=state_color)


def missing_slot(draw: ImageDraw.ImageDraw, box, label: str) -> None:
    x0, y0, x1, y1 = box
    for x in range(x0, x1, 14):
        draw.line([(x, y0), (min(x + 7, x1), y0)], fill=RED, width=2)
        draw.line([(x, y1), (min(x + 7, x1), y1)], fill=RED, width=2)
    for y in range(y0, y1, 14):
        draw.line([(x0, y), (x0, min(y + 7, y1))], fill=RED, width=2)
        draw.line([(x1, y), (x1, min(y + 7, y1))], fill=RED, width=2)
    draw.text((x0 + 6, (y0 + y1) // 2 - 10), f"MISSING: {label}", font=FONT_LABEL, fill=RED)


def draw_lamp(draw: ImageDraw.ImageDraw, cx: int, cy: int, damaged: bool = False) -> None:
    draw.ellipse([cx - 70, cy + 60, cx + 70, cy + 100], fill=(40, 40, 45))
    draw.rectangle([cx - 8, cy - 120, cx + 8, cy + 70], fill=(60, 60, 65))
    draw.ellipse([cx - 45, cy - 165, cx + 45, cy - 85], fill=YELLOW, outline=(120, 90, 20), width=3)
    draw.ellipse([cx - 10, cy - 70, cx + 10, cy - 50], fill=(90, 90, 95))
    draw.text((cx - 60, cy - 30), "touch switch", font=FONT_LABEL, fill=INK)
    if damaged:
        draw.line([(cx - 35, cy - 150), (cx + 10, cy - 100), (cx - 15, cy - 90)], fill=RED, width=4)
        draw.text((cx - 55, cy - 195), "cracked shade", font=FONT_LABEL, fill=RED)


def draw_cable(draw: ImageDraw.ImageDraw, x0: int, y: int, braided: bool = False, length: int = 260) -> None:
    pts = [(x0 + i, y + int(18 * math.sin(i / 22))) for i in range(0, length, 6)]
    draw.line(pts, fill=(45, 45, 50) if not braided else STEEL, width=8, joint="curve")
    draw.rectangle([x0 - 14, y - 14, x0 + 14, y + 14], fill=(70, 70, 75))
    draw.rectangle([x0 + length - 14, y - 14, x0 + length + 14, y + 14], fill=(70, 70, 75))
    if braided:
        for i in range(0, length, 18):
            draw.line([(x0 + i, y - 10), (x0 + i + 10, y + 10)], fill=(90, 96, 103), width=2)
        draw.rectangle([x0 + length // 2 - 10, y + 16, x0 + length // 2 + 10, y + 30], fill=(35, 120, 200))
        draw.text((x0 + length // 2 - 30, y + 34), "velcro tie", font=FONT_LABEL, fill=INK)


def draw_manual(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.rectangle([x, y, x + 90, y + 120], fill=(255, 255, 255), outline=INK, width=2)
    draw.polygon([(x + 70, y), (x + 90, y), (x + 90, y + 20)], fill=(225, 225, 220))
    for i in range(6):
        draw.line([(x + 12, y + 20 + i * 14), (x + 78, y + 20 + i * 14)], fill=(180, 180, 180), width=3)
    draw.text((x + 10, y + 128), "manual", font=FONT_LABEL, fill=INK)


def draw_bottle(draw: ImageDraw.ImageDraw, cx: int, cy: int, damaged: bool = False) -> None:
    draw.rounded_rectangle([cx - 55, cy - 140, cx + 55, cy + 180], radius=26, fill=STEEL, outline=(90, 96, 103), width=3)
    draw.rectangle([cx - 30, cy - 190, cx + 30, cy - 140], fill=(90, 96, 103))
    draw.arc([cx - 20, cy - 220, cx + 20, cy - 190], 200, 340, fill=(60, 60, 65), width=6)
    draw.text((cx - 55, cy + 190), "insulated bottle 750ml", font=FONT_LABEL, fill=INK)
    if damaged:
        draw.polygon([(cx - 30, cy - 20), (cx - 5, cy + 10), (cx - 20, cy + 30), (cx + 5, cy + 55)], outline=RED, width=4)
        draw.ellipse([cx + 15, cy - 60, cx + 45, cy - 30], outline=RED, width=4)
        draw.text((cx - 55, cy + 215), "dent + crack observed", font=FONT_LABEL, fill=RED)


def draw_puzzle_box(draw: ImageDraw.ImageDraw, x: int, y: int, opened: bool, pieces_present: int) -> None:
    draw.rectangle([x, y, x + 220, y + 160], fill=(255, 255, 255), outline=INK, width=3)
    draw.rectangle([x + 10, y + 10, x + 210, y + 110], fill=(80, 130, 170))
    draw.polygon([(x + 10, y + 110), (x + 90, y + 60), (x + 140, y + 90), (x + 210, y + 40), (x + 210, y + 110)], fill=(60, 110, 70))
    draw.text((x + 10, y + 120), "500-Piece Art Jigsaw", font=FONT_LABEL, fill=INK)
    if opened:
        draw.line([(x, y), (x + 220, y)], fill=RED, width=3)
        draw.text((x + 40, y - 26), "box opened / reglued", font=FONT_LABEL, fill=RED)
        random.seed(42)
        for i in range(pieces_present):
            px = x + 20 + (i % 10) * 20
            py = y + 190 + (i // 10) * 20
            draw.rectangle([px, py, px + 14, py + 14], fill=(80, 130, 170), outline=INK)
        draw.text((x, y + 190 + ((pieces_present // 10) + 1) * 20 + 6),
                   f"pieces visible in photo: ~{pieces_present} of 500", font=FONT_LABEL, fill=INK)


def draw_poster(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.rectangle([x, y, x + 90, y + 60], fill=(250, 250, 245), outline=INK, width=2)
    draw.rectangle([x + 6, y + 6, x + 84, y + 40], fill=(80, 130, 170))
    draw.text((x, y + 66), "poster", font=FONT_LABEL, fill=INK)


def apply_capture_degradation(img: Image.Image, blur: bool = False, dark: bool = False, crop: bool = False) -> Image.Image:
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=6))
    if dark:
        px = img.load()
        for yy in range(H):
            for xx in range(0, W, 2):
                r, g, b = px[xx, yy]
                px[xx, yy] = (r // 3, g // 3, b // 3)
    if crop:
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, W, 130], fill=(5, 5, 5))
        draw.rectangle([W - 220, 0, W, H], fill=(5, 5, 5))
        draw.text((20, 40), "operator photo cropped the item's left edge", font=FONT_LABEL, fill=(200, 60, 60))
    return img


@dataclass
class Unit:
    unit_id: str
    sku: str
    asin: str
    order_id: str
    org_id: str
    parts_list: list[str]
    identity_match: str
    parts_missing: list[str]
    observed_state: str
    disposition_hint: str
    scenario: str
    before_file: str
    after_files: list[str] = field(default_factory=list)
    notes: str = ""


UNITS: list[Unit] = []


def save(img: Image.Image, name: str) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    img.save(path, quality=90)
    return f"fixtures/returns_dataset_v1/images/{name}"


def build_lamp_before() -> str:
    img, draw = new_canvas()
    header(draw, "REFERENCE", "SKU-LAMP-LED", "AS SOLD (CATALOGUE)", GREEN)
    draw_lamp(draw, W // 2 - 120, 400)
    draw_cable(draw, W // 2 + 30, 380, braided=False)
    draw_manual(draw, W // 2 + 30, 460)
    watermark(draw)
    return save(img, "lamp_before_reference.jpg")


def build_unit_001() -> None:
    before = build_lamp_before()
    img, draw = new_canvas()
    header(draw, "TEST-UNIT-001", "SKU-LAMP-LED", "AS RETURNED", BLUE)
    draw_lamp(draw, W // 2 - 120, 400)
    draw_cable(draw, W // 2 + 30, 380, braided=False)
    draw_manual(draw, W // 2 + 30, 460)
    watermark(draw)
    after = save(img, "unit001_after_01.jpg")
    UNITS.append(Unit(
        unit_id="TEST-UNIT-001", sku="SKU-LAMP-LED", asin="B0DUMMY357",
        order_id="TEST-ORD-001", org_id="org_demo_alpha",
        parts_list=["lamp", "usb_cable", "manual"],
        identity_match="yes", parts_missing=[], observed_state="opened_unused",
        disposition_hint="restock (all parts present, no damage observed in the provided photos)",
        scenario="Clean return: all listed components present, no visible damage.",
        before_file=before, after_files=[after],
    ))


def build_unit_002() -> None:
    before = build_lamp_before()
    img, draw = new_canvas()
    header(draw, "TEST-UNIT-002", "SKU-LAMP-LED", "AS RETURNED", BLUE)
    draw_lamp(draw, W // 2 - 120, 400)
    draw_manual(draw, W // 2 + 30, 460)
    missing_slot(draw, (W // 2 + 10, 340, W // 2 + 300, 400), "usb_cable")
    watermark(draw)
    after = save(img, "unit002_after_01.jpg")
    UNITS.append(Unit(
        unit_id="TEST-UNIT-002", sku="SKU-LAMP-LED", asin="B0DUMMY357",
        order_id="TEST-ORD-002", org_id="org_demo_alpha",
        parts_list=["lamp", "usb_cable", "manual"],
        identity_match="yes", parts_missing=["usb_cable"], observed_state="signs_of_use",
        disposition_hint="refurbish candidate (essential-but-replaceable part missing; see disposition engine R09/R10, F-012)",
        scenario="Lamp and manual present; the USB-C charging cable is absent from the returned parcel.",
        before_file=before, after_files=[after],
    ))


def build_unit_003() -> None:
    img, draw = new_canvas()
    header(draw, "REFERENCE", "SKU-PUZZLE-500", "AS SOLD (CATALOGUE)", GREEN)
    draw_puzzle_box(draw, W // 2 - 260, 260, opened=False, pieces_present=0)
    draw_poster(draw, W // 2 + 40, 300)
    watermark(draw)
    before = save(img, "puzzle_before_reference.jpg")

    img, draw = new_canvas()
    header(draw, "TEST-UNIT-003", "SKU-PUZZLE-500", "AS RETURNED", BLUE)
    draw_puzzle_box(draw, W // 2 - 260, 220, opened=True, pieces_present=27)
    draw_poster(draw, W // 2 + 40, 300)
    draw.text((60, 600), "operator note: bag of pieces feels far lighter than a full 500-piece set", font=FONT_LABEL, fill=INK)
    watermark(draw)
    after = save(img, "unit003_after_01.jpg")
    UNITS.append(Unit(
        unit_id="TEST-UNIT-003", sku="SKU-PUZZLE-500", asin="B0DUMMY729",
        order_id="TEST-ORD-003", org_id="org_demo_alpha",
        parts_list=["puzzle_pieces (x500)", "poster"],
        identity_match="yes", parts_missing=["puzzle_pieces (partial: visible count far below 500)"],
        observed_state="signs_of_use",
        disposition_hint="liquidate/dispose candidate (essential, non-replaceable component short; puzzle_pieces.replaceable=false in the product card)",
        scenario="Box reopened, poster present, but the piece bag visibly holds far fewer than 500 pieces.",
        before_file=before, after_files=[after],
    ))


def build_unit_004() -> None:
    img, draw = new_canvas()
    header(draw, "REFERENCE", "SKU-BOTTLE-750", "AS SOLD (CATALOGUE)", GREEN)
    draw_bottle(draw, W // 2, 380, damaged=False)
    watermark(draw)
    before = save(img, "bottle_before_reference.jpg")

    img, draw = new_canvas()
    header(draw, "TEST-UNIT-004", "SKU-BOTTLE-750", "AS RETURNED", BLUE)
    draw_bottle(draw, W // 2, 380, damaged=True)
    watermark(draw)
    after = save(img, "unit004_after_01.jpg")
    UNITS.append(Unit(
        unit_id="TEST-UNIT-004", sku="SKU-BOTTLE-750", asin="B0DUMMY622",
        order_id="TEST-ORD-004", org_id="org_demo_alpha",
        parts_list=["bottle", "lid"],
        identity_match="yes", parts_missing=[], observed_state="damaged",
        disposition_hint="dispose/liquidate candidate (structural damage to an essential, non-replaceable component)",
        scenario="Bottle and lid both present, but the body shows a visible dent and crack.",
        before_file=before, after_files=[after],
    ))


def build_unit_005() -> None:
    img, draw = new_canvas()
    header(draw, "REFERENCE", "SKU-CABLE-USBC", "AS SOLD (CATALOGUE)", GREEN)
    draw_cable(draw, W // 2 - 130, 380, braided=True, length=280)
    watermark(draw)
    before = save(img, "cable_before_reference.jpg")

    img, draw = new_canvas()
    header(draw, "TEST-UNIT-005", "SKU-CABLE-USBC", "AS RETURNED", RED)
    draw.text((60, 120), "outer packaging: 'Braided USB-C Cable 2m'", font=FONT_LABEL, fill=INK)
    draw_lamp(draw, W // 2 - 40, 420)
    draw.text((60, 600), "box contents do not match the box label — possible product swap, requires review", font=FONT_LABEL, fill=RED)
    watermark(draw)
    after = save(img, "unit005_after_01.jpg")
    UNITS.append(Unit(
        unit_id="TEST-UNIT-005", sku="SKU-CABLE-USBC", asin="B0DUMMY261",
        order_id="TEST-ORD-005", org_id="org_demo_alpha",
        parts_list=["cable"],
        identity_match="no", parts_missing=["cable (not present; different item found)"],
        observed_state="uncertain",
        disposition_hint="pending_review (identity mismatch — possible product swap, requires human review; never auto-dispositioned)",
        scenario="Outer packaging is labelled as the USB-C cable, but the item inside is a different product (box-swap / C06 defense test).",
        before_file=before, after_files=[after],
        notes="Deliberately triggers the identity check's box-swap defense (F-013).",
    ))


def build_unit_006() -> None:
    before = "fixtures/returns_dataset_v1/images/bottle_before_reference.jpg"

    img, draw = new_canvas()
    header(draw, "TEST-UNIT-006", "SKU-BOTTLE-750", "AS RETURNED (POOR EVIDENCE)", RED)
    draw_bottle(draw, W // 2, 380, damaged=False)
    watermark(draw)
    img = apply_capture_degradation(img, blur=True, dark=True, crop=True)
    after = save(img, "unit006_after_01.jpg")
    UNITS.append(Unit(
        unit_id="TEST-UNIT-006", sku="SKU-BOTTLE-750", asin="B0DUMMY622",
        order_id="TEST-ORD-006", org_id="org_demo_alpha",
        parts_list=["bottle", "lid"],
        identity_match="uncertain", parts_missing=[], observed_state="uncertain",
        disposition_hint="pending_review (evidence insufficient for a reliable judgment — UNCERTAIN is the required outcome, not a forced pass or fail)",
        scenario="Single photo is dark, out of focus and cropped at the edges; the lid is not clearly visible.",
        before_file=before, after_files=[after],
        notes="Purpose-built to test that the pipeline emits UNCERTAIN instead of guessing.",
    ))


def write_manifest() -> None:
    manifest_dir = Path(__file__).parent
    csv_path = manifest_dir / "manifest.csv"
    json_path = manifest_dir / "manifest.json"

    fieldnames = [
        "unit_id", "org_id", "order_id", "ordered_sku", "ordered_asin",
        "before_image", "after_images", "expected_identity_match",
        "expected_parts_list", "expected_parts_missing", "expected_observed_state",
        "expected_amazon_condition", "expected_disposition_hint", "scenario", "notes",
    ]
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for u in UNITS:
            writer.writerow({
                "unit_id": u.unit_id,
                "org_id": u.org_id,
                "order_id": u.order_id,
                "ordered_sku": u.sku,
                "ordered_asin": u.asin,
                "before_image": u.before_file,
                "after_images": ";".join(u.after_files),
                "expected_identity_match": u.identity_match,
                "expected_parts_list": ";".join(u.parts_list),
                "expected_parts_missing": ";".join(u.parts_missing),
                "expected_observed_state": u.observed_state,
                "expected_amazon_condition": "",
                "expected_disposition_hint": u.disposition_hint,
                "scenario": u.scenario,
                "notes": u.notes,
            })

    with json_path.open("w") as fh:
        json.dump([u.__dict__ for u in UNITS], fh, indent=2)

    print(f"Wrote {csv_path} and {json_path} ({len(UNITS)} units)")


def main() -> None:
    build_unit_001()
    build_unit_002()
    build_unit_003()
    build_unit_004()
    build_unit_005()
    build_unit_006()
    write_manifest()


if __name__ == "__main__":
    main()
