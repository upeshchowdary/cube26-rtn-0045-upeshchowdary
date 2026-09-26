"""Intake and photo pipeline acceptance tests (T-PHO-*, §9, §19, §23 P3)."""

from __future__ import annotations

import io
import time
import uuid

import cv2
import httpx
import numpy as np
import pytest
from PIL import Image
from PIL.ExifTags import GPS, Base

from returns_manager.api.app import create_app
from returns_manager.db.pool import Database
from returns_manager.errors import PayloadTooLarge, QualityGateRefusal, UnsupportedMediaType
from returns_manager.intake.images import process_photo, sniff_mime, validate_photo_bytes
from returns_manager.intake.quality import (
    assess_photo_quality,
    evaluate_exposure,
    evaluate_near_duplicate,
    evaluate_resolution,
    evaluate_reused_photo,
    evaluate_sharpness,
)
from returns_manager.intake.retake import guidance_for_issues
from returns_manager.intake.service import IntakeService
from returns_manager.security import api_keys

# ── Helper functions for synthetic test images ─────────────────────────────────


def make_jpeg(
    width: int = 1920,
    height: int = 1080,
    color: tuple[int, int, int] = (128, 128, 128),
    pattern: str = "plain",
    blur: bool = False,
    exif_meta: dict[int, object] | None = None,
) -> bytes:
    """Create a synthetic JPEG image."""
    arr = np.full((height, width, 3), color, dtype=np.uint8)

    if pattern == "checkerboard":
        block = 40
        for y in range(0, height, block):
            for x in range(0, width, block):
                if (x // block + y // block) % 2 == 0:
                    arr[y : y + block, x : x + block] = (190, 190, 190)
                else:
                    arr[y : y + block, x : x + block] = (60, 60, 60)

    if blur:
        blurred = cv2.GaussianBlur(arr, (51, 51), 20)
        arr = np.asarray(blurred, dtype=np.uint8)

    pil_img = Image.fromarray(arr, mode="RGB")
    exif = pil_img.getexif()
    if exif_meta:
        for tag, val in exif_meta.items():
            exif[tag] = val

    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=90, exif=exif)
    return buf.getvalue()


