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
    "只使用用户上传图这一张图片作为唯一图片输入和唯一内容来源。保留全部显著主体与主体集合；全部显著主体逐一对应用户图中的原主体，未经本提示词明确授权，不复制、不合并、不删减、不增殖人物、动物、物体或其关联物；每个呈现实例持续保留身份、面部与体型、轮廓、发型、花纹配色、服装、配饰、手持物和关键关系。输出画幅方向与宽高比跟随用户上传图。"
    "本模板仅改变绘制语言与材质表现，保留主体形态、姿态与视角、呈现实例、环境和构图。"
    "将全部目标画面完整重绘为高反射抛光铬材质：连续圆润曲面概括形体，宽阔高光与深色反射带塑造体积，柔和接触阴影稳定空间，所有区域使用同一非摄影成像。"
    "只生成用户内容和明确授权的变换；模板未授权的新主体、物件、关系或可读文字均为越权新增。"
    "原照片像素、写实皮肤、真实毛发、摄影景深、镜头光照和滤镜式叠加痕迹必须完全消失。"
)

STRUCTURED_PROMPT = (
    PROMPT.replace(
        "本模板仅改变绘制语言与材质表现，保留主体形态、姿态与视角、呈现实例、环境和构图。",
        "本模板允许将主体派生为多个新动作和局部放大实例，重建环境并重组构图；固定使用 CRT 扫描屏、3–6 个复古系统浮窗、菜单栏和图表面板。",
    )
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
                "hint": "上传一张想要重新设计的图片",
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

    def test_accepts_authorized_structured_reconstruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = STRUCTURED_PROMPT
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

    def test_rejects_weak_prompt_without_prompt_only_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = "把图片做成好看的铬金属艺术风格。"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("promptTemplate 缺少" in error for error in errors))

    def test_rejects_prompt_that_preserves_photographic_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = PROMPT + "保留原照片作为底图，再叠加颗粒和手绘笔触。"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("保留摄影底图" in error for error in errors))

    def test_rejects_prompt_without_source_frame_inheritance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = PROMPT.replace(
                "输出画幅方向与宽高比跟随用户上传图。", ""
            )
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("画幅继承要求" in error for error in errors))

    def test_rejects_prompt_without_subject_feature_continuity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = PROMPT.replace("发型、花纹配色、服装、配饰、手持物和", "")
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("主体特征连续性" in error for error in errors))

    def test_rejects_prompt_without_subject_instance_control(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = PROMPT.replace(
                "全部显著主体逐一对应用户图中的原主体，未经本提示词明确授权，不复制、不合并、不删减、不增殖人物、动物、物体或其关联物；",
                "全部显著主体保持可识别；",
            )
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("主体逐一对应与实例控制" in error for error in errors))

    def test_rejects_prompt_without_transformation_permission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = PROMPT.replace("本模板仅改变", "将画面转换为")
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("变换权限声明" in error for error in errors))

    def test_rejects_legacy_dual_image_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = PROMPT + "第 1 张图片仅作为风格参考。"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("禁止参考图依赖" in error for error in errors))

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
