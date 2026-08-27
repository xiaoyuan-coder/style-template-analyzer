#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from audit_approved_after_gate import audit_catalog
from test_validate_style_template import template


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ApprovedAfterGateAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.approved = self.data / "05-风格化模板生产" / "04-研发交付" / "已通过正式模板包"
        self.revision = self.approved / "fixture-style" / "1"
        self.template_file = self.revision / "package" / "style-template.json"
        self.effect_file = self.revision / "package" / "cover.png"
        self.source_file = self.data / "06-模板质量评测" / "02-标准测试集" / "pool" / "source.jpg"
        self.source_file.parent.mkdir(parents=True, exist_ok=True)
        self.effect_file.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (800, 400), "white").save(self.source_file, format="JPEG")
        Image.new("RGB", (400, 800), "white").save(self.effect_file, format="PNG")
        data = template("https://assets.memebuy.cn/style/templates/123e4567-e89b-42d3-a456-426614174000.png")
        data["key"] = "fixture-style"
        data["metadata"]["sourceRef"]["producerKey"] = "fixture-style"
        write_json(self.template_file, data)
        self.prompt_sha = hashlib.sha256(data["promptTemplate"].encode()).hexdigest()
        write_json(self.revision / "internal" / "test-image-assignment.json", {
            "assetId": "asset-1",
        })
        write_json(self.revision / "internal" / "approval-decision-receipt.json", {
            "verdict": "pass",
            "authority": "human",
            "promptSha256": self.prompt_sha,
            "coverSha256": digest(self.effect_file),
            "assetId": "asset-1",
        })
        write_json(self.data / "06-模板质量评测" / "02-标准测试集" / "pool" / "pool.json", {
            "assets": [{
                "assetId": "asset-1",
                "localPath": self.source_file.as_posix(),
                "sha256": digest(self.source_file),
            }]
        })
        self.catalog = self.approved / "统一通过模板索引.json"
        write_json(self.catalog, {"items": [{
            "key": "fixture-style",
            "title": "fixture",
            "revision": 1,
            "approvalProvenance": "direct-human-pass",
            "ossStatus": "finalized",
            "template": "fixture-style/1/package/style-template.json",
            "effectImage": "fixture-style/1/package/cover.png",
            "templateSha256": digest(self.template_file),
            "effectSha256": digest(self.effect_file),
            "approvalEvidence": "fixture-style/1/internal/approval-decision-receipt.json",
            "sourcePackage": "fixture-style/1/package",
        }]})

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def report(self) -> dict:
        return audit_catalog(
            self.catalog,
            self.data,
            self.data / "06-模板质量评测" / "02-标准测试集",
        )

    def test_legacy_package_requires_replay_and_contract(self) -> None:
        item = self.report()["items"][0]
        codes = {issue["code"] for issue in item["issues"]}
        self.assertEqual(item["gateStatus"], "known-boundary-or-prompt-drift")
        self.assertIn("GENERATION_RECEIPT_V2_MISSING", codes)
        self.assertIn("EFFECT_CONTRACT_MISSING", codes)
        self.assertIn("FRAME_BOUNDARY_CONFLICT", codes)

    def test_catalog_hash_drift_is_integrity_blocked(self) -> None:
        data = json.loads(self.catalog.read_text())
        data["items"][0]["effectSha256"] = "0" * 64
        write_json(self.catalog, data)
        item = self.report()["items"][0]
        self.assertEqual(item["gateStatus"], "blocked-evidence-recovery")
        self.assertTrue(any(issue["code"] == "CATALOG_EFFECT_HASH_MISMATCH" for issue in item["issues"]))


if __name__ == "__main__":
    unittest.main()
