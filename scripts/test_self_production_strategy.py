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

    def test_produce_routes_to_strategy_and_requires_x_plus_y(self) -> None:
        self.assertIn("references/self-production-strategy.md", self.skill)
        self.assertIn("图形语言 X + 空间结构 Y", self.skill)
        self.assertIn("同一结构骨架反复换皮", self.skill)

    def test_material_is_auxiliary_for_default_print_production(self) -> None:
        self.assertIn("材质默认只作辅助表现", self.skill)
        self.assertIn("实体材料默认只作辅助维度", self.taxonomy)
        self.assertIn("材质替换未改变内容组织关系", self.taxonomy)

    def test_complete_shape_and_direct_review_are_hard_gates(self) -> None:
        for marker in ("8%–12%", "拦腰裁切", "直接生成候选效果图", "退出当前 ready 选择"):
            self.assertIn(marker, self.strategy)
        self.assertIn("只编译批准项", self.strategy)

    def test_manifest_tracks_strategy_and_regression_test(self) -> None:
        manifest = json.loads((self.skill_root / "skill-manifest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(tuple(map(int, manifest["version"].split("."))), (4, 1, 0))
        self.assertIn("references/self-production-strategy.md", manifest["tracked_files"])
        self.assertIn("scripts/test_self_production_strategy.py", manifest["tracked_files"])


if __name__ == "__main__":
    unittest.main()
