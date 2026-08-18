#!/usr/bin/env python3
"""Regression tests for exact visual revision approval and compilation freeze."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from validate_approved_variants import validate


PROMPT = (
    "只使用用户上传图这一张图片作为唯一图片输入和唯一内容来源。默认保留全部显著主体，每个主体逐一对应用户图中的原主体，保留身份、发型、服装、配饰、手持物和关键关系。"
    "基础主体不复制、不合并、不删减、不增殖；本模板允许以来源轮廓组织连续色块。输出画幅方向与宽高比跟随用户上传图。"
    "将全部目标画面完整重建为柔边平涂与连续空间结构，保持来源主体完整。"
    "只生成用户内容与授权结构；模板未授权的主体、物件和关系属于越权新增。原照片像素必须完全消失。"
)


class ApprovedVariantSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cover = self.root / "selected.png"
        Image.new("RGB", (32, 32), (210, 120, 40)).save(self.cover)
        cover_hash = hashlib.sha256(self.cover.read_bytes()).hexdigest()
        prompt_hash = hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()
        self.approval = {
            "artifactType": "style_template_visual_gate_decision",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer@4.3.0",
            "deliverySetId": "fixture-set",
            "approvalRevision": 1,
            "decisionAuthority": "user_attached_selection",
            "approvedCount": 1,
            "selectionEvidence": [{"matchedKey": "fixture-style", "matchedCover": "selected.png"}],
            "decisions": [{
                "index": 1,
                "key": "fixture-style",
                "cover": "selected.png",
                "testAssetId": "fixture-asset",
                "verdict": "pass",
            }],
        }
        self.compilation = {
            "artifactType": "style_template_approved_compilation_spec",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer@4.3.0",
            "deliverySetId": "fixture-set",
            "approvalRevision": 1,
            "finalizationAuthorization": "user_requested_approved_final_packages",
            "templateCount": 1,
            "templates": [{
                "index": 1,
                "key": "fixture-style",
                "selectedVariant": "pre-overview-first-pass",
                "variantNote": "用户选中总览前首版，已重新冻结机制。",
                "selectedCover": "selected.png",
                "selectedCoverSha256": cover_hash,
                "testAssetId": "fixture-asset",
                "x": "柔边平涂",
                "y": "连续色块场",
                "b": "来源轮廓绑定",
                "c": "主体完整",
                "promptTemplate": PROMPT,
                "promptSha256": prompt_hash,
            }],
        }
        self.approval_file = self.root / "approval.json"
        self.compilation_file = self.root / "compilation.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self) -> None:
        self.approval_file.write_text(json.dumps(self.approval, ensure_ascii=False), encoding="utf-8")
        self.compilation_file.write_text(json.dumps(self.compilation, ensure_ascii=False), encoding="utf-8")

    def test_exact_variant_gate_passes_complete_binding(self) -> None:
        self.write()
        self.assertEqual(validate(self.approval_file, self.compilation_file), [])

    def test_exact_variant_gate_rejects_cover_hash_drift(self) -> None:
        self.compilation["templates"][0]["selectedCoverSha256"] = "0" * 64
        self.write()
        self.assertTrue(any("selectedCoverSha256" in error for error in validate(self.approval_file, self.compilation_file)))

    def test_exact_variant_gate_rejects_prompt_hash_drift(self) -> None:
        self.compilation["templates"][0]["promptSha256"] = "0" * 64
        self.write()
        self.assertTrue(any("promptSha256" in error for error in validate(self.approval_file, self.compilation_file)))

    def test_exact_variant_gate_rejects_approval_cover_mismatch(self) -> None:
        self.approval["decisions"][0]["cover"] = "retry.png"
        self.write()
        self.assertTrue(any("selectedCover" in error for error in validate(self.approval_file, self.compilation_file)))

    def test_exact_variant_gate_requires_variant_note(self) -> None:
        self.compilation["templates"][0]["variantNote"] = ""
        self.write()
        self.assertTrue(any("variantNote" in error for error in validate(self.approval_file, self.compilation_file)))


if __name__ == "__main__":
    unittest.main()
