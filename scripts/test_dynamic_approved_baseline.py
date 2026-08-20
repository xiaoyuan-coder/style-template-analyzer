#!/usr/bin/env python3
"""Read-only regression for the current human-pass-driven baseline."""

from __future__ import annotations

import unittest
from pathlib import Path

from style_dynamic_baseline import DynamicBaselineCatalog


class CurrentDynamicBaselineTests(unittest.TestCase):
    def test_pointer_resolves_all_current_human_passes(self) -> None:
        root = Path(__file__).parents[1]
        pointer = root / "references" / "dynamic-baseline.json"
        catalog = DynamicBaselineCatalog(pointer)
        if not catalog.catalog_file.is_file():
            self.skipTest("业务总库未挂载；跳过动态基线真实数据回归")
        snapshot, templates = catalog.load_active()
        self.assertGreaterEqual(snapshot["count"], 144)
        self.assertEqual(len(templates), snapshot["count"])


if __name__ == "__main__":
    unittest.main()
