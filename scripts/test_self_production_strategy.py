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
        cls.taxonomy = (cls.skill_root / "references/garment-print-template-taxonomy.md").read_text(encoding="utf-8")

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

    def test_manifest_tracks_strategy_and_regression_test(self) -> None:
        manifest = json.loads((self.skill_root / "skill-manifest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(tuple(map(int, manifest["version"].split("."))), (4, 1, 1))
        self.assertIn("references/self-production-strategy.md", manifest["tracked_files"])
        self.assertIn("scripts/test_self_production_strategy.py", manifest["tracked_files"])


if __name__ == "__main__":
    unittest.main()
