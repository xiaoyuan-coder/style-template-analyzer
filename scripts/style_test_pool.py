#!/usr/bin/env python3
"""Read-only high-recognition pool adapter and stable assignment ledger."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

from PIL import Image
from jsonschema import Draft202012Validator

from style_atomic import atomic_write_json
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
                supported_major = {
                    "test-image-pool.schema.json": 2,
                    "test-image-assignment.schema.json": 3,
                    "test-image-assignment-v2.schema.json": 2,
                    "test-image-assignment-ledger.schema.json": 3,
                }.get(schema_name, 1)
                if major > supported_major:
                    raise TestPoolError("contract_version_unsupported")
    schema_file = Path(__file__).parents[1] / "contracts" / schema_name
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    if schema_name == "test-image-assignment-ledger.schema.json":
        schema["properties"]["assignments"]["items"] = {"type": "object"}
    if list(Draft202012Validator(schema).iter_errors(data)):
        raise TestPoolError(invalid_code)
    if schema_name == "test-image-assignment-ledger.schema.json" and isinstance(data, dict):
        for assignment in data.get("assignments", []):
            version = assignment.get("schemaVersion") if isinstance(assignment, dict) else None
            assignment_schema = {
                "1.0.0": "test-image-assignment-v1.schema.json",
                "2.0.0": "test-image-assignment-v2.schema.json",
                "3.0.0": "test-image-assignment.schema.json",
            }.get(str(version), "test-image-assignment.schema.json")
            _validate_contract(assignment, assignment_schema, invalid_code)


def validate_pool_document(data: object) -> None:
    _validate_contract(data, "test-image-pool.schema.json", "test_pool_invalid")


def _valid_hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value.lower())


def hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def normalize_asset(raw: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw.get("recognitionAnchor"), dict):
        required = {
            "assetId", "sourcePageUrl", "imageUrl", "collectedAt", "mime", "width",
            "height", "sha256", "perceptualHash", "category", "localPath", "orientation",
            "status", "recognitionAnchor",
        }
        missing = sorted(required - set(raw))
        if missing:
            raise TestPoolError(f"test_asset_invalid: missing={','.join(missing)}")
        if not _valid_hex(raw["sha256"], 64) or not _valid_hex(raw["perceptualHash"], 16):
            raise TestPoolError("test_asset_invalid: hash")
        if raw["mime"] not in {"image/jpeg", "image/png", "image/webp"}:
            raise TestPoolError("test_asset_invalid: mime")
        if not isinstance(raw["width"], int) or not isinstance(raw["height"], int) or min(raw["width"], raw["height"]) < 128:
            raise TestPoolError("test_asset_invalid: dimensions")
        if raw.get("status") != "ready":
            raise TestPoolError("test_asset_invalid: status")
        for field in ("assetId", "category"):
            if not isinstance(raw[field], str) or not raw[field].strip():
                raise TestPoolError(f"test_asset_invalid: {field}")
        for field in ("sourcePageUrl", "imageUrl"):
            parsed = urlparse(str(raw[field]))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise TestPoolError(f"test_asset_invalid: {field}")
        try:
            datetime.fromisoformat(str(raw["collectedAt"]).replace("Z", "+00:00"))
        except ValueError as error:
            raise TestPoolError("test_asset_invalid: collectedAt") from error
        local_path = Path(str(raw["localPath"]))
        if not local_path.is_file() or sha256_file(local_path) != raw["sha256"]:
            raise TestPoolError("test_asset_invalid: localPath")
        try:
            with Image.open(local_path) as image:
                image.verify()
                expected_mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(image.format)
                if expected_mime != raw["mime"] or image.size != (raw["width"], raw["height"]):
                    raise TestPoolError("test_asset_invalid: localImage")
        except OSError as error:
            raise TestPoolError("test_asset_invalid: localImage") from error
        return dict(raw)

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
        blocked = {item["assetId"] for item in self.assignments if self._blocks_asset(item)}
        catalog_ready = [asset for asset in self.assets if asset["status"] == "ready"]
        ready = [asset for asset in catalog_ready if asset["assetId"] not in blocked]
        total = len(ready)
        categories = Counter(asset["category"] for asset in ready)
        sources = Counter(
            asset.get("sourceAdapter")
            or f"recognition:{asset.get('recognitionAnchor', {}).get('kind', 'other')}"
            for asset in ready
        )
        historical_or_bw = sum(
            asset.get("visualEra") == "historical" or asset.get("colorMode") == "black-and-white"
            for asset in ready
        )
        museum = sum(asset.get("plainMuseumObject") is True for asset in ready)
        return {
            "ready": total,
            "catalogReady": len(catalog_ready),
            "occupied": len(blocked),
            "legacyHeld": len({
                item["assetId"] for item in self.assignments
                if item.get("schemaVersion") == "1.0.0" and self._blocks_asset(item)
            }),
            "consumed": len({
                item["assetId"] for item in self.assignments
                if item.get("schemaVersion") == "2.0.0" and item.get("status") == "consumed"
            }),
            "categories": dict(categories),
            "sources": dict(sources),
            "maxCategoryShare": max(categories.values(), default=0) / total if total else 0.0,
            "maxSourceShare": max(sources.values(), default=0) / total if total else 0.0,
            "historicalOrBlackWhiteShare": historical_or_bw / total if total else 0.0,
            "plainMuseumObjectShare": museum / total if total else 0.0,
        }

    @staticmethod
    def _blocks_asset(item: dict[str, Any]) -> bool:
        if item.get("schemaVersion") == "1.0.0":
            return item.get("status") in {"reserved", "publishing", "committed"}
        return item.get("status") in {"reserved", "awaiting_approval", "consumed"}

    def _unavailable_asset_ids(self, delivery_set_id: str | None = None) -> set[str]:
        return {
            item["assetId"]
            for item in self.assignments
            if self._blocks_asset(item)
            or (delivery_set_id is not None and item.get("deliverySetId") == delivery_set_id)
        }

    def capacity(self, delivery_set_id: str | None = None) -> int:
        """Return ready assets after global occupancy and delivery-set history are applied."""
        used = self._unavailable_asset_ids(delivery_set_id)
        return sum(asset["status"] == "ready" and asset["assetId"] not in used for asset in self.assets)

    def assign(self, delivery_set_id: str, template_key: str, revision: int) -> dict[str, Any]:
        """Compatibility alias for reserving; review readiness requires explicit evidence."""
        return self.reserve(delivery_set_id, template_key, revision)

    def reserve(
        self,
        delivery_set_id: str,
        template_key: str,
        revision: int,
        *,
        legacy: bool = False,
    ) -> dict[str, Any]:
        for item in self.assignments:
            if (item["deliverySetId"], item["templateKey"], item["revision"]) == (delivery_set_id, template_key, revision):
                decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
                if (
                    item.get("schemaVersion") == "2.0.0"
                    and item.get("status") == "released"
                    and decision.get("verdict") == "system_failure"
                ):
                    item["status"] = "reserved"
                    item["assignedAt"] = datetime.now(timezone.utc).isoformat()
                    item.pop("decision", None)
                    item.pop("reviewReadyAt", None)
                return dict(item)
        used = self._unavailable_asset_ids(delivery_set_id)
        available = [asset for asset in self.assets if asset["status"] == "ready" and asset["assetId"] not in used]
        if not available:
            raise TestPoolError("test_pool_insufficient")
        chosen = sorted(available, key=lambda item: (item["category"], item["orientation"], item["assetId"]))[0]
        assignment = {
            "artifactType": "test_image_assignment",
            "schemaVersion": "1.0.0" if legacy else "2.0.0",
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

    def _assignment(self, delivery_set_id: str, template_key: str, revision: int) -> dict[str, Any]:
        for item in self.assignments:
            if (item["deliverySetId"], item["templateKey"], item["revision"]) == (
                delivery_set_id,
                template_key,
                revision,
            ):
                if item.get("schemaVersion") != "2.0.0":
                    raise TestPoolError("legacy_assignment_migration_required")
                return item
        raise TestPoolError("test_assignment_missing")

    def mark_awaiting_approval(
        self,
        delivery_set_id: str,
        template_key: str,
        revision: int,
        *,
        review_ready_at: str | None = None,
    ) -> dict[str, Any]:
        item = self._assignment(delivery_set_id, template_key, revision)
        if item["status"] == "awaiting_approval":
            return dict(item)
        if item["status"] != "reserved":
            raise TestPoolError("test_assignment_transition_invalid")
        item["status"] = "awaiting_approval"
        item["reviewReadyAt"] = review_ready_at or datetime.now(timezone.utc).isoformat()
        return dict(item)

    def consume(
        self,
        delivery_set_id: str,
        template_key: str,
        revision: int,
        *,
        cover_sha256: str,
        prompt_sha256: str,
        reason: str,
        decided_at: str | None = None,
    ) -> dict[str, Any]:
        item = self._assignment(delivery_set_id, template_key, revision)
        if item["status"] == "consumed":
            return dict(item)
        if item["status"] != "awaiting_approval":
            raise TestPoolError("test_assignment_transition_invalid")
        item["status"] = "consumed"
        item["decision"] = {
            "verdict": "pass",
            "authority": "human",
            "decidedAt": decided_at or datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "coverSha256": cover_sha256,
            "promptSha256": prompt_sha256,
        }
        return dict(item)

    def commit(self, delivery_set_id: str, template_key: str, revision: int) -> dict[str, Any]:
        for item in self.assignments:
            if (item["deliverySetId"], item["templateKey"], item["revision"]) == (
                delivery_set_id,
                template_key,
                revision,
            ):
                if item.get("schemaVersion") != "1.0.0":
                    raise TestPoolError("test_assignment_transition_invalid")
                item["status"] = "committed"
                return dict(item)
        raise TestPoolError("test_assignment_missing")

    def mark_publishing(self, delivery_set_id: str, template_key: str, revision: int) -> dict[str, Any]:
        for item in self.assignments:
            if (item["deliverySetId"], item["templateKey"], item["revision"]) == (
                delivery_set_id,
                template_key,
                revision,
            ):
                if item.get("schemaVersion") != "1.0.0":
                    raise TestPoolError("test_assignment_transition_invalid")
                item["status"] = "publishing"
                return dict(item)
        raise TestPoolError("test_assignment_missing")

    def release(
        self,
        delivery_set_id: str,
        template_key: str,
        revision: int,
        *,
        verdict: str | None = None,
        reason: str | None = None,
        authority: str = "human",
        decided_at: str | None = None,
        cover_sha256: str | None = None,
        prompt_sha256: str | None = None,
    ) -> dict[str, Any]:
        legacy_item = next((
            item for item in self.assignments
            if (item["deliverySetId"], item["templateKey"], item["revision"])
            == (delivery_set_id, template_key, revision)
            and item.get("schemaVersion") == "1.0.0"
        ), None)
        if legacy_item is not None:
            if legacy_item.get("status") == "committed":
                return dict(legacy_item)
            self.assignments.remove(legacy_item)
            return dict(legacy_item)
        item = self._assignment(delivery_set_id, template_key, revision)
        if item["status"] == "released":
            return dict(item)
        allowed = (
            item["status"] == "reserved" and authority == "system" and verdict == "system_failure"
        ) or (
            item["status"] == "awaiting_approval"
            and authority == "human"
            and verdict in {"reject", "manual_release"}
        )
        if not allowed:
            raise TestPoolError("explicit_human_release_required")
        item["status"] = "released"
        decision: dict[str, Any] = {
            "verdict": verdict,
            "authority": authority,
            "decidedAt": decided_at or datetime.now(timezone.utc).isoformat(),
            "reason": reason or "explicit release",
        }
        if cover_sha256 is not None:
            decision["coverSha256"] = cover_sha256
        if prompt_sha256 is not None:
            decision["promptSha256"] = prompt_sha256
        item["decision"] = decision
        return dict(item)

    def retire_template(
        self,
        template_key: str,
        *,
        reason: str,
        decided_at: str | None = None,
    ) -> list[dict[str, Any]]:
        if not reason.strip():
            raise TestPoolError("retirement_reason_required")
        released: list[dict[str, Any]] = []
        for item in self.assignments:
            if item.get("templateKey") != template_key or item.get("status") == "released":
                continue
            if item.get("schemaVersion") not in {"1.0.0", "2.0.0", "3.0.0"}:
                raise TestPoolError("legacy_assignment_migration_required")
            previous_decision = item.get("decision")
            item["schemaVersion"] = "3.0.0"
            item["status"] = "released"
            item["decision"] = {
                "verdict": "template_retired",
                "authority": "human",
                "decidedAt": decided_at or datetime.now(timezone.utc).isoformat(),
                "reason": reason.strip(),
            }
            if isinstance(previous_decision, dict):
                item["previousDecision"] = previous_decision
            released.append(dict(item))
        return released

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
                if latest_data.get("schemaVersion") in {"2.0.0", "2.1.0"}:
                    raise TestPoolError("upstream_test_image_pool_is_read_only")
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
            if any(isinstance(asset.get("recognitionAnchor"), dict) for asset in self.assets):
                raise TestPoolError("high_recognition_pool_requires_screening_provenance")
            atomic_write_json(pool_file, {
                "artifactType": "style_test_image_pool",
                "schemaVersion": "1.1.0",
                "producer": "style-template-analyzer",
                "assets": self.assets,
            })

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
            atomic_write_json(ledger_file, {
                "artifactType": "test_image_assignment_ledger",
                "schemaVersion": "3.0.0",
                "producer": "style-template-analyzer",
                "assignments": self.assignments,
            })
            return result

    def _validate_assignments(self) -> None:
        identities: set[tuple[str, str, int]] = set()
        legacy_assets = {
            item.get("assetId") for item in self.assignments
            if item.get("schemaVersion") == "1.0.0" and self._blocks_asset(item)
        }
        current_assets: set[str] = set()
        for item in self.assignments:
            schema_name = {
                "1.0.0": "test-image-assignment-v1.schema.json",
                "2.0.0": "test-image-assignment-v2.schema.json",
                "3.0.0": "test-image-assignment.schema.json",
            }.get(str(item.get("schemaVersion")), "test-image-assignment.schema.json")
            _validate_contract(item, schema_name, "assignment_ledger_invalid")
            try:
                identity = (item["deliverySetId"], item["templateKey"], item["revision"])
                asset = item["assetId"]
            except (KeyError, TypeError) as error:
                raise TestPoolError("assignment_ledger_invalid") from error
            if identity in identities:
                raise TestPoolError("assignment_ledger_invalid")
            identities.add(identity)
            if item.get("schemaVersion") in {"2.0.0", "3.0.0"} and self._blocks_asset(item):
                if asset in current_assets or asset in legacy_assets:
                    raise TestPoolError("assignment_ledger_invalid")
                current_assets.add(asset)

    def reserve_persisted(
        self,
        delivery_set_id: str,
        template_key: str,
        revision: int,
        ledger_file: Path,
        *,
        legacy: bool = False,
    ) -> dict[str, Any]:
        return self._mutate_persisted(
            ledger_file,
            lambda: self.reserve(delivery_set_id, template_key, revision, legacy=legacy),
        )

    def refresh_persisted(self, ledger_file: Path) -> None:
        self._mutate_persisted(ledger_file, lambda: None)

    def commit_persisted(self, delivery_set_id: str, template_key: str, revision: int, ledger_file: Path) -> dict[str, Any]:
        return self._mutate_persisted(
            ledger_file,
            lambda: self.commit(delivery_set_id, template_key, revision),
        )

    def mark_publishing_persisted(self, delivery_set_id: str, template_key: str, revision: int, ledger_file: Path) -> dict[str, Any]:
        return self._mutate_persisted(
            ledger_file,
            lambda: self.mark_publishing(delivery_set_id, template_key, revision),
        )

    def mark_awaiting_approval_persisted(
        self,
        delivery_set_id: str,
        template_key: str,
        revision: int,
        ledger_file: Path,
        *,
        review_ready_at: str | None = None,
    ) -> dict[str, Any]:
        return self._mutate_persisted(
            ledger_file,
            lambda: self.mark_awaiting_approval(
                delivery_set_id,
                template_key,
                revision,
                review_ready_at=review_ready_at,
            ),
        )

    def consume_persisted(
        self,
        delivery_set_id: str,
        template_key: str,
        revision: int,
        ledger_file: Path,
        **decision: Any,
    ) -> dict[str, Any]:
        return self._mutate_persisted(
            ledger_file,
            lambda: self.consume(delivery_set_id, template_key, revision, **decision),
        )

    def release_persisted(
        self,
        delivery_set_id: str,
        template_key: str,
        revision: int,
        ledger_file: Path,
        **decision: Any,
    ) -> dict[str, Any]:
        return self._mutate_persisted(
            ledger_file,
            lambda: self.release(delivery_set_id, template_key, revision, **decision),
        )

    def retire_template_persisted(
        self,
        template_key: str,
        ledger_file: Path,
        *,
        reason: str,
        decided_at: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._mutate_persisted(
            ledger_file,
            lambda: self.retire_template(template_key, reason=reason, decided_at=decided_at),
        )

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
                if existing[0] != assignment:
                    if (
                        assignment.get("schemaVersion") == "1.0.0"
                        and assignment.get("status") == "committed"
                        and existing[0].get("schemaVersion") == "1.0.0"
                        and existing[0].get("status") in {"reserved", "publishing"}
                    ):
                        existing[0]["status"] = "committed"
                    else:
                        raise TestPoolError("test_assignment_state_mismatch")
                return dict(existing[0])
            if assignment["assetId"] in self._unavailable_asset_ids(assignment.get("deliverySetId")):
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
        """Compatibility alias for one persisted reservation."""
        return self.reserve_persisted(delivery_set_id, template_key, revision, ledger_file)

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
