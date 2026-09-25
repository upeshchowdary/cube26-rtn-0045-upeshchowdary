"""Generate Product Knowledge Cards and orders seed data for dev/sample SKUs (§8.2, §8.9)."""

from __future__ import annotations

import base64
import csv
import hashlib
from pathlib import Path
from typing import Any

import yaml

from returns_manager.config import REPO_ROOT
from returns_manager.reference.hashing import compute_reference_content_sha256
from returns_manager.reference.models import ProductCardV1

REF_DIR = REPO_ROOT / "reference"
PRODUCTS_DIR = REF_DIR / "products"

# Minimal valid 1x1 JPEG in base64
_TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP///////////////////////////////////"
    "///////////////////////////////////////////////////wgALCAABAAEBAREA"
    "/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)


def make_dummy_jpeg(seed: int) -> tuple[bytes, str]:
    # Modify one byte deterministically based on seed to produce unique hashes
    raw = bytearray(base64.b64decode(_TINY_JPEG_B64))
    raw[10] = (raw[10] + seed) % 256
    data = bytes(raw)
    return data, hashlib.sha256(data).hexdigest()


SKU_SPECS: dict[str, dict[str, Any]] = {
    "SKU-LAMP-LED": {
        "asin": "B0DUMMY357",
        "title": "LED desk lamp with USB cable",
        "brand": "LuminaTech",
        "category_key": "electronics",
        "df": [
            {
                "id": "df_base_shape",
                "description": "Round weighted base, ~12 cm, matte black",
                "location": "product_body",
                "importance": "critical",
            },
            {
                "id": "df_switch",
                "description": "Touch switch on the arm, not a push button",
                "location": "product_body",
                "importance": "critical",
            },
        ],
        "similar": [{"sku": "SKU-LAMP-LED-V2", "differs_by": ["push button switch", "white base"]}],
        "components": [
            {
                "id": "lamp",
                "name": "lamp",
                "quantity": 1,
                "essential": True,
                "replaceable": False,
                "verifiable_by_photo": True,
                "visual_cues": "The lamp body with arm and base",
                "source": {"type": "seller_catalogue", "ref": "cat row 14"},
            },
            {
                "id": "usb_cable",
                "name": "usb cable",
                "quantity": 1,
                "essential": True,
                "replaceable": True,
                "verifiable_by_photo": True,
                "visual_cues": "Black USB-A to USB-C cable, ~1 m",
                "source": {"type": "seller_catalogue", "ref": "cat row 14"},
            },
            {
                "id": "manual",
                "name": "manual",
                "quantity": 1,
                "essential": False,
                "replaceable": True,
                "verifiable_by_photo": True,
                "visual_cues": "Folded A5 leaflet",
                "source": {"type": "seller_catalogue", "ref": "cat row 14"},
            },
        ],
        "list_price": 199900,
        "refurbish_cost": 30000,
    },
    "SKU-PUZZLE-500": {
        "asin": "B0DUMMY729",
        "title": "500-Piece Art Jigsaw Puzzle",
        "brand": "BrainCraft",
        "category_key": "toys_games",
        "df": [
            {
                "id": "df_box_art",
                "description": "Landscape painting cover art with glossy finish",
                "location": "packaging",
                "importance": "critical",
            },
        ],
        "similar": [],
        "components": [
            {
                "id": "puzzle_pieces",
                "name": "puzzle pieces",
                "quantity": 500,
                "essential": True,
                "replaceable": False,
                "verifiable_by_photo": False,
                "visual_cues": "500 cardboard jigsaw pieces in plastic bag",
                "source": {"type": "seller_catalogue", "ref": "cat row 22"},
            },
            {
                "id": "poster",
                "name": "poster",
                "quantity": 1,
                "essential": False,
                "replaceable": True,
                "verifiable_by_photo": True,
                "visual_cues": "Full color reference poster A4 size",
                "source": {"type": "seller_catalogue", "ref": "cat row 22"},
            },
        ],
        "list_price": 89900,
        "refurbish_cost": 15000,
    },
    "SKU-TOWEL-BLU": {
        "asin": "B0DUMMY600",
        "title": "Premium Cotton Bath Towel Blue",
        "brand": "ComfortSoft",
        "category_key": "home_kitchen",
        "df": [
            {
                "id": "df_border_pattern",
                "description": "Woven ribbed border on short edges",
                "location": "product_body",
                "importance": "critical",
            },
        ],
        "similar": [],
        "components": [
            {
                "id": "towel",
                "name": "towel",
                "quantity": 1,
                "essential": True,
                "replaceable": False,
                "verifiable_by_photo": True,
                "visual_cues": "Navy blue 70x140cm cotton bath towel",
                "source": {"type": "seller_catalogue", "ref": "cat row 30"},
            },
        ],
        "list_price": 69900,
        "refurbish_cost": 10000,
    },
    "SKU-BOTTLE-750": {
        "asin": "B0DUMMY622",
        "title": "750ml Insulated Stainless Steel Water Bottle",
        "brand": "HydroPeak",
        "category_key": "home_kitchen",
        "df": [
            {
                "id": "df_lid_handle",
                "description": "Integrated carry loop on screw cap",
                "location": "accessory",
                "importance": "critical",
            },
        ],
        "similar": [],
        "components": [
            {
                "id": "bottle",
                "name": "bottle",
                "quantity": 1,
                "essential": True,
                "replaceable": False,
                "verifiable_by_photo": True,
                "visual_cues": "Stainless steel double-walled 750ml flask",
                "source": {"type": "seller_catalogue", "ref": "cat row 45"},
            },
            {
                "id": "lid",
                "name": "lid",
                "quantity": 1,
                "essential": True,
                "replaceable": True,
                "verifiable_by_photo": True,
                "visual_cues": "Threaded leakproof lid with silicone seal",
                "source": {"type": "seller_catalogue", "ref": "cat row 45"},
            },
        ],
        "list_price": 129900,
        "refurbish_cost": 20000,
    },
    "SKU-SERUM-30": {
        "asin": "B0DUMMY031",
        "title": "Vitamin C Facial Radiance Serum 30ml",
        "brand": "DermaPure",
        "category_key": "beauty_topical",
        "df": [
            {
                "id": "df_amber_bottle",
                "description": "Amber UV-protective glass bottle with calibrated pipette",
                "location": "product_body",
                "importance": "critical",
            },
        ],
        "similar": [],
        "components": [
            {
                "id": "bottle",
                "name": "bottle",
                "quantity": 1,
                "essential": True,
                "replaceable": False,
                "verifiable_by_photo": True,
                "visual_cues": "30ml amber glass dropper bottle",
                "source": {"type": "seller_catalogue", "ref": "cat row 50"},
            },
            {
                "id": "dropper",
                "name": "dropper",
                "quantity": 1,
                "essential": True,
                "replaceable": True,
                "verifiable_by_photo": True,
                "visual_cues": "Glass pipette dropper cap",
                "source": {"type": "seller_catalogue", "ref": "cat row 50"},
            },
            {
                "id": "leaflet",
                "name": "leaflet",
                "quantity": 1,
                "essential": False,
                "replaceable": True,
                "verifiable_by_photo": True,
                "visual_cues": "Information and usage leaflet",
                "source": {"type": "seller_catalogue", "ref": "cat row 50"},
            },
        ],
        "list_price": 149900,
        "refurbish_cost": 0,
    },
    "SKU-PROT-1KG": {
        "asin": "B0DUMMY357",  # Note: finding F-004 ASIN collision with SKU-LAMP-LED
        "title": "Whey Protein Isolate Powder 1kg Chocolate",
        "brand": "NutriFit",
        "category_key": "grocery_ingestible",
        "df": [
            {
                "id": "df_safety_seal",
                "description": "Tamper-evident heat induction neck seal",
                "location": "packaging",
                "importance": "critical",
            },
        ],
        "similar": [],
        "components": [
            {
                "id": "tub",
                "name": "tub",
                "quantity": 1,
                "essential": True,
                "replaceable": False,
                "verifiable_by_photo": True,
                "visual_cues": "1kg black plastic tub with screw lid",
                "source": {"type": "seller_catalogue", "ref": "cat row 60"},
            },
            {
                "id": "scoop",
                "name": "scoop",
                "quantity": 1,
                "essential": False,
                "replaceable": True,
                "verifiable_by_photo": True,
                "visual_cues": "30g clear plastic measuring scoop",
                "source": {"type": "seller_catalogue", "ref": "cat row 60"},
            },
        ],
        "list_price": 249900,
        "refurbish_cost": 0,
    },
    "SKU-LEASH-6FT": {
        "asin": "B0DUMMY205",
        "title": "Heavy Duty 6ft Padded Dog Leash",
        "brand": "PawsActive",
        "category_key": "pet",
        "df": [
            {
                "id": "df_padded_handle",
                "description": "Neoprene padded grip handle with reflective stitching",
                "location": "product_body",
                "importance": "critical",
            },
        ],
        "similar": [],
        "components": [
            {
                "id": "leash",
                "name": "leash",
                "quantity": 1,
                "essential": True,
                "replaceable": False,
                "verifiable_by_photo": True,
                "visual_cues": "Nylon braided 6ft leash with zinc alloy carabiner",
                "source": {"type": "seller_catalogue", "ref": "cat row 70"},
            },
        ],
        "list_price": 79900,
        "refurbish_cost": 0,
    },
    "SKU-CANDLE-3": {
        "asin": "B0DUMMY964",
        "title": "Aromatherapy Scented Candle Gift Set of 3",
        "brand": "AromaHaven",
        "category_key": "home_kitchen",
        "df": [
            {
                "id": "df_glass_jars",
                "description": "Frosted glass jars with bamboo lids",
                "location": "product_body",
                "importance": "critical",
            },
        ],
        "similar": [],
        "components": [
            {
                "id": "candle",
                "name": "candle",
                "quantity": 3,
                "essential": True,
                "replaceable": False,
                "verifiable_by_photo": True,
                "visual_cues": "Three 100g soy wax candles in frosted jars",
                "source": {"type": "seller_catalogue", "ref": "cat row 80"},
            },
            {
                "id": "gift_box",
                "name": "gift box",
                "quantity": 1,
                "essential": False,
                "replaceable": True,
                "verifiable_by_photo": True,
                "visual_cues": "Magnetic closure branded gift box",
                "source": {"type": "seller_catalogue", "ref": "cat row 80"},
            },
        ],
        "list_price": 119900,
        "refurbish_cost": 0,
    },
    "SKU-MUG-11": {
        "asin": "B0DUMMY351",
        "title": "Ceramic Coffee Mug 11oz Set of 2",
        "brand": "DailyBrew",
        "category_key": "home_kitchen",
        "df": [
            {
                "id": "df_matte_glaze",
                "description": "Matte dual-tone glaze with ergonomic handle",
                "location": "product_body",
                "importance": "critical",
            },
        ],
        "similar": [],
        "components": [
            {
                "id": "mug",
                "name": "mug",
                "quantity": 2,
                "essential": True,
                "replaceable": False,
                "verifiable_by_photo": True,
                "visual_cues": "Two 11oz ceramic mugs with protective dividers",
                "source": {"type": "seller_catalogue", "ref": "cat row 90"},
            },
        ],
        "list_price": 59900,
        "refurbish_cost": 0,
    },
    "SKU-CABLE-USBC": {
        "asin": "B0DUMMY261",
        "title": "Braided USB-C to USB-C Fast Charging Cable 2m",
        "brand": "LuminaTech",
        "category_key": "electronics",
        "df": [
            {
                "id": "df_braided_jacket",
                "description": "Grey nylon braided cable with aluminium connector shells",
                "location": "product_body",
                "importance": "critical",
            },
        ],
        "similar": [],
        "components": [
            {
                "id": "cable",
                "name": "cable",
                "quantity": 1,
                "essential": True,
                "replaceable": False,
                "verifiable_by_photo": True,
                "visual_cues": "2m braided USB-C cable with Velcro tie",
                "source": {"type": "seller_catalogue", "ref": "cat row 100"},
            },
        ],
        "list_price": 49900,
        "refurbish_cost": 5000,
    },
}

