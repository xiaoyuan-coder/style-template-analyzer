#!/usr/bin/env python3

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from recompile_approved_runtime_prompts import (
    compile_prompt,
    genericity_errors,
    replay_evidence_errors,
    semantic_transfer_errors,
    sha256_file,
)
from test_validate_style_template import template


class RecompileApprovedRuntimePromptsTests(unittest.TestCase):
    def test_compiles_legacy_prompt_into_direct_sections(self) -> None:
        data = template()
        prompt = compile_prompt(data)
        self.assertEqual(genericity_errors(prompt), [])
        for section in (
            "任务", "保留", "变换权限", "核心效果", "空间结构",
            "内容映射", "视觉风格", "完成判据", "限制",
        ):
            self.assertEqual(prompt.count(f"{section}："), 1)
        self.assertNotIn("越权新增", prompt)
        self.assertNotIn("本模板", prompt)

    def test_structural_prompt_gets_source_adaptive_boundary(self) -> None:
        data = template()
        data["promptTemplate"] = data["promptTemplate"].replace(
            "仅改变绘制语言与材质表现，保持主体形态、姿态与视角、环境和构图。",
            "本模板允许重建环境并重组构图。",
        )
        prompt = compile_prompt(data)
        self.assertIn("用户图实际可见内容", prompt)
        self.assertIn("核心机关所需角色必须从用户图实际可见内容中选择", prompt)
        self.assertIn("只有不影响核心机关的辅助装饰可以省略", prompt)
        self.assertNotIn("缺少可对应结构时省略该局部机制", prompt)

    def test_case_objects_are_compiled_into_source_roles(self) -> None:
        data = template()
        data["promptTemplate"] = data["promptTemplate"].replace(
            "将整张画面重绘为高反射抛光铬材质。用连续圆润曲面概括形体，宽阔高光与深色反射带塑造体积，柔和接触阴影稳定空间。",
            "图形语言：法式孔版。空间语法：完整脸部作为大轨道中心，汤匙轮廓成为一条窄长内轨，目光方向成为一条宽外轨；两轨在眼睛与匙面高光处相切。来源绑定：内轨、外轨和切点分别来自汤匙、目光与可见高光，不新增餐具或符号。边界策略：不生成文字。",
        )
        prompt = compile_prompt(data)
        self.assertEqual(genericity_errors(prompt), [])
        self.assertNotIn("汤匙", prompt)
        self.assertIn("窄长关联轮廓", prompt)

    def test_spatial_syntax_is_a_hard_composition_instruction(self) -> None:
        data = template()
        data["key"] = "guitar-axis-panorama"
        data["title"] = "琴轴长景"
        data["description"] = "把输入内容重组为折返的连续全景带"
        data["promptTemplate"] = (
            "只使用用户上传图作为唯一内容来源。基础主体不复制、不合并、不删减、不增殖；"
            "允许同一原主体的局部和同一时刻不同景别做可追溯派生。"
            "输出画幅方向与宽高比跟随用户上传图。"
            "图形语言：珊瑚橙、海军蓝、天青、奶油黄和白的动画孔版，清楚粗线与稀疏网点。"
            "空间语法：来源中最长的窄长关联轮廓延展成一条连续长景带，依次承载远景线索、"
            "接触局部、关联物主体和完整主主体；长景带在主主体周围折回一次，形成一条可读的全景路线。"
            "来源绑定：各段内容来自同一时刻的真实位置，完整主主体只出现一次，接触局部承担信息增量。"
            "边界策略：不生成文字或复制主体。"
        )

        prompt = compile_prompt(data)
        core = prompt.split("\n\n核心效果：\n", 1)[1].split("\n\n空间结构：", 1)[0]
        composition = prompt.split("\n\n空间结构：\n", 1)[1].split("\n\n内容映射：", 1)[0]
        mapping = prompt.split("\n\n内容映射：\n", 1)[1].split("\n\n视觉风格：", 1)[0]
        visual = prompt.split("\n\n视觉风格：\n", 1)[1].split("\n\n限制：", 1)[0]

        self.assertIn("连续长景带", core)
        self.assertIn("折回一次", core)
        self.assertIn("接触局部", mapping)
        self.assertIn("上下两条", composition)
        self.assertIn("放大的窄长关联轮廓", composition)
        self.assertIn("跨入白底", composition)
        self.assertNotIn("自适应排布", composition)
        self.assertNotIn("连续长景带", visual)
        self.assertEqual(semantic_transfer_errors(data["promptTemplate"], prompt), [])

    def test_semantic_gate_rejects_spatial_syntax_stranded_in_visual_style(self) -> None:
        source = (
            "图形语言：双色孔版。"
            "空间语法：三个斜切画格沿动作方向排列，主主体跨越画格边界。"
            "来源绑定：画格内容来自同一输入。"
        )
        compiled = (
            "任务：\n从零重绘。\n\n保留：\n保留主体。\n\n变换权限：\n允许重组。\n\n"
            "核心效果：\n保持清楚效果。\n\n空间结构：\n根据用户图自适应排布。\n\n"
            "内容映射：\n使用用户图内容。\n\n"
            "视觉风格：\n使用双色孔版，三个斜切画格沿动作方向排列，主主体跨越画格边界。\n\n"
            "完成判据：\n主体清楚。\n\n"
            "限制：\n不要新增内容。"
        )

        errors = semantic_transfer_errors(source, compiled)
        self.assertTrue(any("空间语法未充分进入" in error for error in errors))

    def test_known_structure_red_cases_compile_to_observable_blueprints(self) -> None:
        cases = {
            "exploded-room-slice": ("四块水平悬浮剖片", "三道以上空气缝"),
            "diagonal-manga-triptych": ("三个面积不等", "全景、动作、特写"),
            "topographic-depth-bands": ("五至七条", "不能退化成背景波浪"),
            "corner-return-kaleidoscope": ("四条宽白斜分割", "中央菱形"),
            "hand-shadow-self-portrait": ("大黑投影", "连续黑色轮廓"),
            "mirror-paw-folding-corridor": ("全部像素统一重绘", "不强制新增折叠"),
        }
        for key, expected in cases.items():
            with self.subTest(key=key):
                data = template()
                data["key"] = key
                prompt = compile_prompt(data)
                self.assertEqual(genericity_errors(prompt), [])
                self.assertTrue(all(marker in prompt for marker in expected))
                self.assertNotIn("缺少可对应结构时省略", prompt)

    def test_dynamic_gate_requires_original_and_two_distinct_transfer_replays(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = []
            sources = []
            for index in range(3):
                path = root / f"generated-{index}.png"
                path.write_bytes(f"image-{index}".encode())
                generated.append(path)
                source = root / f"source-{index}.png"
                source.write_bytes(f"source-{index}".encode())
                sources.append(source)
            result = {
                "newPromptSha256": "p" * 64,
                "beforeSha256": sha256_file(sources[0]),
            }

            def replay(path: Path, source: Path) -> dict[str, object]:
                return {
                    "verdict": "pass",
                    "score": 95,
                    "promptSha256": result["newPromptSha256"],
                    "sourcePath": source.name,
                    "sourceSha256": sha256_file(source),
                    "imageInputCount": 1,
                    "approvedAfterUsedAsRuntimeInput": False,
                    "requiredMechanisms": [{"name": "core", "status": "pass"}],
                    "generatedPath": path.name,
                    "generatedSha256": sha256_file(path),
                }

            evidence = {
                "originalReplay": replay(generated[0], sources[0]),
                "transferReplays": [
                    replay(generated[1], sources[1]),
                    replay(generated[2], sources[2]),
                ],
            }
            self.assertEqual(
                replay_evidence_errors(evidence, result=result, report_file=root / "report.json"),
                [],
            )
            evidence["transferReplays"] = evidence["transferReplays"][:1]
            errors = replay_evidence_errors(evidence, result=result, report_file=root / "report.json")
            self.assertIn("至少需要两张换图迁移回放", errors)


if __name__ == "__main__":
    unittest.main()
