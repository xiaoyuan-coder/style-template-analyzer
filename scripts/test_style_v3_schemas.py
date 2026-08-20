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

from style_baseline import build_baseline_snapshot
from style_test_pool import TestImagePool, normalize_asset
from test_validate_style_template import template


class V3SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contracts = Path(__file__).parents[1] / "contracts"

    def validate(self, filename: str, value: object) -> None:
        schema = json.loads((self.contracts / filename).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(value)

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
        self.validate("test-image-assignment.schema.json", assignment)
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


if __name__ == "__main__":
    unittest.main()
