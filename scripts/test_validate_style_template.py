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


STYLE_INSTRUCTION = (
    "内容权限：当前输入图是主体、物件、场景、文字、视角和构图的唯一来源，保持本次模式范围内的身份、数量、姿态、轮廓、遮挡和空间关系。"
    "成像媒介：把全部可见区域完整重建为高反射抛光铬材质，让反射参与体积塑造。"
    "形体与细节：保留输入结构，以圆润连续曲面概括细小表面纹理。"
    "线条与边缘：外轮廓清晰，内部结构由反射边界和高光转折界定。"
    "笔触与纹理：表面光滑，无纸纹、颗粒和手绘笔触。"
    "色彩组织：中性银灰占主导，输入环境色只作为受控反射色带出现。"
    "明暗与空间：宽阔高光、深色反射带和柔和接触阴影建立体积，保持输入视角和布局。"
    "覆盖要求：主体、背景、文字、界面、边缘和角落统一重建，不保留原始哑光表面或未处理照片区域。"
    "去摄影化：全部可见区域以目标媒介重新构成，原照片像素、摄影皮肤、真实毛发、镜头景深、原始镜头光照和照片噪声必须完全消失。"
)


def template(asset: str = "./style.png") -> dict:
    return {
        "schemaVersion": "1.0",
        "taxonomyVersion": "2.0",
        "key": "high-gloss-chrome-rendering",
        "title": "高光镜面塑形",
        "description": "以高反射镜面、宽阔高光和圆润块面重绘输入内容",
        "category": {
            "primary": "material-3d",
            "secondary": "chrome-inflatable-sculpture",
            "displayName": "材质立体",
        },
        "displayCategory": "材质立体",
        "referenceType": "single-style-reference",
        "referenceStructure": "single-style-reference",
        "supportedModes": ["whole_image", "subject_only"],
        "contentScope": "adaptive",
        "contentStrategy": "full_scene_preservation",
        "modeInstructions": {
            "whole_image": "保留整张输入画布的全部内容、文字、UI、布局与空间关系，并统一应用模板风格。",
            "subject_only": "只提取并风格化主要主体，移除原背景和其他非主体内容，使用均匀纯白背景。",
        },
        "referenceAssets": {"style": asset},
        "styleInstruction": STYLE_INSTRUCTION,
        "contentExclusion": "参考内容禁迁移清单：具体气球、人物、道具、场景、服饰、姿势、文字、品牌、边框和装饰。以上内容不得影响裁切或构图，不要新增输入图不存在的物件或可读文字。",
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

    def test_rejects_shallow_unstructured_style_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "style.png"
            asset.write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["styleInstruction"] = "把人物画成太空角色，加入星星和几何边框，使用漫画感与复古感。"
            data["contentExclusion"] = "不要复制具体人物、文字、品牌和背景故事。"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("强制风格结构" in error for error in errors))
            self.assertTrue(any("参考内容禁迁移清单" in error for error in errors))

    def test_rejects_photographic_target_category(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "style.png"
            asset.write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["category"] = {
                "primary": "photographic-look",
                "secondary": "nostalgic-film",
                "displayName": "摄影质感",
            }
            data["displayCategory"] = "摄影质感"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("八类体系" in error for error in errors))

    def test_rejects_false_pass_below_ninety(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["style.png", "input.png", "output.png"]:
                (root / name).write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["needsReview"] = False
            data["testAssets"] = {"input": "./input.png", "output": "./output.png"}
            data["styleEvaluation"] = {
                "score": 89,
                "verdict": "pass",
                "hardFailures": [],
                "dimensionScores": {
                    "imagingMedium": 18,
                    "marksAndTexture": 18,
                    "colorOrganization": 14,
                    "linesAndEdges": 14,
                    "shapeAndDetail": 9,
                    "toneAndSpace": 8,
                    "globalCoverage": 8,
                },
                "evidence": "完成了跨主体生成，但风格还原分数仍低于本轮验收门槛。",
            }
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("score >= 90" in error for error in errors))

    def test_rejects_hard_failure_with_nonzero_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "style.png"
            asset.write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["styleEvaluation"] = {
                "score": 50,
                "verdict": "fail",
                "hardFailures": ["摄影介质残留"],
                "dimensionScores": {
                    "imagingMedium": 0,
                    "marksAndTexture": 10,
                    "colorOrganization": 10,
                    "linesAndEdges": 10,
                    "shapeAndDetail": 5,
                    "toneAndSpace": 5,
                    "globalCoverage": 10,
                },
                "evidence": "主体仍保留明显摄影毛发和镜头虚化，只叠加了浅色颗粒。",
            }
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("score 必须为 0" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
