#!/usr/bin/env python3
"""Authoritative catalog status and workstation delivery diagnostics."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PRODUCER = "style-template-analyzer@8.7.0"


class OperationalAuditError(RuntimeError):
    """Raised when an authoritative operational source is invalid."""


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(value: object, *, catalog_root: Path, data_root: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    if candidate.parts and candidate.parts[0] in {
        "05-风格化模板生产",
        "06-模板质量评测",
        "07-数据验收与上线",
    }:
        return (data_root / candidate).resolve()
    return (catalog_root / candidate).resolve()


def _remote(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        url = urlparse(value)
    except ValueError:
        return False
    return url.scheme == "https" and bool(url.hostname)


def _extract_local_path(receipt: Any) -> Path | None:
    if not isinstance(receipt, dict):
        return None
    for field in ("approvedBefore", "inputPath", "sourcePath", "localPath"):
        value = receipt.get(field)
        if isinstance(value, str) and value:
            path = Path(value)
            if path.is_file():
                return path.resolve()
    for field in ("source", "provider"):
        source = receipt.get(field)
        if isinstance(source, dict):
            path = _extract_local_path(source)
            if path is not None:
                return path
    return None


def discover_approved_before(
    item: dict[str, Any],
    *,
    catalog_root: Path,
    data_root: Path,
) -> Path | None:
    explicit = _resolve(item.get("approvedBefore"), catalog_root=catalog_root, data_root=data_root)
    if explicit is not None and explicit.is_file():
        return explicit
    source_package = _resolve(item.get("sourcePackage"), catalog_root=catalog_root, data_root=data_root)
    if source_package is None:
        return None
    roots = [source_package]
    if source_package.name in {"package", "review-package"}:
        roots.append(source_package.parent / "internal")
    roots.extend([source_package / "internal", source_package.parent / "internal"])
    seen: set[Path] = set()
    for root in roots:
        root = root.resolve()
        if root in seen:
            continue
        seen.add(root)
        for name in (
            "generation-request.json",
            "cover-generation-request.json",
            "test-image-assignment.json",
            "cover-generation-receipt.json",
        ):
            file = root / name
            if not file.is_file():
                continue
            try:
                path = _extract_local_path(_read(file))
            except (OSError, json.JSONDecodeError):
                path = None
            if path is not None:
                return path
        for name in ("before.png", "before.jpg", "before.jpeg", "source.png", "source.jpg", "source.jpeg"):
            candidate = root / name
            if candidate.is_file():
                return candidate.resolve()
    return None


def _catalog(catalog_file: Path) -> dict[str, Any]:
    try:
        value = _read(catalog_file)
    except (OSError, json.JSONDecodeError) as error:
        raise OperationalAuditError(f"catalog_unreadable:{error}") from error
    if (
        not isinstance(value, dict)
        or value.get("artifactType") != "style_template_delivery_catalog"
        or not isinstance(value.get("items"), list)
    ):
        raise OperationalAuditError("catalog_invalid")
    return value


def workflow_status_snapshot(
    catalog_file: Path,
    *,
    data_root: Path | None = None,
    delivery_root: Path | None = None,
) -> dict[str, Any]:
    catalog_file = catalog_file.resolve()
    catalog_root = catalog_file.parent
    data_root = (data_root or catalog_root).resolve()
    delivery_root = delivery_root.resolve() if delivery_root else None
    catalog = _catalog(catalog_file)
    rows: list[dict[str, Any]] = []
    for raw in catalog["items"]:
        if not isinstance(raw, dict):
            raise OperationalAuditError("catalog_item_invalid")
        key = raw.get("key")
        revision = raw.get("revision")
        if not isinstance(key, str) or not isinstance(revision, int):
            raise OperationalAuditError("catalog_item_identity_invalid")
        issues: list[str] = []
        template_file = _resolve(raw.get("template"), catalog_root=catalog_root, data_root=data_root)
        effect_file = _resolve(raw.get("effectImage"), catalog_root=catalog_root, data_root=data_root)
        template: dict[str, Any] = {}
        if template_file is None or not template_file.is_file():
            issues.append("CATALOG_TEMPLATE_MISSING")
        else:
            try:
                value = _read(template_file)
                template = value if isinstance(value, dict) else {}
            except (OSError, json.JSONDecodeError):
                issues.append("CATALOG_TEMPLATE_INVALID")
            expected = raw.get("templateSha256")
            if isinstance(expected, str) and expected and _sha256(template_file) != expected:
                issues.append("CATALOG_TEMPLATE_HASH_DRIFT")
        if effect_file is None or not effect_file.is_file():
            issues.append("CATALOG_EFFECT_MISSING")
        else:
            expected = raw.get("effectSha256")
            if isinstance(expected, str) and expected and _sha256(effect_file) != expected:
                issues.append("CATALOG_EFFECT_HASH_DRIFT")
        cover = template.get("cover", raw.get("cover"))
        actual_status = "finalized" if _remote(cover) else "awaiting-finalization"
        if raw.get("ossStatus") != actual_status:
            issues.append("CATALOG_OSS_STATUS_DRIFT")
        approved_before = discover_approved_before(raw, catalog_root=catalog_root, data_root=data_root)
        if approved_before is None:
            issues.append("APPROVED_BEFORE_UNDISCOVERABLE")
        delivery_file = delivery_root / f"{key}.json" if delivery_root else None
        delivered = bool(delivery_file and delivery_file.is_file())
        if actual_status == "finalized" and delivery_root and not delivered:
            issues.append("DELIVERY_JSON_MISSING")
        rows.append({
            "key": key,
            "revision": revision,
            "catalogOssStatus": raw.get("ossStatus"),
            "actualOssStatus": actual_status,
            "delivered": delivered,
            "template": template_file.as_posix() if template_file else None,
            "approvedAfter": effect_file.as_posix() if effect_file else None,
            "approvedBefore": approved_before.as_posix() if approved_before else None,
            "delivery": delivery_file.as_posix() if delivery_file else None,
            "issues": issues,
        })
    counts = {
        "templates": len(rows),
        "catalogFinalized": sum(row["catalogOssStatus"] == "finalized" for row in rows),
        "actualFinalized": sum(row["actualOssStatus"] == "finalized" for row in rows),
        "awaitingFinalization": sum(row["actualOssStatus"] == "awaiting-finalization" for row in rows),
        "delivered": sum(row["delivered"] for row in rows),
        "missingApprovedBefore": sum("APPROVED_BEFORE_UNDISCOVERABLE" in row["issues"] for row in rows),
        "issueItems": sum(bool(row["issues"]) for row in rows),
    }
    return {
        "artifactType": "style_workflow_status_snapshot",
        "schemaVersion": "1.0.0",
        "producer": PRODUCER,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "catalog": catalog_file.as_posix(),
        "catalogSha256": _sha256(catalog_file),
        "deliveryRoot": delivery_root.as_posix() if delivery_root else None,
        "counts": counts,
        "items": rows,
    }


def diagnose_delivery(
    delivery_file: Path,
    catalog_file: Path,
    *,
    data_root: Path | None = None,
) -> dict[str, Any]:
    delivery_file = delivery_file.resolve()
    catalog_file = catalog_file.resolve()
    catalog_root = catalog_file.parent
    data_root = (data_root or catalog_root).resolve()
    catalog = _catalog(catalog_file)
    try:
        delivery = _read(delivery_file)
    except (OSError, json.JSONDecodeError) as error:
        raise OperationalAuditError(f"delivery_unreadable:{error}") from error
    if not isinstance(delivery, dict) or not isinstance(delivery.get("key"), str):
        raise OperationalAuditError("delivery_invalid")
    matches = [
        item for item in catalog["items"]
        if isinstance(item, dict) and item.get("key") == delivery["key"] and isinstance(item.get("revision"), int)
    ]
    if not matches:
        raise OperationalAuditError("delivery_key_not_in_catalog")
    active = max(matches, key=lambda item: item["revision"])
    active_template_file = _resolve(active.get("template"), catalog_root=catalog_root, data_root=data_root)
    if active_template_file is None or not active_template_file.is_file():
        raise OperationalAuditError("active_template_missing")
    active_template = _read(active_template_file)
    issues: list[str] = []
    if delivery != active_template:
        issues.append("DELIVERY_JSON_STALE")
    before = discover_approved_before(active, catalog_root=catalog_root, data_root=data_root)
    if before is None:
        issues.append("APPROVED_BEFORE_UNDISCOVERABLE")
    return {
        "artifactType": "style_delivery_diagnostic",
        "schemaVersion": "1.0.0",
        "producer": PRODUCER,
        "delivery": delivery_file.as_posix(),
        "deliverySha256": _sha256(delivery_file),
        "catalog": catalog_file.as_posix(),
        "templateKey": delivery["key"],
        "activeRevision": active["revision"],
        "activeTemplate": active_template_file.as_posix(),
        "activeTemplateSha256": _sha256(active_template_file),
        "approvedBefore": before.as_posix() if before else None,
        "approvedAfter": str(_resolve(active.get("effectImage"), catalog_root=catalog_root, data_root=data_root) or ""),
        "issues": issues,
        "status": "pass" if not issues else "drift",
    }