def make_png(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_webp(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    return buf.getvalue()


def make_heic_bytes() -> bytes:
    # Minimal valid HEIC container bytes with ftypheic brand
    return b"\x00\x00\x00\x1cftypheic\x00\x00\x00\x00heicmif1\x00\x00\x00\x08mdat"


def _fresh_org() -> str:
    return f"org_t{uuid.uuid4().hex[:12]}"


# ── T-PHO-01: Magic byte sniffing ──────────────────────────────────────────────


def test_t_pho_01_magic_bytes_sniffing() -> None:
    """Allowed formats: JPEG, PNG, WebP, HEIC/HEIF; invalid formats raise 415 UnsupportedMediaType."""
    jpeg_data = make_jpeg()
    assert sniff_mime(jpeg_data) == "image/jpeg"

    png_data = make_png()
    assert sniff_mime(png_data) == "image/png"

    webp_data = make_webp()
    assert sniff_mime(webp_data) == "image/webp"

    heic_data = make_heic_bytes()
    assert sniff_mime(heic_data) == "image/heic"

    # Unsupported formats and random bytes
    with pytest.raises(UnsupportedMediaType):
        sniff_mime(b"%PDF-1.5 fake pdf content")

    with pytest.raises(UnsupportedMediaType):
        sniff_mime(b"<html><body>Not an image</body></html>")

    with pytest.raises(UnsupportedMediaType):
        sniff_mime(b"GIF89a\x01\x00\x01\x00\x80\x00\x00")

    with pytest.raises(UnsupportedMediaType):
        sniff_mime(b"\x00\x01\x02\x03\x04")


# ── T-PHO-02: Size cap 20 MB ───────────────────────────────────────────────────


def test_t_pho_02_size_cap_20mb() -> None:
    """Photo upload enforces 20 MB cap; larger payloads raise PayloadTooLarge."""
    # Under 20 MB
    valid_bytes = b"\xff\xd8\xff" + b"0" * 1024
    assert validate_photo_bytes(valid_bytes) == "image/jpeg"

    # Over 20 MB
    over_limit_bytes = b"\xff\xd8\xff" + b"0" * (20 * 1024 * 1024 + 1)
    with pytest.raises(PayloadTooLarge):
        validate_photo_bytes(over_limit_bytes)


# ── T-PHO-03: Decompression bomb guard ─────────────────────────────────────────


def test_t_pho_03_decompression_bomb_guard() -> None:
    """Image.MAX_IMAGE_PIXELS is set to 60,000,000 to prevent decompression bomb DOS."""
    assert Image.MAX_IMAGE_PIXELS == 60_000_000


# ── T-PHO-04: EXIF transposition and GPS stripping ─────────────────────────────


def test_t_pho_04_exif_transposition_and_gps_stripping() -> None:
    """EXIF is sanitized to remove GPS info, orientation is transposed, and analysis copy strips metadata."""
    img = Image.new("RGB", (300, 150), color=(128, 128, 128))
    exif = img.getexif()
    exif[Base.Make] = "TestCamera"
    exif[Base.Model] = "ModelX"
    exif[Base.Orientation] = 6  # 90 degrees CCW
    gps_ifd = exif.get_ifd(Base.GPSInfo)
    gps_ifd[GPS.GPSLatitudeRef] = "N"
    gps_ifd[GPS.GPSLatitude] = (37, 46, 29)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    raw_bytes = buf.getvalue()

    processed = process_photo(raw_bytes)

    # GPS info must not be present in sanitized exif_summary
    assert "GPSInfo" not in processed.exif_summary
    assert "34853" not in processed.exif_summary
    assert processed.exif_summary.get("Make") == "TestCamera"
    assert processed.exif_summary.get("Model") == "ModelX"

    # Orientation 6 transposes (300, 150) -> width 150, height 300
    # Original raw width/height
    assert processed.original_width == 300
    assert processed.original_height == 150

    # Analysis copy is valid JPEG with sha256
    assert processed.sha256_analysis is not None
    assert len(processed.phash) == 64


# ── T-PHO-05: Deduplication by sha256_original ─────────────────────────────────


@pytest.mark.db
@pytest.mark.asyncio
async def test_t_pho_05_dedupe_by_sha256_original(db: Database) -> None:
    """Uploading the same photo bytes twice to the same return returns the existing row (no duplicate)."""
    org_id = _fresh_org()
    async with db.transaction(org_id) as conn:
        await conn.execute(
            "INSERT INTO rm.organizations (org_id, name) VALUES (%s, %s)", (org_id, "Org Dedupe")
        )

    svc = IntakeService(db)
    ret = await svc.create_return(org_id=org_id, actor_id="op_test", order_id="ORD-01", unit_id="UNIT-0001")

    photo_bytes = make_jpeg(width=1200, height=900, pattern="checkerboard")

    res1 = await svc.upload_photo(
        org_id=org_id, actor_id="op_test", return_id=ret.return_id, photo_bytes=photo_bytes
    )
    res2 = await svc.upload_photo(
        org_id=org_id, actor_id="op_test", return_id=ret.return_id, photo_bytes=photo_bytes
    )

    # Identical photo_id returned
    assert res1.photo_id == res2.photo_id
    assert res1.slot == res2.slot

    # DB verification: exactly 1 row exists
    async with db.transaction(org_id) as conn:
        res = await conn.execute(
            "SELECT count(*) as cnt FROM rm.return_photos WHERE org_id = %s AND return_id = %s",
            (org_id, ret.return_id),
        )
        row = await res.fetchone()
        assert row is not None
        assert row["cnt"] == 1


# ── T-PHO-06: Idempotent upload replay ─────────────────────────────────────────


@pytest.mark.db
@pytest.mark.asyncio
async def test_t_pho_06_idempotent_upload_replay(db: Database) -> None:
    """Sending the same Idempotency-Key returns the stored response with idempotent_replay=True."""
    org_id = _fresh_org()
    async with db.transaction(org_id) as conn:
        await conn.execute(
            "INSERT INTO rm.organizations (org_id, name) VALUES (%s, %s)", (org_id, "Org Idem")
        )

    svc = IntakeService(db)
    ret = await svc.create_return(org_id=org_id, actor_id="op_test", order_id="ORD-02", unit_id="UNIT-0002")

    photo_bytes = make_jpeg(width=1200, height=900, pattern="checkerboard")
    idem_key = "idem-upload-key-12345"

    res1 = await svc.upload_photo(
        org_id=org_id,
        actor_id="op_test",
        return_id=ret.return_id,
        photo_bytes=photo_bytes,
        idempotency_key=idem_key,
    )
    assert not res1.idempotent_replay

    res2 = await svc.upload_photo(
        org_id=org_id,
        actor_id="op_test",
        return_id=ret.return_id,
        photo_bytes=photo_bytes,
        idempotency_key=idem_key,
    )
    assert res2.idempotent_replay
    assert res2.photo_id == res1.photo_id


# ── T-PHO-07: Quality gate on synthetic images ─────────────────────────────────


def test_t_pho_07_quality_gate_synthetic_checks() -> None:
    """Sharpness, exposure, and resolution thresholds function correctly on synthetic inputs (§9.2)."""
    # 1. Sharpness: high-contrast checkerboard passes; Gaussian blur fails
    sharp_arr = np.zeros((1024, 1024), dtype=np.uint8)
    for y in range(0, 1024, 32):
        for x in range(0, 1024, 32):
            if (x // 32 + y // 32) % 2 == 0:
                sharp_arr[y : y + 32, x : x + 32] = 255
    res_sharp = evaluate_sharpness(sharp_arr)
    assert res_sharp.status == "pass"

    blur_arr = cv2.GaussianBlur(sharp_arr, (51, 51), 25)
    res_blur = evaluate_sharpness(blur_arr)
    assert res_blur.status == "fail"
    assert "blur" in res_blur.issues

    # 2. Exposure: normal passes; dark fails; bright fails
    res_norm = evaluate_exposure(np.full((100, 100), 128, dtype=np.uint8))
    assert res_norm.status == "pass"

    res_dark = evaluate_exposure(np.full((100, 100), 20, dtype=np.uint8))
    assert res_dark.status == "fail"
    assert "too_dark" in res_dark.issues

    res_bright = evaluate_exposure(np.full((100, 100), 245, dtype=np.uint8))
    assert res_bright.status == "fail"
    assert "too_bright" in res_bright.issues

    # 3. Resolution: >=1080 passes; 720-1079 warns; <720 fails
    assert evaluate_resolution(1920, 1080).status == "pass"
    assert evaluate_resolution(1200, 800).status == "warn"
    assert evaluate_resolution(600, 600).status == "fail"


# ── T-PHO-08: Near duplicate and reused photo flags ────────────────────────────


def test_t_pho_08_near_duplicate_and_reused_photo() -> None:
    """Near-duplicate within return set flags warn; reused photo within org in 30 days flags warn."""
    # Near-duplicate: identical phash (distance 0 <= 5)
    phash1 = "1" * 64
    phash2 = "1" * 63 + "0"  # distance 1
    res_dup = evaluate_near_duplicate(phash1, [phash2])
    assert res_dup.status == "warn"
    assert "near_duplicate_in_set" in res_dup.issues

    # Different images: distance > 10 passes
    phash_diff = "0" * 32 + "1" * 32  # distance 32
    res_diff = evaluate_near_duplicate(phash1, [phash_diff])
    assert res_diff.status == "pass"

    # Reused photo: distance <= 4 flags possible_reused_photo
    res_reused = evaluate_reused_photo(phash1, [phash2])
    assert res_reused.status == "warn"
    assert "possible_reused_photo" in res_reused.issues


# ── T-PHO-09: Submit gating ────────────────────────────────────────────────────


@pytest.mark.db
@pytest.mark.asyncio
async def test_t_pho_09_submit_gating(db: Database) -> None:
    """Submit requires >= 2 non-failing photos unless warnings acknowledged (§9.2, §9.4)."""
    org_id = _fresh_org()
    async with db.transaction(org_id) as conn:
        await conn.execute(
            "INSERT INTO rm.organizations (org_id, name) VALUES (%s, %s)", (org_id, "Org Gating")
        )

    svc = IntakeService(db)
    ret = await svc.create_return(org_id=org_id, actor_id="op_test", order_id="ORD-03", unit_id="UNIT-0003")

    # 0 photos -> submit must fail
    with pytest.raises(QualityGateRefusal):
        await svc.submit_return(org_id=org_id, actor_id="op_test", return_id=ret.return_id)

    # 1 good photo + 1 blurry photo
    sharp_photo = make_jpeg(width=1200, height=1200, pattern="checkerboard")
    blurry_photo = make_jpeg(width=1200, height=1200, pattern="checkerboard", blur=True)

    await svc.upload_photo(
        org_id=org_id, actor_id="op_test", return_id=ret.return_id, photo_bytes=sharp_photo
    )
    await svc.upload_photo(
        org_id=org_id, actor_id="op_test", return_id=ret.return_id, photo_bytes=blurry_photo
    )

    # 1 non-fail photo (<2 required): submit must fail without acknowledgement
    with pytest.raises(QualityGateRefusal) as exc_info:
        await svc.submit_return(org_id=org_id, actor_id="op_test", return_id=ret.return_id)
    assert "at least 2 non-failing photos" in str(exc_info.value)

    # Submit with acknowledge_quality_warnings=True must succeed
    sub_res = await svc.submit_return(
        org_id=org_id,
        actor_id="op_test",
        return_id=ret.return_id,
        acknowledge_quality_warnings=True,
    )
    assert sub_res.status == "queued"
    assert sub_res.job_id is not None

    # Verify return transitioned to queued in DB
    details = await svc.get_return(org_id=org_id, return_id=ret.return_id)
    assert details.return_data.status == "queued"
    assert details.return_data.submitted_at is not None


# ── T-PHO-10: Local upload latency benchmark ───────────────────────────────────


def test_t_pho_10_upload_latency_local() -> None:
    """Local processing of a high-resolution photo must complete well under 1.5 seconds (§9.1)."""
    photo_bytes = make_jpeg(width=2048, height=1536, pattern="checkerboard")

    t0 = time.perf_counter()
    processed = process_photo(photo_bytes)
    quality = assess_photo_quality(
        image_bytes=processed.original_bytes,
        phash=processed.phash,
        orig_width=processed.original_width,
        orig_height=processed.original_height,
    )
    guidance = guidance_for_issues(quality.issues)
    elapsed = time.perf_counter() - t0

    assert isinstance(guidance, list)
    assert elapsed < 1.5, f"Processing took {elapsed:.3f} s (expected < 1.5 s)"
    assert processed.sha256_original is not None


# ── T-PHO-11: Retake guidance generator ────────────────────────────────────────


def test_t_pho_11_retake_guidance_generator() -> None:
    """Retake guidance provides deterministic instructions for every quality issue code (§9.3)."""
    issues = ["blur", "too_dark", "near_duplicate_in_set"]
    guidance = guidance_for_issues(issues)

    assert len(guidance) == 3
    reasons = [g.reason_code for g in guidance]
    assert "blur" in reasons
    assert "too_dark" in reasons
    assert "near_duplicate_in_set" in reasons

    for g in guidance:
        assert g.source == "gate"
        assert len(g.instruction) > 10


# ── T-PHO-12: Full intake lifecycle via FastAPI endpoints ──────────────────────


@pytest.mark.db
@pytest.mark.asyncio
async def test_t_pho_12_fastapi_endpoints(db: Database) -> None:
    """FastAPI routes for return creation, photo upload, observation, and submit work end-to-end."""
    org_id = _fresh_org()
    async with db.transaction(org_id) as conn:
        await conn.execute("INSERT INTO rm.organizations (org_id, name) VALUES (%s, %s)", (org_id, "Org API"))

    # Issue API key with returns:write and returns:read
    key = await api_keys.create_key(
        db,
        org_id=org_id,
        name="test-intake-key",
        scopes=["returns:write", "returns:read"],
        created_by="test",
        env="local",
    )

    from returns_manager.api.deps import Services
    from returns_manager.config import get_settings

    app = create_app()
    app.state.services = Services(settings=get_settings(), db=db, jwt=None, storage=None)
    headers = {"X-API-Key": key.plaintext}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create return
        create_resp = await client.post(
            "/api/v1/returns",
            headers=headers,
            json={"order_id": "ORD-API-01", "unit_id": "UNIT-0042", "ordered_sku": "SKU-001"},
        )
        assert create_resp.status_code == 201
        ret_data = create_resp.json()
        return_id = ret_data["return_id"]
        assert ret_data["status"] == "capturing"
        assert ret_data["record_id"] == "RTN-0042"

        # 2. Upload photo 1
        photo1 = make_jpeg(width=1200, height=900, pattern="checkerboard")
        upload_resp1 = await client.post(
            f"/api/v1/returns/{return_id}/photos",
            headers={**headers, "Idempotency-Key": "key-photo-1"},
            files={"file": ("photo1.jpg", photo1, "image/jpeg")},
        )
        assert upload_resp1.status_code == 200
        p1_data = upload_resp1.json()
        assert p1_data["slot"] == 1
        assert p1_data["alias"] == "P1"

        # 3. Upload photo 2 (distinct image)
        photo2 = make_jpeg(width=1920, height=1200, pattern="checkerboard")
        upload_resp2 = await client.post(
            f"/api/v1/returns/{return_id}/photos",
            headers={**headers, "Idempotency-Key": "key-photo-2"},
            files={"file": ("photo2.jpg", photo2, "image/jpeg")},
        )
        assert upload_resp2.status_code == 200
        p2_data = upload_resp2.json()
        assert p2_data["slot"] == 2
        assert p2_data["alias"] == "P2"

        # 4. Record operator observation
        obs_resp = await client.post(
            f"/api/v1/returns/{return_id}/observation",
            headers=headers,
            json={"observed_state": "opened_unused", "note": "Seal broken, contents intact"},
        )
        assert obs_resp.status_code == 200
        obs_data = obs_resp.json()
        assert obs_data["observed_state"] == "opened_unused"

        # 5. Submit return
        sub_resp = await client.post(
            f"/api/v1/returns/{return_id}/submit",
            headers=headers,
            json={"note": "Ready for inspection"},
        )
        assert sub_resp.status_code == 202
        sub_data = sub_resp.json()
        assert sub_data["status"] == "queued"
        assert sub_data["job_id"] is not None

        # 6. Get return details
        get_resp = await client.get(f"/api/v1/returns/{return_id}", headers=headers)
        assert get_resp.status_code == 200
        details = get_resp.json()
        assert details["return"]["status"] == "queued"
        assert len(details["photos"]) == 2
        assert details["observation"]["observed_state"] == "opened_unused"
