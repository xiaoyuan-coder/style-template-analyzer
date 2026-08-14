#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("migrate_prompt_only.py")
SPEC = importlib.util.spec_from_file_location("migrate_prompt_only", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)

LEGACY_PROMPT = (
    "以第 2 张图片（用户上传图）作为唯一内容来源，保持其中全部主体、数量、身份、姿态、轮廓、物件关系、文字、场景、视角、画幅与构图。"
    "第 1 张图片仅作为风格参考，把第 2 张图片的全部可见区域完整重绘为粗线网点漫画效果：粗黑轮廓、规则圆点和有限原色色盘。"
    "全部可见区域统一执行。"
    "严禁复制第 1 张图片中的女性宇航员、头盔与星空；不得新增用户图中不存在的主体、道具、装饰或文字。"
    "原照片像素、写实皮肤、真实毛发、摄影景深和镜头光照必须完全消失。"
)

PROMPT_ONLY_070 = (
    "只使用用户上传图这一张图片作为唯一图片输入和唯一内容来源，保持其中全部主体、数量、身份、姿态、表情、轮廓、内部特征、物件关系、文字、场景、视角、画幅与构图。"
    "输出画幅方向与宽高比跟随用户上传图。"
    "把用户上传图的全部可见区域完整重绘为体素积木塑形效果：所有边缘由像素阶梯和立方体接缝构成。"
    "全部可见区域统一执行。"
    "只重绘用户上传图中已有内容，不生成额外主体、道具、装饰、边框、容器或可读文字。"
    "原照片像素、写实皮肤、真实毛发、摄影景深和镜头光照必须完全消失。"
)


class MigrationTests(unittest.TestCase):
    def test_migrates_dual_image_prompt_without_reference_content(self) -> None:
        prompt = MODULE.migrate_prompt(LEGACY_PROMPT)
        self.assertIn("唯一图片输入和唯一内容来源", prompt)
        self.assertIn("画幅方向与宽高比跟随用户上传图", prompt)
        self.assertIn("粗黑轮廓、规则圆点和有限原色色盘", prompt)
        self.assertIn("发型、花纹配色、服装、配饰、手持物", prompt)
        self.assertIn("逐一对应用户图中的原主体", prompt)
        self.assertIn("不复制、不合并、不删减、不增殖", prompt)
        self.assertIn("本模板仅改变绘制语言", prompt)
        self.assertIn("模板未授权", prompt)
        self.assertIn("越权新增", prompt)
        self.assertNotIn("第 1 张", prompt)
        self.assertNotIn("第 2 张", prompt)
        self.assertNotIn("女性宇航员", prompt)
        self.assertNotIn("参考图", prompt)

    def test_migrates_photographic_salvage_sentence(self) -> None:
        legacy = LEGACY_PROMPT.replace(
            "全部可见区域统一执行。",
            "参考图中的摄影成像只用于观测上述色彩、边缘、纹理和空间算子；将这些算子扩展为覆盖主体、背景、文字、边缘和角落的完整非摄影成像。",
        )
        prompt = MODULE.migrate_prompt(legacy)
        self.assertIn("上述风格算子扩展为覆盖主体、背景、文字、边缘和角落", prompt)
        self.assertNotIn("参考图", prompt)

    def test_upgrades_existing_prompt_only_070_contract(self) -> None:
        prompt = MODULE.migrate_prompt(PROMPT_ONLY_070)
        self.assertIn("全部显著主体", prompt)
        self.assertIn("发型、花纹配色、服装、配饰、手持物", prompt)
        self.assertIn("逐一对应用户图中的原主体", prompt)
        self.assertIn("不复制、不合并、不删减、不增殖", prompt)
        self.assertIn("本模板允许执行且仅执行下文明确写出", prompt)
        self.assertIn("模板未授权", prompt)
        self.assertIn("越权新增", prompt)
        self.assertIn("体素积木塑形", prompt)
        self.assertNotIn("第 1 张", prompt)
        self.assertNotIn("参考图", prompt)

    def test_reupgrades_prompt_only_without_duplicate_contract_sentences(self) -> None:
        prompt = MODULE.migrate_prompt(MODULE.migrate_prompt(PROMPT_ONLY_070))
        self.assertEqual(prompt.count("逐一对应用户图中的原主体"), 1)
        self.assertEqual(prompt.count("本模板允许执行且仅执行"), 1)

    def test_rejects_unknown_dual_image_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "不符合受支持的双图开头"):
            MODULE.migrate_prompt("第 1 张图控制风格，第 2 张图控制内容。")

    def test_copies_template_and_retargets_local_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = root / "source-batch"
            asset = batch / "01-input" / "style.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"image")
            template_dir = batch / "02-data" / "0001"
            template_dir.mkdir(parents=True)
            data = {
                "key": "comic-dot",
                "cover": "../../01-input/style.png",
                "promptTemplate": LEGACY_PROMPT,
            }
            source_file = template_dir / "style-template.json"
            source_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            output = root / "output"
            summary = MODULE.migrate_directory(batch / "02-data", output)
            migrated_file = output / "0001" / "style-template.json"
            migrated = json.loads(migrated_file.read_text(encoding="utf-8"))
            self.assertEqual(summary["templates"], 1)
            self.assertTrue((migrated_file.parent / migrated["cover"]).resolve().is_file())
            self.assertNotIn("referenceImage", migrated)
            self.assertNotIn("第 1 张", migrated["promptTemplate"])


if __name__ == "__main__":
    unittest.main()
