#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("validate_style_analysis.py")
SPEC = importlib.util.spec_from_file_location("validate_style_analysis", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def contract() -> dict:
    return {
        "families": ["drawing-style"],
        "subjectSelection": "all-salient",
        "subjectForm": "preserve",
        "poseAndView": "preserve",
        "instanceMode": "preserve",
        "environmentMode": "preserve",
        "compositionMode": "preserve",
        "contentInvariants": [
            "subject-set",
            "subject-features",
            "associated-objects",
            "key-relationships",
            "frame-policy",
        ],
        "templateConstants": [],
        "allowedDerivations": [],
        "textPolicy": {
            "subjectText": "preserve-when-legible",
            "environmentText": "preserve",
            "templateText": "none",
        },
        "framePolicy": "inherit-source-aspect-ratio",
        "renderingTarget": "full-non-photographic-redraw",
    }


def analysis() -> dict:
    return {
        "schemaVersion": "3.0.0",
        "templateKey": "soft-film-grain-salvage",
        "referenceAsset": "../../01-输入/0031.png",
        "referenceType": "single-style-reference",
        "extractionMode": "hybrid-operator-salvage",
        "referenceContentInventory": ["游乐园", "过山车", "胶片齿孔边框"],
        "transformationContract": contract(),
        "renderingFingerprint": {
            "imagingMedium": "由低频柔边色块和可见颗粒簇构成的非摄影印刷插画。",
            "shapeAndDetail": "主体结构保持完整，微细节压缩成柔边色面与颗粒轮廓。",
            "linesAndEdges": "轮廓由青灰与奶白色面柔和交界形成，不保留镜头失焦像素。",
            "marksAndTexture": "粗细两级颗粒直接组成形体、明暗和边缘，覆盖全部区域。",
            "colorOrganization": "黄绿、浅青、奶白和少量粉色组成低对比有限色盘。",
            "toneAndSpace": "高光扩散为奶白色面，阴影压成青灰颗粒块，空间保持插画化。",
            "globalCoverage": "用户输入全部像素由色面和颗粒重新构造，摄影底图完全退出。",
        },
        "signatureMechanisms": [
            {"family": "rendering", "mechanism": "两级颗粒簇参与形体构造", "evidence": "全局可见粗细颗粒。"},
            {"family": "drawing-style", "mechanism": "黄绿浅青奶白低对比色盘", "evidence": "主色集中于这些色域。"},
            {"family": "rendering", "mechanism": "奶白扩散高光和青灰阴影", "evidence": "亮暗边界呈扩散色带。"},
        ],
        "referenceContentBlocklist": ["游乐园", "过山车", "胶片齿孔边框"],
        "salvagePlan": {
            "sourceDependency": "dominant-photographic",
            "observedOperators": ["低对比黄绿色偏色", "奶白高光扩散", "粗细两级全局颗粒"],
            "nonPhotographicCarrier": "用颗粒簇和柔边色面直接重建所有形体。",
            "coverageExpansion": "把局部和表面摄影处理扩展为覆盖主体、背景和边角的完整非摄影成像。",
            "uncertainty": "参考图没有独立绘画线稿，线条规律由色面边界保守推导。",
        },
        "classificationConfidence": 0.78,
        "qualityStatus": "salvaged",
        "reviewNotes": ["需要真实生成验证救援后的全像素覆盖。"],
    }


class AnalysisValidatorTests(unittest.TestCase):
    def test_accepts_legacy_schema_version(self) -> None:
        data = analysis()
        data["schemaVersion"] = "2.0"
        data["transformationContract"]["contentInvariants"][-1] = "source-frame"
        self.assertEqual(MODULE.validate_data(data), [])

    def test_accepts_legacy_semver_schema_version(self) -> None:
        data = analysis()
        data["schemaVersion"] = "2.0.0"
        data["transformationContract"]["contentInvariants"][-1] = "source-frame"
        self.assertEqual(MODULE.validate_data(data), [])

    def test_current_schema_accepts_approved_after_frame_override(self) -> None:
        data = analysis()
        data["transformationContract"]["framePolicy"] = "fixed-template-aspect-ratio"
        self.assertEqual(MODULE.validate_data(data), [])

    def test_legacy_schema_rejects_frame_override(self) -> None:
        data = analysis()
        data["schemaVersion"] = "2.0.0"
        data["transformationContract"]["contentInvariants"][-1] = "source-frame"
        data["transformationContract"]["framePolicy"] = "fixed-template-aspect-ratio"
        self.assertTrue(any("framePolicy" in error for error in MODULE.validate_data(data)))

    def test_accepts_print_ready_artwork_classification(self) -> None:
        data = analysis()
        data["garmentPrintClassification"] = {
            "userFacingCategory": "版印",
            "designProduct": "artwork",
            "renderingMedium": "duotone-woodcut",
            "subjectTreatment": "stylize-form",
            "visualSystem": "none",
            "layoutStructure": "single-scene",
            "printReadiness": "A",
            "deanalysisRequired": False,
        }
        self.assertEqual(MODULE.validate_data(data), [])

    def test_rejects_unmarked_analysis_callouts(self) -> None:
        data = analysis()
        data["garmentPrintClassification"] = {
            "userFacingCategory": "手绘",
            "designProduct": "artwork",
            "renderingMedium": "watercolor",
            "subjectTreatment": "stylize-form",
            "visualSystem": "analysis-system",
            "layoutStructure": "annotated-callouts",
            "printReadiness": "C",
            "deanalysisRequired": False,
        }
        errors = MODULE.validate_data(data)
        self.assertTrue(any("analysis-board" in error for error in errors))
        self.assertTrue(any("deanalysisRequired=true" in error for error in errors))

    def test_accepts_complete_salvaged_analysis(self) -> None:
        self.assertEqual(MODULE.validate_data(analysis()), [])

    def test_accepts_crt_structured_reconstruction(self) -> None:
        data = analysis()
        data["qualityStatus"] = "usable"
        data["extractionMode"] = "direct-reconstruction"
        del data["salvagePlan"]
        data["transformationContract"] = {
            **contract(),
            "families": ["drawing-style", "visual-system", "information-expression", "composition-structure"],
            "poseAndView": "derive",
            "instanceMode": "repeat-or-split",
            "environmentMode": "rebuild",
            "compositionMode": "reorganize",
            "templateConstants": ["CRT 扫描屏幕", "3-6 个复古系统浮窗", "菜单栏与图表面板"],
            "allowedDerivations": [
                "local-enlargement",
                "feature-statistics",
                "subject-repetition",
                "new-viewpoint",
                "environment-reconstruction",
                "composition-reorganization",
            ],
            "textPolicy": {
                "subjectText": "preserve-when-legible",
                "environmentText": "remove-with-environment",
                "templateText": "template-specific",
            },
        }
        data["signatureMechanisms"] = [
            {"family": "visual-system", "mechanism": "复古操作系统浮窗层级", "evidence": "画面含多个可拖拽窗口。"},
            {"family": "information-expression", "mechanism": "用户主体局部放大和颜色图表", "evidence": "窗口内容来自中心主体。"},
            {"family": "drawing-style", "mechanism": "低分辨率像素和 CRT 扫描线", "evidence": "全部区域共享像素栅格。"},
        ]
        self.assertEqual(MODULE.validate_data(data), [])

    def test_rejects_template_constant_also_blocklisted(self) -> None:
        data = analysis()
        data["transformationContract"]["templateConstants"] = ["胶片齿孔边框"]
        errors = MODULE.validate_data(data)
        self.assertTrue(any("互斥" in error for error in errors))

    def test_rejects_derived_pose_without_derivation(self) -> None:
        data = analysis()
        data["transformationContract"]["poseAndView"] = "derive"
        errors = MODULE.validate_data(data)
        self.assertTrue(any("new-viewpoint" in error or "new-action" in error for error in errors))

    def test_rejects_incomplete_content_invariants(self) -> None:
        data = analysis()
        data["transformationContract"]["contentInvariants"].remove("associated-objects")
        errors = MODULE.validate_data(data)
        self.assertTrue(any("五项全局不变量" in error for error in errors))

    def test_rejects_salvage_without_observed_operators(self) -> None:
        data = analysis()
        data["salvagePlan"]["observedOperators"] = []
        errors = MODULE.validate_data(data)
        self.assertTrue(any("observedOperators" in error for error in errors))

    def test_accepts_low_information_salvage_with_two_operators(self) -> None:
        data = analysis()
        data["extractionMode"] = "low-information-salvage"
        data["salvagePlan"]["sourceDependency"] = "near-empty"
        data["salvagePlan"]["observedOperators"] = ["纯黑占据主画面", "极少暖白反色标记"]
        self.assertEqual(MODULE.validate_data(data), [])

    def test_rejects_direct_analysis_with_salvage_plan(self) -> None:
        data = analysis()
        data["qualityStatus"] = "usable"
        data["extractionMode"] = "direct-reconstruction"
        errors = MODULE.validate_data(data)
        self.assertTrue(any("salvagePlan" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
