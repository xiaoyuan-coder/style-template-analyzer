#!/usr/bin/env python3
"""Durable human retirement registry for approved style templates."""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from style_atomic import atomic_write_json


PRODUCER = "style-template-analyzer"
RETIREMENT_REGISTRY_NAME = "已退役模板索引.json"
KEY_RE = re.compile(r"^[a-z][a-z0-9-]{1,59}$")


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
