#!/usr/bin/env python3
"""Human-pass-driven dynamic baseline catalog and active snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from style_atomic import atomic_write_json
from style_baseline import validate_baseline_snapshot
from style_contracts import PRODUCER, read_json, sha256_file
from style_retirement import (
    RETIREMENT_REGISTRY_NAME,
    RetirementRegistryError,
    lifecycle_lock,
    load_retired_keys,
)


class DynamicBaselineError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest_entries(entries: list[dict[str, Any]]) -> str:
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@contextmanager
def _lock(path: Path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def _data_root(catalog_root: Path) -> Path:
    for parent in (catalog_root, *catalog_root.parents):
        if parent.name == "05-风格化模板生产":
            return parent.parent
    return catalog_root


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


class DynamicBaselineCatalog:
    """Registers every human pass and exposes one latest active revision per key."""

    def __init__(self, catalog_file: Path) -> None:
        source = catalog_file.resolve()
        if source.is_file():
            candidate = read_json(source)
            if isinstance(candidate, dict) and candidate.get("artifactType") == "style_dynamic_baseline_pointer":
                if (
                    candidate.get("schemaVersion") != "1.0.0"
                    or candidate.get("producer") != PRODUCER
                    or candidate.get("promotionTrigger") != "human-pass"
                    or candidate.get("selectionPolicy") != "latest-passed-revision-per-key"
                ):
                    raise DynamicBaselineError("dynamic_baseline_pointer_invalid")
                source = (source.parent / str(candidate.get("catalog", ""))).resolve()
        self.catalog_file = source
        self.root = self.catalog_file.parent
        self.lock_file = self.root / ".dynamic-baseline.lock"
        self._lifecycle_guard_state = threading.local()
        self._process_lifecycle_lock = threading.RLock()

    def _read_catalog(self) -> dict[str, Any]:
        if not self.catalog_file.is_file():
            raise DynamicBaselineError("dynamic_baseline_catalog_missing")
        catalog = read_json(self.catalog_file)
        if (
            not isinstance(catalog, dict)
            or catalog.get("artifactType") != "style_template_delivery_catalog"
            or catalog.get("producer") != PRODUCER
            or not isinstance(catalog.get("items"), list)
        ):
            raise DynamicBaselineError("dynamic_baseline_catalog_invalid")
        return catalog

    def _retired_keys(self) -> set[str]:
        try:
            return load_retired_keys(self.root / RETIREMENT_REGISTRY_NAME)
        except RetirementRegistryError as error:
            raise DynamicBaselineError(str(error)) from error

    @contextmanager
    def approval_guard(self, template_key: str):
        """Hold the retirement/promotion boundary for one human-pass transaction."""
        depth = getattr(self._lifecycle_guard_state, "depth", 0)
        if depth:
            if template_key in self._retired_keys():
                raise DynamicBaselineError("dynamic_baseline_template_retired")
            yield
            return
        registry = self.root / RETIREMENT_REGISTRY_NAME
        with self._process_lifecycle_lock:
            with lifecycle_lock(registry):
                if template_key in self._retired_keys():
                    raise DynamicBaselineError("dynamic_baseline_template_retired")
                self._lifecycle_guard_state.depth = 1
                try:
                    yield
                finally:
                    self._lifecycle_guard_state.depth = 0

    def load_active(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        catalog = self._read_catalog()
        retired_keys = self._retired_keys()
        active: dict[str, dict[str, Any]] = {}
        for item in catalog["items"]:
            if not isinstance(item, dict) or item.get("verdict") != "pass":
                continue
            key = item.get("key")
            revision = item.get("revision")
            if not isinstance(key, str) or not isinstance(revision, int):
                raise DynamicBaselineError("dynamic_baseline_entry_invalid")
            if key in retired_keys:
                continue
            previous = active.get(key)
            if previous is None or revision > previous["revision"]:
                active[key] = item
            elif revision == previous["revision"] and item != previous:
                raise DynamicBaselineError("dynamic_baseline_identity_conflict")
        entries: list[dict[str, Any]] = []
        templates: list[dict[str, Any]] = []
        titles: set[str] = set()
        for key, item in sorted(active.items()):
            template_path = (self.root / str(item.get("template", ""))).resolve()
            if self.root not in template_path.parents or not template_path.is_file():
                raise DynamicBaselineError("dynamic_baseline_template_missing")
            if sha256_file(template_path) != item.get("templateSha256"):
                raise DynamicBaselineError("dynamic_baseline_digest_mismatch")
            template = read_json(template_path)
            if template.get("key") != key or template.get("title") != item.get("title"):
                raise DynamicBaselineError("dynamic_baseline_template_identity_mismatch")
            if template["title"] in titles:
                raise DynamicBaselineError("dynamic_baseline_duplicate_title")
            titles.add(template["title"])
            entries.append({
                "key": key,
                "title": template["title"],
                "path": template_path.relative_to(self.root).as_posix(),
                "sha256": item["templateSha256"],
            })
            templates.append(template)
        if not entries:
            raise DynamicBaselineError("dynamic_baseline_empty")
        snapshot = {
            "artifactType": "style_baseline_snapshot",
            "schemaVersion": "1.0.0",
            "producer": PRODUCER,
            "approved": True,
            "root": self.root.as_posix(),
            "createdAt": catalog.get("generatedAt") or _now(),
            "count": len(entries),
            "digest": _digest_entries(entries),
            "entries": entries,
        }
        errors = validate_baseline_snapshot(snapshot, self.root)
        if errors:
            raise DynamicBaselineError(errors[0])
        return snapshot, templates

    def __call__(self, event: dict[str, Any], *, _lifecycle_guarded: bool = False) -> dict[str, Any]:
        decision = event.get("decision")
        review_root = Path(str(event.get("reviewRoot", ""))).resolve()
        if not isinstance(decision, dict) or decision.get("verdict") != "pass":
            raise DynamicBaselineError("dynamic_baseline_requires_human_pass")
        public = review_root / "review-package"
        template_file = public / "style-template.json"
        cover_file = public / "cover.png"
        approval_file = review_root / "internal" / "approval-decision-receipt.json"
        if not all(path.is_file() for path in (template_file, cover_file, approval_file)):
            raise DynamicBaselineError("dynamic_baseline_source_missing")
        template = read_json(template_file)
        key = decision.get("templateKey")
        revision = decision.get("revision")
        if template.get("key") != key or not isinstance(revision, int):
            raise DynamicBaselineError("dynamic_baseline_source_identity_mismatch")
        if not _lifecycle_guarded:
            with self.approval_guard(str(key)):
                return self(event, _lifecycle_guarded=True)
        template_digest = sha256_file(template_file)
        cover_digest = sha256_file(cover_file)
        target = self.root / key / str(revision)
        with _lock(self.lock_file):
            catalog = self._read_catalog()
            existing = next((
                item for item in catalog["items"]
                if item.get("key") == key and item.get("revision") == revision
            ), None)
            if existing is not None:
                if existing.get("templateSha256") != template_digest or existing.get("effectSha256") != cover_digest:
                    raise DynamicBaselineError("dynamic_baseline_identity_conflict")
            else:
                if target.exists():
                    target_template = target / "package/style-template.json"
                    target_cover = target / "package/cover.png"
                    if (
                        not target_template.is_file()
                        or not target_cover.is_file()
                        or sha256_file(target_template) != template_digest
                        or sha256_file(target_cover) != cover_digest
                    ):
                        raise DynamicBaselineError("dynamic_baseline_target_conflict")
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = Path(tempfile.mkdtemp(prefix=f".{revision}-baseline-", dir=target.parent))
                    try:
                        package = temporary / "package"
                        internal = temporary / "internal"
                        package.mkdir()
                        internal.mkdir()
                        shutil.copy2(template_file, package / "style-template.json")
                        shutil.copy2(cover_file, package / "cover.png")
                        shutil.copy2(approval_file, internal / "approval-decision-receipt.json")
                        manifest = {
                            "artifactType": "style_template_catalog_entry",
                            "schemaVersion": "1.0.0",
                            "producer": PRODUCER,
                            "generatedAt": _now(),
                            "status": "approved",
                            "stage": "dynamic-human-pass",
                            "templateKey": key,
                            "revision": revision,
                            "approvalProvenance": "direct-human-pass",
                            "artifacts": [
                                {"path": "package/style-template.json", "sha256": template_digest},
                                {"path": "package/cover.png", "sha256": cover_digest},
                                {"path": "internal/approval-decision-receipt.json", "sha256": sha256_file(approval_file)},
                            ],
                        }
                        atomic_write_json(temporary / "artifact-manifest.json", manifest)
                        os.replace(temporary, target)
                    except Exception:
                        shutil.rmtree(temporary, ignore_errors=True)
                        raise
                data_root = _data_root(self.root)
                item = {
                    "id": f"{key}-r{revision}",
                    "key": key,
                    "title": template["title"],
                    "revision": revision,
                    "verdict": "pass",
                    "approvalProvenance": "direct-human-pass",
                    "ossStatus": "awaiting-finalization",
                    "template": (target / "package/style-template.json").relative_to(self.root).as_posix(),
                    "effectImage": (target / "package/cover.png").relative_to(self.root).as_posix(),
                    "templateSha256": template_digest,
                    "effectSha256": cover_digest,
                    "cover": template.get("cover"),
                    "approvalEvidence": _relative_or_absolute(approval_file, data_root),
                    "sourcePackage": _relative_or_absolute(public, data_root),
                }
                catalog["items"].append(item)
                catalog["items"].sort(key=lambda value: (value["key"], value["revision"]))
                catalog["generatedAt"] = _now()
                catalog["templateCount"] = len(catalog["items"])
                catalog["effectImageCount"] = len(catalog["items"])
                provenance = catalog.setdefault("approvalProvenanceCounts", {})
                provenance["direct-human-pass"] = sum(
                    value.get("approvalProvenance") == "direct-human-pass" for value in catalog["items"]
                )
                oss_counts = catalog.setdefault("ossStatusCounts", {})
                for status in ("finalized", "awaiting-finalization"):
                    oss_counts[status] = sum(value.get("ossStatus") == status for value in catalog["items"])
                atomic_write_json(self.catalog_file, catalog)
            mirror = self.root / (
                "已通过模板清单.json" if self.catalog_file.name == "统一通过模板索引.json" else "统一通过模板索引.json"
            )
            atomic_write_json(mirror, catalog)
            snapshot, _ = self.load_active()
        return {
            "catalog": self.catalog_file.as_posix(),
            "catalogDigest": sha256_file(self.catalog_file),
            "activeRevision": max(
                item["revision"] for item in self._read_catalog()["items"] if item.get("key") == key
            ),
            "baselineCount": snapshot["count"],
            "idempotent": existing is not None,
        }
