#!/usr/bin/env python3
"""Durable human retirement registry for approved style templates."""

from __future__ import annotations

import json
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from style_atomic import atomic_write_json


PRODUCER = "style-template-analyzer"
RETIREMENT_REGISTRY_NAME = "已退役模板索引.json"
KEY_RE = re.compile(r"^[a-z][a-z0-9-]{1,59}$")
_LIFECYCLE_THREAD_LOCK = threading.RLock()


class RetirementRegistryError(ValueError):
    """Machine-readable retirement registry failure."""


@contextmanager
def _lock(path: Path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


@contextmanager
def lifecycle_lock(registry_file: Path):
    """Serialize retirement registration with dynamic-baseline promotion."""
    with _LIFECYCLE_THREAD_LOCK:
        with _lock(registry_file.parent / ".style-template-lifecycle.lock"):
            yield


def _empty_registry() -> dict[str, Any]:
    return {
        "artifactType": "style_template_retirement_registry",
        "schemaVersion": "1.0.0",
        "producer": PRODUCER,
        "items": [],
    }


def load_retirement_registry(registry_file: Path) -> dict[str, Any]:
    if not registry_file.is_file():
        return _empty_registry()
    try:
        data = json.loads(registry_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RetirementRegistryError("retirement_registry_invalid") from error
    if (
        not isinstance(data, dict)
        or data.get("artifactType") != "style_template_retirement_registry"
        or data.get("schemaVersion") != "1.0.0"
        or data.get("producer") != PRODUCER
        or not isinstance(data.get("items"), list)
    ):
        raise RetirementRegistryError("retirement_registry_invalid")
    keys: set[str] = set()
    for item in data["items"]:
        key = item.get("templateKey") if isinstance(item, dict) else None
        if not isinstance(key, str) or not KEY_RE.fullmatch(key) or key in keys:
            raise RetirementRegistryError("retirement_registry_invalid")
        keys.add(key)
    return data


def load_retired_keys(registry_file: Path) -> set[str]:
    return {str(item["templateKey"]) for item in load_retirement_registry(registry_file)["items"]}


def register_retirement(
    registry_file: Path,
    template_key: str,
    reason: str,
    *,
    retired_at: str | None = None,
) -> dict[str, Any]:
    if not KEY_RE.fullmatch(template_key) or not reason.strip():
        raise RetirementRegistryError("retirement_request_invalid")
    with lifecycle_lock(registry_file):
        return _register_retirement_unlocked(
            registry_file,
            template_key,
            reason,
            retired_at=retired_at,
        )


def _register_retirement_unlocked(
    registry_file: Path,
    template_key: str,
    reason: str,
    *,
    retired_at: str | None,
) -> dict[str, Any]:
    registry = load_retirement_registry(registry_file)
    existing = next(
        (item for item in registry["items"] if item["templateKey"] == template_key),
        None,
    )
    if existing is not None:
        return dict(existing)
    item = {
        "templateKey": template_key,
        "retiredAt": retired_at or datetime.now(timezone.utc).isoformat(),
        "authority": "human",
        "reason": reason.strip(),
    }
    registry["items"].append(item)
    registry["items"].sort(key=lambda candidate: candidate["templateKey"])
    atomic_write_json(registry_file, registry)
    return dict(item)


def register_retirement_and_refresh_catalog(
    registry_file: Path,
    catalog_file: Path,
    template_key: str,
    reason: str,
) -> tuple[dict[str, Any], int]:
    """Register retirement and remove the key from the active catalog under one lock."""
    _validate_retirement_request(registry_file, catalog_file, template_key, reason)
    with lifecycle_lock(registry_file):
        registry_existed = registry_file.is_file()
        registry = load_retirement_registry(registry_file)
        catalog = _load_active_catalog(catalog_file)
        updated_registry, retirement = _updated_registry(registry, template_key, reason)
        updated_catalog, removed = _catalog_without_template(catalog, template_key)
        try:
            atomic_write_json(registry_file, updated_registry)
            atomic_write_json(catalog_file, updated_catalog)
        except Exception:
            _restore_json(registry_file, registry_existed, registry)
            _restore_json(catalog_file, True, catalog)
            raise
        return retirement, removed


def retire_template_transaction(
    pool: Any,
    ledger_file: Path,
    registry_file: Path,
    catalog_file: Path,
    template_key: str,
    reason: str,
) -> tuple[dict[str, Any], int, list[dict[str, Any]]]:
    """Retire registry, active catalog, and test-image assignments as one lifecycle transaction."""
    _validate_retirement_request(registry_file, catalog_file, template_key, reason)
    with lifecycle_lock(registry_file):
        registry_existed = registry_file.is_file()
        registry = load_retirement_registry(registry_file)
        catalog = _load_active_catalog(catalog_file)
        updated_registry, retirement = _updated_registry(registry, template_key, reason)
        updated_catalog, removed = _catalog_without_template(catalog, template_key)
        try:
            atomic_write_json(registry_file, updated_registry)
            atomic_write_json(catalog_file, updated_catalog)
            released = pool.retire_template_persisted(
                template_key,
                ledger_file,
                reason=f"模板退役：{reason}",
                decided_at=retirement.get("retiredAt"),
            )
        except Exception:
            _restore_json(registry_file, registry_existed, registry)
            _restore_json(catalog_file, True, catalog)
            raise
        return retirement, removed, released


def _validate_retirement_request(
    registry_file: Path,
    catalog_file: Path,
    template_key: str,
    reason: str,
) -> None:
    if not KEY_RE.fullmatch(template_key) or not reason.strip():
        raise RetirementRegistryError("retirement_request_invalid")
    expected_registry = catalog_file.resolve().parent / RETIREMENT_REGISTRY_NAME
    if registry_file.resolve() != expected_registry:
        raise RetirementRegistryError("retirement_catalog_scope_mismatch")


def _load_active_catalog(catalog_file: Path) -> dict[str, Any]:
    try:
        catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RetirementRegistryError("active_catalog_invalid") from error
    if (
        not isinstance(catalog, dict)
        or catalog.get("artifactType") != "style_template_delivery_catalog"
        or catalog.get("producer") != PRODUCER
        or not isinstance(catalog.get("items"), list)
        or any(
            not isinstance(item, dict) or not isinstance(item.get("key"), str)
            for item in catalog.get("items", [])
        )
    ):
        raise RetirementRegistryError("active_catalog_invalid")
    return catalog


def _updated_registry(
    registry: dict[str, Any],
    template_key: str,
    reason: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = json.loads(json.dumps(registry, ensure_ascii=False))
    existing = next(
        (item for item in updated["items"] if item["templateKey"] == template_key),
        None,
    )
    if existing is not None:
        return updated, dict(existing)
    retirement = {
        "templateKey": template_key,
        "retiredAt": datetime.now(timezone.utc).isoformat(),
        "authority": "human",
        "reason": reason.strip(),
    }
    updated["items"].append(retirement)
    updated["items"].sort(key=lambda item: item["templateKey"])
    return updated, dict(retirement)


def _shaped_counts(existing: object, values: list[str]) -> dict[str, int]:
    counts = {
        str(key): 0
        for key in existing
    } if isinstance(existing, dict) else {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _catalog_without_template(
    catalog: dict[str, Any],
    template_key: str,
) -> tuple[dict[str, Any], int]:
    updated = json.loads(json.dumps(catalog, ensure_ascii=False))
    retained = [item for item in updated["items"] if item["key"] != template_key]
    removed = len(updated["items"]) - len(retained)
    updated["items"] = retained
    updated["templateCount"] = len(retained)
    if "effectImageCount" in updated:
        updated["effectImageCount"] = sum(bool(item.get("effectImage")) for item in retained)
    if "approvalProvenanceCounts" in updated:
        updated["approvalProvenanceCounts"] = _shaped_counts(
            updated["approvalProvenanceCounts"],
            [str(item.get("approvalProvenance", "unknown")) for item in retained],
        )
    if "ossStatusCounts" in updated:
        updated["ossStatusCounts"] = _shaped_counts(
            updated["ossStatusCounts"],
            [str(item.get("ossStatus", "unknown")) for item in retained],
        )
    return updated, removed


def _restore_json(path: Path, existed: bool, value: dict[str, Any]) -> None:
    if existed:
        atomic_write_json(path, value)
    else:
        path.unlink(missing_ok=True)
