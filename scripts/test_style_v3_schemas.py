#!/usr/bin/env python3
"""Schema examples for v3 internal artifacts."""

from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from PIL import Image
from referencing import Registry, Resource

from style_baseline import build_baseline_snapshot
from style_test_pool import TestImagePool, TestPoolError, normalize_asset
from test_validate_style_template import template


class V3SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contracts = Path(__file__).parents[1] / "contracts"

    def validate(self, filename: str, value: object) -> None:
        self.validator(filename).validate(value)

    def validator(self, filename: str) -> Draft202012Validator:
        schema = json.loads((self.contracts / filename).read_text(encoding="utf-8"))
        assignment_schema = json.loads(
            (self.contracts / "test-image-assignment.schema.json").read_text(encoding="utf-8")
        )
        registry = Registry().with_resource(
            assignment_schema["$id"],
            Resource.from_contents(assignment_schema),
        )
        return Draft202012Validator(schema, registry=registry)

    def asset(self) -> dict:
        local_path = Path(tempfile.gettempdir()) / "style-v3-schema-fixture.jpg"
        Image.new("RGB", (640, 512), (20, 80, 140)).save(local_path, format="JPEG")
        return normalize_asset({
            "assetId": "fixture-asset",
            "sourceAdapter": "fixture",
            "sourcePageUrl": "https://example.test/file",
            "imageUrl": "https://example.test/file.jpg",
            "author": "Fixture Author",
            "license": "CC0",
            "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
            "rightsStatus": "verified",
            "collectedAt": "2026-08-17T00:00:00Z",
            "mime": "image/jpeg",
            "width": 640,
            "height": 512,
            "sha256": hashlib.sha256(local_path.read_bytes()).hexdigest(),
            "perceptualHash": "0" * 16,
            "photographic": True,
            "photographicEvidence": "测试 fixture 确认摄影图",
            "riskLabels": [],
            "category": "object",
            "localPath": local_path.as_posix(),
        })

    def test_pool_assignment_receipt_and_self_production_examples(self) -> None:
        asset = self.asset()
        pool = TestImagePool([asset])
        assignment = pool.assign("delivery-1", "fixture-style", 1)
        self.validate("test-image-assignment-ledger.schema.json", {
            "artifactType": "test_image_assignment_ledger",
            "schemaVersion": "2.0.0",
            "producer": "style-template-analyzer",
            "assignments": [assignment],
        })
        self.validate("test-image-pool.schema.json", {
            "artifactType": "style_test_image_pool",
            "schemaVersion": "1.1.0",
            "producer": "style-template-analyzer",
            "assets": [{
                **asset,
                "semanticClusterId": "fixture-cluster",
                "visualEra": "contemporary",
                "colorMode": "color",
                "plainMuseumObject": False,
            }],
        })
        self.validate("test-image-pool.schema.json", {
            "artifactType": "style_test_image_pool",
            "schemaVersion": "2.1.0",
            "producer": "test-image-pool-curator",
            "generatedAt": "2026-08-21T08:00:00Z",
            "sourceManifest": "/tmp/candidate-manifest.json",
            "decisionLog": "/tmp/screening-decisions.json",
            "assets": [],
        })
        self.validate("test-image-assignment-v2.schema.json", assignment)
        pool.mark_awaiting_approval("delivery-1", "fixture-style", 1)
        pool.consume(
            "delivery-1",
            "fixture-style",
            1,
            cover_sha256="a" * 64,
            prompt_sha256="b" * 64,
            reason="人工通过",
        )
        retired = pool.retire_template("fixture-style", reason="人工退役")[0]
        self.validate("test-image-assignment.schema.json", retired)
        self.validate("test-image-assignment-ledger.schema.json", {
            "artifactType": "test_image_assignment_ledger",
            "schemaVersion": "4.0.0",
            "producer": "style-template-analyzer",
            "assignments": [retired],
        })
        self.assertEqual(retired["previousDecision"]["verdict"], "pass")

        invalid_retired = dict(retired)
        invalid_retired.pop("decision")
        ledger_validator = self.validator("test-image-assignment-ledger.schema.json")
        self.assertFalse(ledger_validator.is_valid({
            "artifactType": "test_image_assignment_ledger",
            "schemaVersion": "4.0.0",
            "producer": "style-template-analyzer",
            "assignments": [invalid_retired],
        }))
        self.assertTrue(ledger_validator.is_valid({
            "artifactType": "test_image_assignment_ledger",
            "schemaVersion": "3.0.0",
            "producer": "style-template-analyzer",
            "assignments": [invalid_retired],
        }))
        self.validate("cover-generation-receipt.schema.json", {
            "artifactType": "cover_generation_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": "fixture-style",
            "revision": 1,
            "assetId": "fixture-asset",
            "provider": {"model": "fake"},
        })
        self.validate("cover-check-receipt.schema.json", {
            "artifactType": "cover_check_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": "fixture-style",
            "revision": 1,
            "verdict": "pass",
            "attempts": [{"attempt": 1, "verdict": "pass", "reasons": []}],
        })
        self.validate("approval-decision-receipt.schema.json", {
            "artifactType": "approval_decision_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "deliverySetId": "delivery-1",
            "templateKey": "fixture-style",
            "revision": 1,
            "assetId": "fixture-asset",
            "verdict": "pass",
            "authority": "human",
            "decidedAt": "2026-08-19T00:00:00Z",
            "reason": "人工验收通过",
            "coverSha256": "a" * 64,
            "promptSha256": "b" * 64,
        })
        self.validate("oss-finalization-receipt.schema.json", {
            "artifactType": "oss_finalization_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": "fixture-style",
            "revision": 1,
            "assetsDomain": "assets.example.com",
            "remoteCoverUrl": "https://assets.example.com/style/templates/123e4567-e89b-42d3-a456-426614174000.png",
            "provider": {"service": "fixture"},
        })
        self.validate("self-production-analysis.schema.json", {
            "artifactType": "self_production_analysis",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": "fixture-style",
            "baselineDigest": "b" * 64,
            "novelty": {"key": "unique", "title": "unique", "promptMechanism": "unique", "category": "distinct"},
        })

    def test_baseline_snapshot_example(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = root / "one"
            item.mkdir()
            (item / "style.png").write_bytes(b"image")
            (item / "style-template.json").write_text(json.dumps(template(), ensure_ascii=False), encoding="utf-8")
            snapshot = build_baseline_snapshot(root, approved_count=1)
            self.validate("baseline-snapshot.schema.json", snapshot)

    def test_current_baseline_approval_shape(self) -> None:
        approval = json.loads((Path(__file__).parents[1] / "references" / "legacy-approved-baseline-94.json").read_text(encoding="utf-8"))
        self.validate("baseline-approval.schema.json", approval)

    def test_dynamic_baseline_pointer_shape(self) -> None:
        pointer = json.loads((Path(__file__).parents[1] / "references" / "dynamic-baseline.json").read_text(encoding="utf-8"))
        self.validate("dynamic-baseline-pointer.schema.json", pointer)

    def test_high_recognition_pool_shape(self) -> None:
        asset_id = "anchor-" + "a" * 20
        event_id = "screen-20260820T080000-1234abcd"
        self.validate("test-image-pool.schema.json", {
            "artifactType": "style_test_image_pool",
            "schemaVersion": "2.0.0",
            "producer": "style-template-analyzer",
            "generatedAt": "2026-08-20T08:00:00Z",
            "sourceManifest": "/tmp/candidate-manifest.json",
            "decisionLog": "/tmp/screening-decisions.json",
            "assets": [{
                "assetId": asset_id,
                "sourcePageUrl": "https://example.test/source",
                "imageUrl": "https://example.test/known.jpg",
                "collectedAt": "2026-08-20T08:00:00Z",
                "mime": "image/jpeg",
                "width": 640,
                "height": 512,
                "sha256": "c" * 64,
                "perceptualHash": "d" * 16,
                "category": "名人梗图",
                "localPath": "/tmp/known.jpg",
                "orientation": "landscape",
                "status": "ready",
                "recognitionAnchor": {
                    "kind": "celebrity-meme",
                    "screenedBy": "human",
                    "screenedAt": "2026-08-20T08:00:00Z",
                    "decisionEventId": event_id,
                    "sourceCandidateIds": ["known"],
                },
            }],
        })

    def test_pool_version_and_producer_are_exactly_bound(self) -> None:
        schema = json.loads((self.contracts / "test-image-pool.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)

        def pool(schema_version: str, producer: str) -> dict:
            return {
                "artifactType": "style_test_image_pool",
                "schemaVersion": schema_version,
                "producer": producer,
                "generatedAt": "2026-08-21T08:00:00Z",
                "sourceManifest": "/tmp/candidate-manifest.json",
                "decisionLog": "/tmp/screening-decisions.json",
                "assets": [],
            }

        self.assertTrue(validator.is_valid(pool("2.0.0", "style-template-analyzer")))
        self.assertTrue(validator.is_valid(pool("2.1.0", "test-image-pool-curator")))
        self.assertFalse(validator.is_valid(pool("2.0.0", "test-image-pool-curator")))
        self.assertFalse(validator.is_valid(pool("2.1.0", "style-template-analyzer")))

    def test_pool_consumer_loads_curator_2_1_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_file = root / "anchor.jpg"
            Image.new("RGB", (640, 512), (90, 120, 160)).save(image_file, format="JPEG")
            pool_file = root / "pool.json"
            ledger_file = root / "assignment-ledger.json"
            pool_file.write_text(json.dumps({
                "artifactType": "style_test_image_pool",
                "schemaVersion": "2.1.0",
                "producer": "test-image-pool-curator",
                "generatedAt": "2026-08-21T08:00:00Z",
                "sourceManifest": "/tmp/candidate-manifest.json",
                "decisionLog": "/tmp/screening-decisions.json",
                "assets": [{
                    "assetId": "anchor-" + "a" * 20,
                    "sourcePageUrl": "https://example.test/source",
                    "imageUrl": "https://example.test/anchor.jpg",
                    "collectedAt": "2026-08-21T08:00:00Z",
                    "mime": "image/jpeg",
                    "width": 640,
                    "height": 512,
                    "sha256": hashlib.sha256(image_file.read_bytes()).hexdigest(),
                    "perceptualHash": "1" * 16,
                    "category": "互联网经典梗图",
                    "localPath": image_file.as_posix(),
                    "orientation": "landscape",
                    "status": "ready",
                    "recognitionAnchor": {
                        "kind": "internet-meme",
                        "screenedBy": "human",
                        "screenedAt": "2026-08-21T08:00:00Z",
                        "decisionEventId": "screen-20260821T080000-1234abcd",
                        "sourceCandidateIds": ["known-scene"],
                    },
                }],
            }, ensure_ascii=False), encoding="utf-8")
            pool = TestImagePool.load(pool_file, ledger_file)
            self.assertEqual(pool.capacity(), 1)
            original_pool = pool_file.read_bytes()
            assignment = pool.reserve_persisted("delivery-1", "internet-meme", 1, ledger_file)
            self.assertEqual(assignment["status"], "reserved")
            self.assertTrue(ledger_file.is_file())
            self.assertEqual(pool_file.read_bytes(), original_pool)
            with self.assertRaisesRegex(TestPoolError, "upstream_test_image_pool_is_read_only"):
                pool.save(pool_file, ledger_file)
            self.assertEqual(pool_file.read_bytes(), original_pool)

    def test_runtime_reads_legacy_v3_ledger_with_historical_loose_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = self.asset()
            pool_file = root / "pool.json"
            pool_file.write_text(json.dumps({
                "artifactType": "style_test_image_pool",
                "schemaVersion": "1.1.0",
                "producer": "style-template-analyzer",
                "assets": [asset],
            }), encoding="utf-8")
            ledger_file = root / "ledger.json"
            ledger_file.write_text(json.dumps({
                "artifactType": "test_image_assignment_ledger",
                "schemaVersion": "3.0.0",
                "producer": "style-template-analyzer",
                "assignments": [{
                    "artifactType": "test_image_assignment",
                    "schemaVersion": "3.0.0",
                    "producer": "style-template-analyzer",
                    "deliverySetId": "legacy-delivery",
                    "templateKey": "legacy-style",
                    "revision": 1,
                    "assetId": asset["assetId"],
                    "assignedAt": "2026-08-21T00:00:00Z",
                    "status": "released",
                }],
            }), encoding="utf-8")

            loaded = TestImagePool.load(pool_file, ledger_file)

            self.assertEqual(loaded.assignment_ledger_version, "3.0.0")
            self.assertEqual(loaded.assignments[0]["status"], "released")


if __name__ == "__main__":
    unittest.main()
