#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("validate_style_template.py")
SPEC = importlib.util.spec_from_file_location("validate_style_template", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


PROMPT = (
    "以第 2 张图片（用户上传图）作为唯一内容来源，保持其中主体、数量、身份、姿态、轮廓、物件关系、视角与构图。"
    "第 1 张图片仅作为风格参考，把第 2 张图片完整重绘为高反射抛光铬材质：使用连续圆润曲面、宽阔高光、深色反射带和柔和接触阴影塑造体积，全部可见区域统一执行。"
    "严禁复制第 1 张图片中的气球、人物、道具、场景、文字、品牌、边框和装饰；不得新增用户图中不存在的主体或可读文字。"
    "原照片像素、写实皮肤、真实毛发、摄影景深、镜头光照、照片噪声和滤镜式处理痕迹必须完全消失，结果必须保持用户上传内容可识别。"
)


def template(asset: str = "./style.png") -> dict:
    return {
        "key": "high-gloss-chrome-rendering",
        "title": "高光镜面塑形",
        "description": "以高反射镜面、宽阔高光和圆润块面重绘你的图片",
        "kind": "STYLE_REF",
        "cover": asset,
        "referenceImage": asset,
        "imageSize": "1024x1024",
        "imageN": 1,
        "promptTemplate": PROMPT,
        "inputSchema": [
            {
                "type": "image",
                "id": "source",
                "label": "你的原图",
                "hint": "上传一张想要转换风格的图片",
                "required": True,
                "maxCount": 1,
                "private": False,
            }
        ],
        "preprocessSteps": [],
        "metadata": {
            "sourceRef": {
                "producerKey": "high-gloss-chrome-rendering",
                "styleAsset": "风格化素材/0001.png",
                "taxonomyVersion": "2.0",
            }
        },
    }


class ValidatorTests(unittest.TestCase):
    def test_valid_local_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(MODULE.validate_data(data, file, "local", "", ""), [])

    def test_accepts_managed_remote_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "style-template.json"
            url = "https://assets.example.com/dev/style/templates/00000000-0000-4000-8000-000000000000.png"
            errors = MODULE.validate_data(
                template(url), file, "remote", "assets.example.com", "dev/"
            )
            self.assertEqual(errors, [])

    def test_rejects_old_analysis_fields_in_runtime_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["supportedModes"] = ["whole_image", "subject_only"]
            data["styleInstruction"] = "旧分析字段"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("不允许的最终交付字段" in error for error in errors))

    def test_rejects_missing_local_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "style-template.json"
            errors = MODULE.validate_data(template(), file, "local", "", "")
            self.assertTrue(any("本地图片不存在" in error for error in errors))

    def test_rejects_weak_prompt_without_reference_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = "把图片做成好看的铬金属艺术风格。"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("promptTemplate 缺少" in error for error in errors))

    def test_rejects_incorrect_input_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["inputSchema"][0]["id"] = "subject"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("inputSchema" in error for error in errors))

    def test_rejects_source_ref_key_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["metadata"]["sourceRef"]["producerKey"] = "other-key"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("producerKey" in error for error in errors))

    def test_accepts_optional_metadata_tags_without_top_level_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["metadata"]["tags"] = []
            self.assertEqual(MODULE.validate_data(data, file, "local", "", ""), [])
            data["tags"] = ["镜面"]
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("不允许的最终交付字段" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
