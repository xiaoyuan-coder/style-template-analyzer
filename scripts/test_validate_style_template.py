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
    "任务：\n"
    "请以用户上传图为内容依据，从零完整重绘整张画面。\n\n"
    "保留：\n"
    "保留全部显著主体；全部显著主体逐一对应用户图中的原主体，不复制、不合并、不删减、不增殖人物、动物、物体或其关联物。保留身份、面部与体型、轮廓、发型、花纹配色、服装、配饰、手持物和关键关系。\n\n"
    "画面重构：\n"
    "仅改变绘制语言与材质表现，保持主体形态、姿态与视角、环境和构图。\n\n"
    "构图：\n"
    "输出画幅方向与宽高比跟随用户上传图。\n\n"
    "视觉风格：\n"
    "将整张画面重绘为高反射抛光铬材质。用连续圆润曲面概括形体，宽阔高光与深色反射带塑造体积，柔和接触阴影稳定空间。\n\n"
    "限制：\n"
    "不要新增用户图中没有的主体、物件、关系或可读文字。不要保留照片像素、写实皮肤、真实毛发、摄影景深、镜头光照或滤镜叠加痕迹。"
)

STRUCTURED_PROMPT = (
    PROMPT.replace(
        "仅改变绘制语言与材质表现，保持主体形态、姿态与视角、环境和构图。",
        "允许改变主体的呈现次数和视角，将主体拆成多个新动作和局部放大画面，重建环境并重组构图。使用 CRT 扫描屏、3–6 个复古系统浮窗、菜单栏和图表面板。",
    )
)

V2_PROMPT = (
    "任务：\n"
    "以用户上传图为内容依据，从零完整重绘整张图像，生成一幅可直接用于服装印制的镜面块面图案。\n\n"
    "保留：\n"
    "保留全部显著主体并与用户图中的原主体逐一对应；保持身份、发型、服装、配饰、手持物和关键关系。基础主体不复制、不合并、不删减、不增殖。\n\n"
    "变换权限：\n"
    "仅改变绘制语言与材质表现，保持主体形态、姿态、视角、环境和主要构图。\n\n"
    "核心效果：\n"
    "把主体全部重建为连续圆润的高反射镜面块体，以宽阔高光和深色反射带共同塑造体积。\n\n"
    "空间结构：\n"
    "输出画幅方向与宽高比跟随用户上传图；保持原主体位置、尺度、遮挡和前后层级。\n\n"
    "内容映射：\n"
    "用户图中的每个主体和关联物在原位置获得同一镜面材质，轮廓、接触关系和归属保持清楚。\n\n"
    "视觉风格：\n"
    "使用抛光铬金属表面、干净硬边、宽白高光、深灰反射带和柔和接触阴影，整张画面使用一致的非摄影渲染。\n\n"
    "完成判据：\n"
    "最终图必须同时保持全部主体身份、原构图和完整镜面覆盖；缩略图下仍能读出圆润块面与宽阔高光。\n\n"
    "限制：\n"
    "不要新增用户图中没有的主体、物件、关系或可读文字。不要保留照片像素、写实皮肤、真实毛发、摄影景深、镜头光照或滤镜叠加痕迹。"
)


def template(asset: str = "./style.png") -> dict:
    return {
        "key": "high-gloss-chrome-rendering",
        "title": "高光镜面塑形",
        "description": "以高反射镜面、宽阔高光和圆润块面重绘你的图片",
        "kind": "STYLE_REF",
        "cover": asset,
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
    def test_rejects_title_outside_three_to_six_characters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "style-template.json"
            for title in ("水彩", "水青双色阈值印刷"):
                data = template()
                data["title"] = title
                errors = MODULE.validate_data(data, file, "local", "", "")
                self.assertTrue(any("title" in error for error in errors))

    def test_valid_local_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(MODULE.validate_data(data, file, "local", "", ""), [])

    def test_rejects_removed_reference_image_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["referenceImage"] = "./style.png"
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("referenceImage" in error for error in errors))

    def test_accepts_authorized_structured_reconstruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = STRUCTURED_PROMPT
            self.assertEqual(MODULE.validate_data(data, file, "local", "", ""), [])

    def test_accepts_v2_nine_section_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = V2_PROMPT
            self.assertEqual(MODULE.validate_data(data, file, "local", "", ""), [])

    def test_rejects_v2_prompt_with_empty_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = V2_PROMPT.replace(
                "核心效果：\n把主体全部重建为连续圆润的高反射镜面块体，以宽阔高光和深色反射带共同塑造体积。",
                "核心效果：\n",
            )
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("核心效果" in error and "不得为空" in error for error in errors))

    def test_accepts_equivalent_source_frame_inheritance_wording(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = PROMPT.replace(
                "输出画幅方向与宽高比跟随用户上传图。",
                "输出画布严格保持用户上传图的相同方向与宽高比。",
            )
            self.assertEqual(MODULE.validate_data(data, file, "local", "", ""), [])

    def test_accepts_explicit_after_authorized_frame_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = PROMPT.replace(
                "输出画幅方向与宽高比跟随用户上传图。",
                "允许改变画幅方向与宽高比，输出固定为竖版四比五画幅。",
            )
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
            self.assertTrue(any("画幅策略" in error for error in errors))

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
                "全部显著主体逐一对应用户图中的原主体，不复制、不合并、不删减、不增殖人物、动物、物体或其关联物。",
                "全部显著主体保持可识别。",
            )
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("主体逐一对应与实例控制" in error for error in errors))

    def test_rejects_prompt_without_transformation_permission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = PROMPT.replace(
                "仅改变绘制语言与材质表现，保持主体形态、姿态与视角、环境和构图。",
                "保持画面的基本可识别性。",
            )
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("变换权限声明" in error for error in errors))

    def test_rejects_contract_transcript_language(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "style.png").write_bytes(b"image")
            file = root / "style-template.json"
            data = template()
            data["promptTemplate"] = PROMPT.replace("保留全部显著主体", "主体范围遵循前文来源绑定")
            errors = MODULE.validate_data(data, file, "local", "", "")
            self.assertTrue(any("内部合同或悬空指代用语" in error for error in errors))

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
