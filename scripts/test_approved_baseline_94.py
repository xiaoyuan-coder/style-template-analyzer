#!/usr/bin/env python3
"""Read-only regression for the legacy 94-template static baseline."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from style_baseline import verify_approval_descriptor
from validate_style_package import validate_package


class ApprovedBaseline94Tests(unittest.TestCase):
    def test_current_approved_baseline_matches_count_and_digest(self) -> None:
        skill_root = Path(__file__).parents[1]
        repo_root = skill_root
        descriptor = json.loads((skill_root / "references" / "legacy-approved-baseline-94.json").read_text(encoding="utf-8"))
        business_root = (repo_root / descriptor["businessRoot"]).resolve()
        if not business_root.is_dir():
            self.skipTest("业务总库未挂载；仅跳过真实 94 基线回归")
        snapshot, errors = verify_approval_descriptor(descriptor, repo_root)
        self.assertEqual(errors, [])
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["count"], 94)
        self.assertEqual(len(list(business_root.rglob("effect.png"))), 94)
        package_errors, summary = validate_package(
            business_root, "legacy", "remote", "assets.memebuy.cn", "",
        )
        self.assertEqual(package_errors, [])
        self.assertEqual(summary["templates"], 94)


if __name__ == "__main__":
    unittest.main()
