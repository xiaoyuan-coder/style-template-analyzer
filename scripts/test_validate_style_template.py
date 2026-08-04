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


def template(asset: str = "./style.png") -> dict:
    return {
        "schemaVersion": "1.0",
        "taxonomyVersion": "2.0",
        "key": "chrome-balloon-sculpture",
        "title": "镜面气球雕塑",
        "description": "把主体塑造成镜面气球雕塑",
        "category": {
            "primary": "material-3d",
            "secondary": "chrome-inflatable-sculpture",
            "displayName": "材质立体",
        },
        "displayCategory": "材质立体",
        "tags": ["镜面", "气球"],
        "styleTags": ["镜面", "气球"],
        "referenceType": "single-style-reference",
        "referenceStructure": "single-style-reference",
        "supportedModes": ["whole_image", "subject_only"],
        "contentScope": "adaptive",
        "contentStrategy": "primary_subject_reconstruction",
        "modeInstructions": {
            "whole_image": "保留整张输入画布的全部内容、文字、UI、布局与空间关系，并统一应用模板风格。",
            "subject_only": "只提取并风格化主要主体，移除原背景和其他非主体内容，使用均匀纯白背景。",
        },
        "referenceAssets": {"style": asset},
        "styleInstruction": "保持主体身份、数量、姿态和轮廓，将主体重建为圆润的镜面气球雕塑。",
        "contentExclusion": "不要复制参考图中的具体主体、文字、品牌和背景故事。",
        "classificationConfidence": 0.94,
        "needsReview": True,
    }


class ValidatorTests(unittest.TestCase):
    def test_valid_local_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "style.png"
            asset.write_bytes(b"image")
            file = root / "style-template.json"
            file.write_text(json.dumps(template(), ensure_ascii=False), encoding="utf-8")
            data = json.loads(file.read_text(encoding="utf-8"))
            self.assertEqual(MODULE.validate_data(data, file, "local", "", ""), [])

    def test_rejects_taxonomy_and_missing_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "style-template.json"
            data = template()
            data["displayCategory"] = "错误分类"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("displayCategory" in error for error in errors))
            self.assertTrue(any("本地图片不存在" in error for error in errors))

    def test_accepts_managed_remote_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "template.json"
            url = "https://assets.example.com/dev/style/templates/00000000-0000-4000-8000-000000000000.png"
            errors = MODULE.validate_data(
                template(url),
                file,
                "remote",
                "assets.example.com",
                "dev/",
            )
            self.assertEqual(errors, [])

    def test_rejects_single_mode_usable_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "style.png"
            asset.write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["supportedModes"] = ["subject_only"]
            data["contentScope"] = "subject"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("同时支持" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
