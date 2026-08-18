#!/usr/bin/env python3
"""Tests for approved baselines, test assets, and stable assignments."""

from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from style_baseline import build_baseline_snapshot, validate_baseline_snapshot
from style_test_pool import (
    TestImagePool,
    TestPoolError,
    normalize_asset,
)
from test_validate_style_template import template


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ApprovedBaselineTests(unittest.TestCase):
    def test_snapshot_is_deterministic_and_validates_declared_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(2):
                item = root / f"item-{index}"
                item.mkdir()
                data = template()
                data["key"] = f"sample-style-{index}"
                data["title"] = f"样式{index + 1}号"
                data["metadata"]["sourceRef"]["producerKey"] = data["key"]
                (item / "style.png").write_bytes(b"image")
                write_json(item / "style-template.json", data)
            first = build_baseline_snapshot(root, approved_count=2, created_at="2026-08-17T00:00:00Z")
            second = build_baseline_snapshot(root, approved_count=2, created_at="2026-08-17T00:00:00Z")
            self.assertEqual(first["digest"], second["digest"])
            self.assertEqual(validate_baseline_snapshot(first, root), [])
            first["count"] = 3
            self.assertIn("baseline_count_mismatch", validate_baseline_snapshot(first, root))

            first["schemaVersion"] = "99.0.0"
            self.assertEqual(validate_baseline_snapshot(first, root), ["failed: contract_version_unsupported"])

    def test_snapshot_rejects_duplicate_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("a", "b"):
                item = root / name
                item.mkdir()
                (item / "style.png").write_bytes(b"image")
                write_json(item / "style-template.json", template())
            with self.assertRaisesRegex(ValueError, "baseline_duplicate_key"):
                build_baseline_snapshot(root, approved_count=2)


