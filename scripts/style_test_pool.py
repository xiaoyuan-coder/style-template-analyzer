#!/usr/bin/env python3
"""Rights-aware real-photo pool and stable delivery-set assignment ledger."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

from PIL import Image
from jsonschema import Draft202012Validator

from style_contracts import sha256_file
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


AUTO_READY_LICENSES = {"CC0", "PUBLIC DOMAIN", "PDM", "PEXELS LICENSE"}
HIGH_RISK_LABELS = {
    "identifiable-person-rights-unknown",
    "license-unknown",
    "trademark-sensitive",
    "weapon-sensitive",
    "sexual-content",
    "hate-symbol",
    "watermark-detected",
}


class TestPoolError(ValueError):
    """Machine-readable pool failure."""


def _validate_contract(data: object, schema_name: str, invalid_code: str) -> None:
    if isinstance(data, dict):
        version = data.get("schemaVersion")
        if isinstance(version, str) and version.count(".") == 2:
            try:
                major = int(version.split(".", 1)[0])
            except ValueError:
                pass
            else:
                if major > 1:
                    raise TestPoolError("contract_version_unsupported")
    schema_file = Path(__file__).parents[1] / "contracts" / schema_name
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    if schema_name == "test-image-assignment-ledger.schema.json":
        assignment_schema = json.loads(
            (schema_file.parent / "test-image-assignment.schema.json").read_text(encoding="utf-8")
        )
        schema["properties"]["assignments"]["items"] = assignment_schema
    if list(Draft202012Validator(schema).iter_errors(data)):
        raise TestPoolError(invalid_code)


def validate_pool_document(data: object) -> None:
    _validate_contract(data, "test-image-pool.schema.json", "test_pool_invalid")


def _valid_hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value.lower())


def hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def normalize_asset(raw: dict[str, Any]) -> dict[str, Any]:
    required = {
        "assetId", "sourceAdapter", "sourcePageUrl", "imageUrl", "author", "license",
        "licenseUrl", "rightsStatus", "collectedAt", "mime", "width", "height", "sha256",
        "perceptualHash", "photographic", "riskLabels", "category",
        "photographicEvidence", "localPath",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise TestPoolError(f"test_asset_invalid: missing={','.join(missing)}")
    if not _valid_hex(raw["sha256"], 64) or not _valid_hex(raw["perceptualHash"], 16):
        raise TestPoolError("test_asset_invalid: hash")
    if raw["mime"] not in {"image/jpeg", "image/png", "image/webp"}:
        raise TestPoolError("test_asset_invalid: mime")
    if not isinstance(raw["width"], int) or not isinstance(raw["height"], int) or min(raw["width"], raw["height"]) < 512:
        raise TestPoolError("test_asset_invalid: dimensions")
    for field in ("assetId", "sourceAdapter", "author", "license", "category", "photographicEvidence"):
        if not isinstance(raw[field], str) or not raw[field].strip():
            raise TestPoolError(f"test_asset_invalid: {field}")
    for field in ("sourcePageUrl", "imageUrl", "licenseUrl"):
        parsed = urlparse(str(raw[field]))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise TestPoolError(f"test_asset_invalid: {field}")
    try:
        datetime.fromisoformat(str(raw["collectedAt"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise TestPoolError("test_asset_invalid: collectedAt") from error
    if not isinstance(raw.get("riskLabels"), list) or not all(isinstance(item, str) for item in raw["riskLabels"]):
        raise TestPoolError("test_asset_invalid: riskLabels")
    local_path = Path(str(raw["localPath"]))
    local_verified = local_path.is_file() and sha256_file(local_path) == raw["sha256"]
    if local_verified:
        try:
            with Image.open(local_path) as image:
                image.verify()
                expected_mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(image.format)
                local_verified = expected_mime == raw["mime"] and image.size == (raw["width"], raw["height"])
        except OSError:
            local_verified = False
    risks = set(raw.get("riskLabels", []))
    license_name = str(raw["license"]).upper()
    auto_ready = (
        raw.get("rightsStatus") == "verified"
        and raw.get("photographic") is True
        and local_verified
        and license_name in AUTO_READY_LICENSES
        and not risks.intersection(HIGH_RISK_LABELS)
    )
    result = dict(raw)
    result["status"] = "ready" if auto_ready else "manual_review"
    result["orientation"] = (
        "square" if raw["width"] == raw["height"] else "landscape" if raw["width"] > raw["height"] else "portrait"
    )
    return result


@dataclass
class TestImagePool:
    assets: list[dict[str, Any]] = field(default_factory=list)
    assignments: list[dict[str, Any]] = field(default_factory=list)
    near_duplicate_threshold: int = 5

    def __post_init__(self) -> None:
        initial = list(self.assets)
        self.assets = []
        for asset in initial:
            self.add(asset)
        self._validate_assignments()

    def add(self, asset: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_asset(asset)
        for current in self.assets:
            if current["assetId"] == normalized["assetId"]:
                raise TestPoolError("duplicate_asset_id")
            if current["sha256"] == normalized["sha256"]:
                raise TestPoolError("duplicate_exact")
            if hamming_distance(current["perceptualHash"], normalized["perceptualHash"]) <= self.near_duplicate_threshold:
                raise TestPoolError("duplicate_perceptual")
            cluster = normalized.get("semanticClusterId")
            if cluster and cluster == current.get("semanticClusterId"):
                raise TestPoolError("duplicate_semantic")
        self.assets.append(normalized)
        return normalized

    def ready_distribution(self) -> dict[str, Any]:
        ready = [asset for asset in self.assets if asset["status"] == "ready"]
        total = len(ready)
        categories = Counter(asset["category"] for asset in ready)
        sources = Counter(asset["sourceAdapter"] for asset in ready)
        historical_or_bw = sum(
            asset.get("visualEra") == "historical" or asset.get("colorMode") == "black-and-white"
            for asset in ready
        )
        museum = sum(asset.get("plainMuseumObject") is True for asset in ready)
        return {
            "ready": total,
            "categories": dict(categories),
            "sources": dict(sources),
            "maxCategoryShare": max(categories.values(), default=0) / total if total else 0.0,
            "maxSourceShare": max(sources.values(), default=0) / total if total else 0.0,
            "historicalOrBlackWhiteShare": historical_or_bw / total if total else 0.0,
            "plainMuseumObjectShare": museum / total if total else 0.0,
        }

    def capacity(self, delivery_set_id: str) -> int:
        used = {item["assetId"] for item in self.assignments if item["deliverySetId"] == delivery_set_id}
        return sum(asset["status"] == "ready" and asset["assetId"] not in used for asset in self.assets)

    def assign(self, delivery_set_id: str, template_key: str, revision: int) -> dict[str, Any]:
        assignment = self.reserve(delivery_set_id, template_key, revision)
        return self.commit(delivery_set_id, template_key, revision)

    def reserve(self, delivery_set_id: str, template_key: str, revision: int) -> dict[str, Any]:
        for item in self.assignments:
            if (item["deliverySetId"], item["templateKey"], item["revision"]) == (delivery_set_id, template_key, revision):
                return dict(item)
        used = {item["assetId"] for item in self.assignments if item["deliverySetId"] == delivery_set_id}
        available = [asset for asset in self.assets if asset["status"] == "ready" and asset["assetId"] not in used]
        if not available:
            raise TestPoolError("test_pool_insufficient")
        chosen = sorted(available, key=lambda item: (item["category"], item["orientation"], item["assetId"]))[0]
        assignment = {
            "artifactType": "test_image_assignment",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "deliverySetId": delivery_set_id,
            "templateKey": template_key,
            "revision": revision,
            "assetId": chosen["assetId"],
            "assignedAt": datetime.now(timezone.utc).isoformat(),
            "status": "reserved",
        }
        self.assignments.append(assignment)
        return dict(assignment)

    def commit(self, delivery_set_id: str, template_key: str, revision: int) -> dict[str, Any]:
        for item in self.assignments:
            if (item["deliverySetId"], item["templateKey"], item["revision"]) == (delivery_set_id, template_key, revision):
                item["status"] = "committed"
                return dict(item)
        raise TestPoolError("test_assignment_missing")

    def release(self, delivery_set_id: str, template_key: str, revision: int) -> None:
        self.assignments = [
            item for item in self.assignments
            if (item["deliverySetId"], item["templateKey"], item["revision"])
            != (delivery_set_id, template_key, revision) or item.get("status") == "committed"
        ]

    def asset(self, asset_id: str) -> dict[str, Any]:
        for asset in self.assets:
            if asset["assetId"] == asset_id:
                current = normalize_asset(asset)
                if current["status"] != "ready":
                    raise TestPoolError("test_asset_not_ready")
                return current
        raise TestPoolError("test_asset_not_ready")

    def save(self, pool_file: Path, ledger_file: Path) -> None:
        self._save_pool_persisted(pool_file)
        self._mutate_persisted(ledger_file, lambda: None)

    def _save_pool_persisted(self, pool_file: Path) -> None:
        """Merge pool additions under a sidecar lock before atomic replace."""
        import fcntl

        pool_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file = pool_file.with_suffix(pool_file.suffix + ".lock")
        with lock_file.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            latest_data = json.loads(pool_file.read_text(encoding="utf-8")) if pool_file.is_file() else None
            if latest_data is not None:
                validate_pool_document(latest_data)
            latest = latest_data.get("assets", []) if isinstance(latest_data, dict) else []
            merged = TestImagePool(latest, near_duplicate_threshold=self.near_duplicate_threshold)
            by_id = {asset["assetId"]: asset for asset in merged.assets}
            for asset in self.assets:
                current = by_id.get(asset["assetId"])
                if current is not None:
                    if current["sha256"] != asset["sha256"]:
                        raise TestPoolError("duplicate_asset_id")
                    continue
                added = merged.add(asset)
                by_id[added["assetId"]] = added
            self.assets = merged.assets
            self._atomic_write(pool_file, {
                "artifactType": "style_test_image_pool",
                "schemaVersion": "1.1.0",
                "producer": "style-template-analyzer",
                "assets": self.assets,
            })

    @staticmethod
    def _atomic_write(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def _mutate_persisted(self, ledger_file: Path, operation: Any) -> Any:
        import fcntl

        ledger_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file = ledger_file.with_suffix(ledger_file.suffix + ".lock")
        with lock_file.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if ledger_file.is_file():
                ledger_data = json.loads(ledger_file.read_text(encoding="utf-8"))
                _validate_contract(
                    ledger_data,
                    "test-image-assignment-ledger.schema.json",
                    "assignment_ledger_invalid",
                )
                self.assignments = ledger_data.get("assignments", [])
                self._validate_assignments()
            result = operation()
            self._atomic_write(ledger_file, {
                "artifactType": "test_image_assignment_ledger",
                "schemaVersion": "1.0.0",
                "producer": "style-template-analyzer",
                "assignments": self.assignments,
            })
            return result

    def _validate_assignments(self) -> None:
        identities: set[tuple[str, str, int]] = set()
        assets: set[tuple[str, str]] = set()
        for item in self.assignments:
            _validate_contract(item, "test-image-assignment.schema.json", "assignment_ledger_invalid")
            try:
                identity = (item["deliverySetId"], item["templateKey"], item["revision"])
                asset = (item["deliverySetId"], item["assetId"])
            except (KeyError, TypeError) as error:
                raise TestPoolError("assignment_ledger_invalid") from error
            if identity in identities or asset in assets:
                raise TestPoolError("assignment_ledger_invalid")
            identities.add(identity)
            assets.add(asset)

    def reserve_persisted(self, delivery_set_id: str, template_key: str, revision: int, ledger_file: Path) -> dict[str, Any]:
        return self._mutate_persisted(ledger_file, lambda: self.reserve(delivery_set_id, template_key, revision))

    def refresh_persisted(self, ledger_file: Path) -> None:
        self._mutate_persisted(ledger_file, lambda: None)

    def commit_persisted(self, delivery_set_id: str, template_key: str, revision: int, ledger_file: Path) -> dict[str, Any]:
        return self._mutate_persisted(ledger_file, lambda: self.commit(delivery_set_id, template_key, revision))

    def mark_publishing_persisted(self, delivery_set_id: str, template_key: str, revision: int, ledger_file: Path) -> dict[str, Any]:
        def mark() -> dict[str, Any]:
            for item in self.assignments:
                if (item["deliverySetId"], item["templateKey"], item["revision"]) == (delivery_set_id, template_key, revision):
                    item["status"] = "publishing"
                    return dict(item)
            raise TestPoolError("test_assignment_missing")
        return self._mutate_persisted(ledger_file, mark)

    def release_persisted(self, delivery_set_id: str, template_key: str, revision: int, ledger_file: Path) -> None:
        self._mutate_persisted(ledger_file, lambda: self.release(delivery_set_id, template_key, revision))

    def reconcile_persisted(self, assignment: dict[str, Any], ledger_file: Path) -> dict[str, Any]:
        def reconcile() -> dict[str, Any]:
            expected = (assignment["deliverySetId"], assignment["templateKey"], assignment["revision"])
            existing = [
                item for item in self.assignments
                if (item["deliverySetId"], item["templateKey"], item["revision"]) == expected
            ]
            if existing:
                if existing[0]["assetId"] != assignment["assetId"]:
                    raise TestPoolError("test_asset_already_assigned")
                if assignment.get("status") == "committed" and existing[0].get("status") in {"reserved", "publishing"}:
                    existing[0]["status"] = "committed"
                return dict(existing[0])
            if any(
                item["deliverySetId"] == assignment["deliverySetId"] and item["assetId"] == assignment["assetId"]
                for item in self.assignments
            ):
                raise TestPoolError("test_asset_already_assigned")
            self.assignments.append(dict(assignment))
            return dict(assignment)
        return self._mutate_persisted(ledger_file, reconcile)

    def assign_persisted(
        self,
        delivery_set_id: str,
        template_key: str,
        revision: int,
        ledger_file: Path,
    ) -> dict[str, Any]:
        """Serialize assignment updates through a stable sidecar lock and atomic replace."""
        assignment = self.reserve_persisted(delivery_set_id, template_key, revision, ledger_file)
        return self.commit_persisted(delivery_set_id, template_key, revision, ledger_file)

    @classmethod
    def load(cls, pool_file: Path, ledger_file: Path) -> "TestImagePool":
        pool_data = json.loads(pool_file.read_text(encoding="utf-8"))
        ledger_data = json.loads(ledger_file.read_text(encoding="utf-8")) if ledger_file.is_file() else {"assignments": []}
        validate_pool_document(pool_data)
        if ledger_file.is_file():
            _validate_contract(
                ledger_data,
                "test-image-assignment-ledger.schema.json",
                "assignment_ledger_invalid",
            )
        pool = cls(pool_data["assets"], ledger_data["assignments"])
        return pool
