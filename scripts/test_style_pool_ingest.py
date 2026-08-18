#!/usr/bin/env python3
"""Tests for collected-image download, hashing, and pool admission."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from style_pool_ingest import ingest_records, load_existing_assets
from style_test_pool import TestImagePool, TestPoolError


def jpeg_fixture(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (640, 512), color).save(buffer, format="JPEG")
    return buffer.getvalue()


class PoolIngestTests(unittest.TestCase):
    def test_downloaded_photo_is_fingerprinted_saved_and_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool = TestImagePool()
            record = {
                "sourceAdapter": "wikimedia-commons-html",
                "sourcePageUrl": "https://commons.wikimedia.org/wiki/File:Fixture.jpg",
                "imageUrl": "https://upload.wikimedia.org/fixture.jpg",
                "author": "Fixture Author",
                "license": "CC0",
                "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
                "photographic": True,
                "photographicEvidence": "人工 fixture 确认真实摄影",
                "category": "object",
                "riskLabels": [],
            }
            results = ingest_records(
                [record], root / "assets", pool,
                fetcher=lambda _: jpeg_fixture((200, 40, 20)),
                collected_at="2026-08-17T00:00:00Z",
            )
            self.assertEqual(results[0]["status"], "accepted")
            self.assertEqual(pool.assets[0]["status"], "ready")
            self.assertEqual(len(pool.assets[0]["sha256"]), 64)
            self.assertEqual(len(pool.assets[0]["perceptualHash"]), 16)
            self.assertTrue(Path(pool.assets[0]["localPath"]).is_file())

    def test_unconfirmed_photo_remains_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            record = {
                "sourceAdapter": "wikimedia-commons-html",
                "sourcePageUrl": "https://commons.wikimedia.org/wiki/File:Fixture.jpg",
                "imageUrl": "https://upload.wikimedia.org/fixture.jpg",
                "author": "Fixture Author",
                "license": "CC0",
                "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
                "category": "unclassified",
            }
            pool = TestImagePool()
            ingest_records([record], Path(directory), pool, fetcher=lambda _: jpeg_fixture((10, 20, 30)))
            self.assertEqual(pool.assets[0]["status"], "manual_review")

    def test_visual_person_detection_overrides_non_people_metadata_category(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            record = {
                "sourceAdapter": "loc-free-to-use",
                "sourcePageUrl": "https://www.loc.gov/pictures/item/fixture/",
                "imageUrl": "https://tile.loc.gov/fixture.jpg",
                "author": "Library of Congress",
                "license": "Public Domain",
                "licenseUrl": "https://www.loc.gov/free-to-use/",
                "photographic": True,
                "photographicEvidence": "metadata",
                "category": "nature_outdoor",
                "riskLabels": [],
            }
            pool = TestImagePool()
            ingest_records(
                [record], Path(directory) / "assets", pool,
                fetcher=lambda _: jpeg_fixture((10, 20, 30)),
                visual_classifier=lambda _payload, _record: {
                    "photographic": True,
                    "photographicEvidence": "视觉模型确认真实摄影并检测到可识别人物",
                    "category": "nature_outdoor",
                    "riskLabels": ["identifiable-person-rights-unknown"],
                },
            )
            self.assertEqual(pool.assets[0]["status"], "manual_review")
            self.assertIn("identifiable-person-rights-unknown", pool.assets[0]["riskLabels"])

    def test_asset_checkpoint_reuses_completed_download(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / "asset-checkpoint.json"
            record = {
                "sourceAdapter": "fixture",
                "sourcePageUrl": "https://example.test/source",
                "imageUrl": "https://example.test/image.jpg",
                "author": "Fixture",
                "license": "CC0",
                "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
                "photographic": True,
                "photographicEvidence": "fixture",
                "category": "object",
                "riskLabels": [],
            }
            calls = 0
            def fetcher(_url: str) -> bytes:
                nonlocal calls
                calls += 1
                return jpeg_fixture((80, 90, 100))
            first_pool = TestImagePool()
            first = ingest_records(
                [record], root / "assets", first_pool,
                fetcher=fetcher, asset_checkpoint_file=checkpoint,
            )
            second_pool = TestImagePool()
            second = ingest_records(
                [record], root / "assets", second_pool,
                fetcher=fetcher, asset_checkpoint_file=checkpoint,
            )
            self.assertEqual(calls, 1)
            self.assertEqual(first[0]["status"], "accepted")
            self.assertTrue(second[0]["idempotent"])
            self.assertEqual(second_pool.assets[0]["assetId"], first_pool.assets[0]["assetId"])

    def test_unknown_pool_major_is_rejected_before_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pool_file = Path(directory) / "pool.json"
            pool_file.write_text(json.dumps({
                "artifactType": "style_test_image_pool",
                "schemaVersion": "99.0.0",
                "producer": "style-template-analyzer",
                "assets": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(TestPoolError, "contract_version_unsupported"):
                load_existing_assets(pool_file)


if __name__ == "__main__":
    unittest.main()