ORG_SKUS: dict[str, list[str]] = {
    "org_demo_alpha": [
        "SKU-LAMP-LED",
        "SKU-TOWEL-BLU",
        "SKU-PUZZLE-500",
        "SKU-PROT-1KG",
        "SKU-LEASH-6FT",
        "SKU-BOTTLE-750",
        "SKU-CABLE-USBC",
        "SKU-SERUM-30",
    ],
    "org_demo_bravo": [
        "SKU-PUZZLE-500",
        "SKU-BOTTLE-750",
        "SKU-SERUM-30",
        "SKU-CANDLE-3",
        "SKU-MUG-11",
        "SKU-PROT-1KG",
        "SKU-TOWEL-BLU",
    ],
}


def generate_all_cards() -> list[Path]:
    written: list[Path] = []

    for org_id, skus in ORG_SKUS.items():
        org_dir = PRODUCTS_DIR / org_id
        org_dir.mkdir(parents=True, exist_ok=True)
        images_base = org_dir / "images"

        for idx, sku in enumerate(skus):
            spec = SKU_SPECS[sku]
            sku_img_dir = images_base / sku
            sku_img_dir.mkdir(parents=True, exist_ok=True)

            img_bytes, img_sha = make_dummy_jpeg(idx)
            img_path = sku_img_dir / "front.jpg"
            img_path.write_bytes(img_bytes)
            rel_img_path = f"images/{sku}/front.jpg"

            card_data: dict[str, Any] = {
                "schema": "product-card/v1",
                "version": "1.0.0",
                "org_id": org_id,
                "sku": sku,
                "identifiers": {
                    "asin": spec["asin"],
                    "fnsku": None,
                    "gtin": None,
                    "model_numbers": [],
                    "barcode_values": [],
                },
                "title": spec["title"],
                "brand": spec["brand"],
                "category_key": spec["category_key"],
                "distinguishing_features": spec["df"],
                "similar_skus": spec["similar"],
                "components": spec["components"],
                "reference_images": [
                    {
                        "id": "ref_front",
                        "view": "front",
                        "path": rel_img_path,
                        "sha256": img_sha,
                    }
                ],
                "value": {
                    "synthetic": True,
                    "list_price": {"amount_minor": spec["list_price"], "currency": "INR"},
                    "recovery_rate_bp": {
                        "restock_new": 10000,
                        "restock_used": 6500,
                        "refurbish": 5500,
                        "liquidate": 2000,
                        "dispose": 0,
                    },
                    "refurbish_cost": {"amount_minor": spec["refurbish_cost"], "currency": "INR"},
                },
                "provenance_notes": f"Product Knowledge Card for {sku} under {org_id}",
            }

            card_obj = ProductCardV1.model_validate(card_data)
            d = card_obj.model_dump(by_alias=True)
            d["content_sha256"] = compute_reference_content_sha256(d)
            card_file = org_dir / f"{sku}.yaml"
            card_file.write_text(yaml.dump(d, sort_keys=False, allow_unicode=True), encoding="utf-8")
            written.append(card_file)

    # Orders seed
    orders_dir = REF_DIR / "orders"
    orders_dir.mkdir(parents=True, exist_ok=True)
    orders_file = orders_dir / "orders-seed.csv"

    sample_csv = REPO_ROOT / "data" / "returns_sample.csv"
    orders_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    with sample_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["org_id"], row["order_id"], row["unit_id"])
            if key not in seen:
                seen.add(key)
                orders_rows.append(
                    {
                        "org_id": row["org_id"],
                        "order_id": row["order_id"],
                        "unit_id": row["unit_id"],
                        "ordered_sku": row["ordered_sku"],
                        "ordered_asin": row["ordered_asin"],
                        "quantity": 1,
                        "fulfilment_route": "fba",
                        "ordered_at": row["captured_at"],
                    }
                )

    with orders_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "org_id",
                "order_id",
                "unit_id",
                "ordered_sku",
                "ordered_asin",
                "quantity",
                "fulfilment_route",
                "ordered_at",
            ],
        )
        writer.writeheader()
        writer.writerows(orders_rows)

    return written


if __name__ == "__main__":
    files = generate_all_cards()
    print(f"Generated {len(files)} product cards.")