class TestImagePoolTests(unittest.TestCase):
    def asset(self, asset_id: str, digest: str, perceptual_hash: str) -> dict[str, object]:
        local_path = Path(tempfile.gettempdir()) / f"style-v3-foundation-{asset_id}.jpg"
        Image.new("RGB", (640, 512), (ord(digest[0]) % 255, 40, 80)).save(local_path, format="JPEG")
        return normalize_asset({
            "assetId": asset_id,
            "sourceAdapter": "fixture",
            "sourcePageUrl": f"https://example.test/{asset_id}",
            "imageUrl": f"https://example.test/{asset_id}.jpg",
            "author": "Fixture Author",
            "license": "CC0",
            "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
            "rightsStatus": "verified",
            "collectedAt": "2026-08-17T00:00:00Z",
            "mime": "image/jpeg",
            "width": 640,
            "height": 512,
            "sha256": hashlib.sha256(local_path.read_bytes()).hexdigest(),
            "perceptualHash": perceptual_hash,
            "photographic": True,
            "photographicEvidence": "测试 fixture 确认摄影图",
            "riskLabels": [],
            "category": "object",
            "localPath": local_path.as_posix(),
        })

    def test_rights_gate_and_dedup(self) -> None:
        first = self.asset("asset-a", "a" * 64, "0" * 16)
        self.assertEqual(first["status"], "ready")
        review = dict(first, assetId="asset-b", license="CC BY-SA 4.0")
        self.assertEqual(normalize_asset(review)["status"], "manual_review")
        pexels = dict(
            first,
            assetId="asset-pexels",
            sourceAdapter="pexels-sitemap-manual",
            license="Pexels License",
            licenseUrl="https://www.pexels.com/license/",
        )
        self.assertEqual(normalize_asset(pexels)["status"], "ready")
        pool = TestImagePool([first])
        with self.assertRaisesRegex(TestPoolError, "duplicate_exact"):
            pool.add(self.asset("asset-c", "a" * 64, "f" * 16))

    def test_semantic_cluster_blocks_visually_repetitive_sequence(self) -> None:
        first = dict(self.asset("asset-a", "a" * 64, "0" * 16), semanticClusterId="same-cat-session")
        second = dict(self.asset("asset-b", "b" * 64, "f" * 16), semanticClusterId="same-cat-session")
        pool = TestImagePool([first])
        with self.assertRaisesRegex(TestPoolError, "duplicate_semantic"):
            pool.add(second)

    def test_ready_distribution_reports_source_and_visual_concentration(self) -> None:
        first = dict(
            self.asset("asset-a", "a" * 64, "0" * 16),
            sourceAdapter="loc-free-to-use-bulk", visualEra="historical", colorMode="black-and-white",
        )
        second = dict(
            self.asset("asset-b", "b" * 64, "f" * 16),
            sourceAdapter="loc-free-to-use-bulk", visualEra="contemporary", colorMode="color",
        )
        distribution = TestImagePool([first, second]).ready_distribution()
        self.assertEqual(distribution["maxSourceShare"], 1.0)
        self.assertEqual(distribution["historicalOrBlackWhiteShare"], 0.5)

    def test_assignment_is_unique_idempotent_and_capacity_checked(self) -> None:
        pool = TestImagePool([
            self.asset("asset-a", "a" * 64, "0" * 16),
            self.asset("asset-b", "b" * 64, "f" * 16),
        ])
        first = pool.assign("delivery-1", "template-a", 1)
        again = pool.assign("delivery-1", "template-a", 1)
        second = pool.assign("delivery-1", "template-b", 1)
        self.assertEqual(first, again)
        self.assertNotEqual(first["assetId"], second["assetId"])
        with self.assertRaisesRegex(TestPoolError, "test_pool_insufficient"):
            pool.assign("delivery-1", "template-c", 1)

    def test_reassigning_same_template_requires_new_revision(self) -> None:
        pool = TestImagePool([
            self.asset("asset-a", "a" * 64, "0" * 16),
            self.asset("asset-b", "b" * 64, "f" * 16),
        ])
        old = pool.assign("delivery-1", "template-a", 1)
        new = pool.assign("delivery-1", "template-a", 2)
        self.assertNotEqual(old["assetId"], new["assetId"])

    def test_persisted_reservations_are_unique_across_pool_instances(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.json"
            assets = [
                self.asset("asset-a", "a" * 64, "0" * 16),
                self.asset("asset-b", "b" * 64, "f" * 16),
            ]
            first = TestImagePool(assets).reserve_persisted("delivery-1", "template-a", 1, ledger)
            second = TestImagePool(assets).reserve_persisted("delivery-1", "template-b", 1, ledger)
            self.assertNotEqual(first["assetId"], second["assetId"])

    def test_stale_pool_saves_merge_instead_of_losing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool_file = root / "pool.json"
            ledger_file = root / "ledger.json"
            first = TestImagePool([self.asset("asset-a", "a" * 64, "0" * 16)])
            stale_second = TestImagePool([self.asset("asset-b", "b" * 64, "f" * 16)])

            first.save(pool_file, ledger_file)
            stale_second.save(pool_file, ledger_file)

            saved = TestImagePool.load(pool_file, ledger_file)
            self.assertEqual({asset["assetId"] for asset in saved.assets}, {"asset-a", "asset-b"})

    def test_persistent_pool_and_ledger_enforce_contract_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool_file = root / "pool.json"
            ledger_file = root / "ledger.json"
            TestImagePool([self.asset("asset-a", "a" * 64, "0" * 16)]).save(pool_file, ledger_file)

            pool_data = json.loads(pool_file.read_text(encoding="utf-8"))
            pool_data["schemaVersion"] = "99.0.0"
            write_json(pool_file, pool_data)
            with self.assertRaisesRegex(TestPoolError, "contract_version_unsupported"):
                TestImagePool.load(pool_file, ledger_file)

            pool_data["schemaVersion"] = "1.0.0"
            write_json(pool_file, pool_data)
            ledger_data = json.loads(ledger_file.read_text(encoding="utf-8"))
            ledger_data["producer"] = "wrong"
            write_json(ledger_file, ledger_data)
            with self.assertRaisesRegex(TestPoolError, "assignment_ledger_invalid"):
                TestImagePool.load(pool_file, ledger_file)


if __name__ == "__main__":
    unittest.main()
