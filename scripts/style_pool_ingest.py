#!/usr/bin/env python3
"""Download collected source records, fingerprint images, and update a test pool."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen
from urllib.error import URLError

from PIL import Image

from style_test_pool import AUTO_READY_LICENSES, TestImagePool, TestPoolError, normalize_asset, validate_pool_document


MAX_IMAGE_BYTES = 25 * 1024 * 1024
FORMAT_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
FORMAT_EXTENSION = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def fetch_image(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "MemebuyStyleTemplatePool/4.0 (rights-aware test asset maintenance)"})
    try:
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()
        with urlopen(request, timeout=30, context=context) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_IMAGE_BYTES:
                raise TestPoolError("test_asset_invalid: file_too_large")
            payload = response.read(MAX_IMAGE_BYTES + 1)
    except URLError as error:
        raise TestPoolError(f"source_download_failed: {error.reason}") from error
    if len(payload) > MAX_IMAGE_BYTES:
        raise TestPoolError("test_asset_invalid: file_too_large")
    return payload


def perceptual_dhash(image: Image.Image) -> str:
    grayscale = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(grayscale.getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | int(pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return f"{value:016x}"


def ingest_records(
    records: list[dict[str, Any]],
    assets_dir: Path,
    pool: TestImagePool,
    *,
    fetcher: Callable[[str], bytes] = fetch_image,
    collected_at: str | None = None,
    asset_checkpoint_file: Path | None = None,
    visual_classifier: Callable[[bytes, dict[str, Any]], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    assets_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    checkpoint: dict[str, Any] = {
        "artifactType": "style_test_asset_checkpoint",
        "schemaVersion": "1.0.0",
        "producer": "style-template-analyzer",
        "records": {},
    }
    if asset_checkpoint_file is not None and asset_checkpoint_file.is_file():
        loaded = json.loads(asset_checkpoint_file.read_text(encoding="utf-8"))
        if (
            loaded.get("artifactType") != "style_test_asset_checkpoint"
            or loaded.get("schemaVersion") != "1.0.0"
            or not isinstance(loaded.get("records"), dict)
        ):
            raise TestPoolError("asset_checkpoint_invalid")
        checkpoint = loaded

    def save_checkpoint() -> None:
        if asset_checkpoint_file is None:
            return
        asset_checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = asset_checkpoint_file.with_suffix(asset_checkpoint_file.suffix + f".tmp-{os.getpid()}")
        temporary.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(asset_checkpoint_file)

    for record in records:
        identity = hashlib.sha256(
            f"{record.get('sourcePageUrl', '')}\0{record.get('imageUrl', '')}".encode("utf-8")
        ).hexdigest()
        cached = checkpoint["records"].get(identity)
        if isinstance(cached, dict) and cached.get("status") == "accepted" and isinstance(cached.get("asset"), dict):
            asset = normalize_asset(cached["asset"])
            if not any(current["assetId"] == asset["assetId"] for current in pool.assets):
                pool.add(asset)
            results.append({**cached, "idempotent": True})
            continue
        if isinstance(cached, dict) and cached.get("status") == "rejected" and cached.get("code") != "source_download_failed":
            results.append({**cached, "idempotent": True})
            continue
        try:
            payload = fetcher(record["imageUrl"])
            digest = hashlib.sha256(payload).hexdigest()
            with Image.open(io.BytesIO(payload)) as image:
                image.load()
                image_format = image.format or ""
                if image_format not in FORMAT_MIME:
                    raise TestPoolError("test_asset_invalid: image_format")
                width, height = image.size
                perceptual_hash = perceptual_dhash(image)
            asset_id = f"commons-{digest[:20]}"
            target = assets_dir / f"{asset_id}{FORMAT_EXTENSION[image_format]}"
            temporary = target.with_suffix(target.suffix + f".tmp-{os.getpid()}")
            temporary.write_bytes(payload)
            temporary.replace(target)
            license_name = str(record.get("license", "Unknown"))
            declared_rights = record.get("rightsStatus")
            rights_status = (
                declared_rights
                if declared_rights in {"verified", "manual_review", "rejected"}
                else "verified" if license_name.upper() in AUTO_READY_LICENSES else "manual_review"
            )
            visual = visual_classifier(payload, record) if visual_classifier is not None else {}
            if not isinstance(visual, dict):
                raise TestPoolError("visual_classifier_invalid")
            risk_labels = sorted(set(record.get("riskLabels", [])) | set(visual.get("riskLabels", [])))
            asset = normalize_asset({
                "assetId": asset_id,
                "sourceAdapter": record.get("sourceAdapter", "unknown"),
                "sourcePageUrl": record["sourcePageUrl"],
                "imageUrl": record["imageUrl"],
                "author": record.get("author") or "Unknown",
                "license": license_name,
                "licenseUrl": record.get("licenseUrl") or record["sourcePageUrl"],
                "rightsStatus": rights_status,
                "collectedAt": collected_at or datetime.now(timezone.utc).isoformat(),
                "mime": FORMAT_MIME[image_format],
                "width": width,
                "height": height,
                "sha256": digest,
                "perceptualHash": perceptual_hash,
                "photographic": visual.get("photographic") is True if visual_classifier is not None else record.get("photographic") is True,
                "photographicEvidence": visual.get("photographicEvidence") or record.get("photographicEvidence") or "等待视觉模型确认摄影真实性",
                "riskLabels": risk_labels,
                "category": visual.get("category") or record.get("category", "unclassified"),
                "localPath": target.as_posix(),
                "semanticClusterId": visual.get("semanticClusterId") or digest,
                "visualEra": visual.get("visualEra", "unknown"),
                "colorMode": visual.get("colorMode", "unknown"),
                "plainMuseumObject": visual.get("plainMuseumObject") is True or record.get("plainMuseumObject") is True,
            })
            pool.add(asset)
            result = {"status": "accepted", "asset": asset}
        except (KeyError, OSError, TestPoolError, ValueError) as error:
            result = {"status": "rejected", "code": str(error).split(":", 1)[0], "sourcePageUrl": record.get("sourcePageUrl")}
        checkpoint["records"][identity] = result
        save_checkpoint()
        results.append(result)
    return results


def atomic_save_pool(pool: TestImagePool, pool_file: Path) -> None:
    import fcntl

    pool_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file = pool_file.with_suffix(pool_file.suffix + ".lock")
    with lock_file.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        latest_data = json.loads(pool_file.read_text(encoding="utf-8")) if pool_file.is_file() else None
        if latest_data is not None:
            validate_pool_document(latest_data)
        latest = latest_data.get("assets", []) if isinstance(latest_data, dict) else []
        merged = TestImagePool(latest)
        known_ids = {asset["assetId"] for asset in merged.assets}
        for asset in pool.assets:
            if asset["assetId"] not in known_ids:
                merged.add(asset)
                known_ids.add(asset["assetId"])
        pool.assets = merged.assets
        temporary = pool_file.with_suffix(pool_file.suffix + f".tmp-{os.getpid()}")
        temporary.write_text(json.dumps({
            "artifactType": "style_test_image_pool",
            "schemaVersion": "1.1.0",
            "producer": "style-template-analyzer",
            "assets": pool.assets,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(pool_file)


def load_existing_assets(pool_file: Path) -> list[dict[str, Any]]:
    if not pool_file.is_file():
        return []
    pool_data = json.loads(pool_file.read_text(encoding="utf-8"))
    validate_pool_document(pool_data)
    return pool_data["assets"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("pool", type=Path)
    parser.add_argument("assets_dir", type=Path)
    parser.add_argument("--asset-checkpoint", type=Path)
    args = parser.parse_args()
    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    existing = load_existing_assets(args.pool)
    pool = TestImagePool(existing)
    results = ingest_records(
        checkpoint.get("records", []), args.assets_dir, pool,
        asset_checkpoint_file=args.asset_checkpoint,
    )
    atomic_save_pool(pool, args.pool)
    accepted = sum(item["status"] == "accepted" for item in results)
    print(json.dumps({
        "accepted": accepted,
        "rejected": len(results) - accepted,
        "distribution": pool.ready_distribution(),
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
