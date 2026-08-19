#!/usr/bin/env python3
"""Documentation regression tests for the self-production design gate."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


class SelfProductionStrategyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill_root = Path(__file__).parents[1]
        cls.skill = (cls.skill_root / "SKILL.md").read_text(encoding="utf-8")
        cls.strategy = (cls.skill_root / "references/self-production-strategy.md").read_text(encoding="utf-8")
        cls.architecture = (cls.skill_root / "references/architecture-and-lifecycle.md").read_text(encoding="utf-8")
        cls.oss_handoff = (cls.skill_root / "references/oss-handoff.md").read_text(encoding="utf-8")
        cls.taxonomy = (cls.skill_root / "references/garment-print-template-taxonomy.md").read_text(encoding="utf-8")
        cls.goodcases = (cls.skill_root / "references/goodcase-after-aesthetics.md").read_text(encoding="utf-8")
        cls.badcases = (cls.skill_root / "references/badcase-learning.md").read_text(encoding="utf-8")

    def test_produce_routes_to_strategy_and_requires_mechanism_model(self) -> None:
        self.assertIn("references/self-production-strategy.md", self.skill)
        self.assertIn("X 图形语言 × Y 空间语法 × B 内容绑定 × C 边界策略", self.skill)
        for marker in ("graphicLanguage", "spatialGrammar", "contentBinding", "boundaryPolicy"):
            self.assertIn(marker, self.strategy)
        self.assertIn("沿用同一结构骨架换皮", self.strategy)

    def test_material_is_auxiliary_for_default_print_production(self) -> None:
        self.assertIn("材质默认只作辅助表现", self.skill)
        self.assertIn("实体材料默认只作辅助维度", self.taxonomy)
        self.assertIn("材质替换未改变内容组织关系", self.taxonomy)

    def test_semantic_integrity_and_direct_review_are_hard_gates(self) -> None:
        for marker in (
            "8%–12%", "主动裁切", "景别推进", "抽象关系带", "拦腰截断",
            "直接生成候选图", "退出当前 ready 选择",
        ):
            self.assertIn(marker, self.strategy)
        self.assertIn("只编译批准项", self.strategy)
        self.assertNotIn("只有明确的满版 `pattern` 才允许触边", self.strategy)

    def test_inspiration_is_compiled_to_mechanisms_without_literal_shells(self) -> None:
        for marker in ("内容落点", "关系重组", "来源绑定", "边界行为", "重新发明载体"):
            self.assertIn(marker, self.strategy)
        self.assertIn("去掉来源的配色、材质和外壳", self.strategy)

    def test_plain_print_templates_exclude_analysis_frames_by_default(self) -> None:
        for marker in ("外框", "放大镜小窗", "连接线", "分析标注"):
            self.assertIn(marker, self.strategy)
        self.assertIn("用户明确要求图鉴、档案、分析或说明书效果", self.strategy)

    def test_aesthetic_non_regression_and_structure_value_are_hard_gates(self) -> None:
        for marker in (
            "审美非退化", "信息增量测试", "可识别主体重复测试", "去结构测试",
            "变形预算测试", "构图连续测试", "媒介关系测试",
        ):
            self.assertIn(marker, self.strategy)
        self.assertIn("一个完整主锚点 + 一个来源明确的放大细节", self.strategy)
        self.assertIn("允许混合媒介", self.strategy)
        self.assertNotIn("统一媒介", self.strategy)

    def test_produce_requires_approval_and_post_approval_finalization_command(self) -> None:
        for document in (self.skill, self.strategy, self.architecture, self.oss_handoff):
            self.assertIn("批准", document)
            self.assertIn("上传 OSS", document)
        self.assertIn("批准本身只更新名单", self.skill)
        self.assertIn("数量目标或“模板包”字样不能跳过审批", self.strategy)
        self.assertIn("批准本身也不触发上传", self.oss_handoff)

    def test_exact_visual_revision_is_frozen_before_finalization(self) -> None:
        for marker in (
            "具体视觉 revision", "selectedCoverSha256", "prompt SHA",
            "validate_approved_variants.py", "批准专用编译规格",
        ):
            self.assertIn(marker, self.skill + self.strategy + self.architecture)
        self.assertIn("首版、retry、replacement 和总览副本", self.strategy)
        self.assertIn("运行时图片数组仍只含用户上传图", self.strategy)

    def test_after_first_goodcase_learning_drives_candidate_design(self) -> None:
        self.assertIn("references/goodcase-after-aesthetics.md", self.skill)
        for marker in (
            "visual-authority", "relational-invention", "after 第一眼吸引力",
            "来源价值保留", "X 视觉统治力", "Y 内容适配", "印制闭合度",
            "sourceAdvantage", "60%–70%", "新颖性不能救回难看的 after",
        ):
            self.assertIn(marker, self.skill + self.strategy + self.goodcases)
        for key in (
            "transparent-watercolor-artwork", "three-act-flat-gouache",
            "interlocking-dual-silhouette", "floating-shelf-depth",
            "memebuy-crt-interface",
        ):
            self.assertIn(key, self.goodcases)

    def test_manifest_tracks_strategy_and_regression_test(self) -> None:
        manifest = json.loads((self.skill_root / "skill-manifest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(tuple(map(int, manifest["version"].split("."))), (4, 5, 0))
        self.assertIn("references/self-production-strategy.md", manifest["tracked_files"])
        self.assertIn("references/goodcase-after-aesthetics.md", manifest["tracked_files"])
        self.assertIn("references/badcase-learning.md", manifest["tracked_files"])
        self.assertIn("scripts/validate_approved_variants.py", manifest["tracked_files"])
        self.assertIn("scripts/build_style_badcase_corpus.py", manifest["tracked_files"])
        self.assertIn("scripts/test_approved_variant_selection.py", manifest["tracked_files"])
        self.assertIn("scripts/test_build_style_badcase_corpus.py", manifest["tracked_files"])
        self.assertIn("scripts/test_self_production_strategy.py", manifest["tracked_files"])

    def test_explicit_user_rejections_feed_badcase_learning(self) -> None:
        for marker in (
            "style_badcase_corpus", "用户明确拒绝", "待审核", "未表态",
            "具体视觉 revision", "幂等", "GoodCase", "BadCase",
        ):
            self.assertIn(marker, self.skill + self.strategy + self.architecture + self.badcases)
        self.assertIn("scripts/build_style_badcase_corpus.py", self.skill + self.strategy + self.badcases)


if __name__ == "__main__":
    unittest.main()
