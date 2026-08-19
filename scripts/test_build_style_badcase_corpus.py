#!/usr/bin/env python3
"""Tests for user-rejection BadCase corpus maintenance."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from PIL import Image

from build_style_badcase_corpus import build_item, logical_identity, rejected_entries


class BadcaseCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "batch"
        self.authoring = self.root / "authoring"
        self.authoring.mkdir(parents=True)
        Image.new("RGB", (64, 64), (80, 120, 160)).save(self.authoring / "reject.png")
        self.decision_path = self.authoring / "approval-decision.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_only_explicit_user_rejections_are_collected(self) -> None:
        decision = {
            "artifactType": "style_template_visual_gate_decision",
            "decisionAuthority": "user_attached_selection",
            "decisionAt": "2026-08-18T00:00:00+00:00",
            "decisions": [
                {"index": 1, "key": "passed-style", "verdict": "pass", "cover": "reject.png"},
                {"index": 2, "key": "rejected-style", "verdict": "reject", "cover": "reject.png", "reasons": ["not_selected_by_user"]},
                {"index": 3, "key": "pending-style", "verdict": "pending", "cover": "reject.png"},
            ],
        }
        self.decision_path.write_text(json.dumps(decision), encoding="utf-8")
        entries = rejected_entries(decision, accept_legacy_exclusions=False)
        self.assertEqual([item[0]["key"] for item in entries], ["rejected-style"])
        record = build_item(self.decision_path, decision, entries[0][0], legacy_exclusion=False)
        self.assertEqual(record["authority"], "user_attached_selection")
        self.assertEqual(record["decision"], "reject")
        self.assertTrue(record["afterImage"].endswith("reject.png"))

    def test_legacy_exclusion_requires_explicit_flag(self) -> None:
        decision = {"artifactType": "style_template_approval_decision", "excluded": [{"key": "legacy-style", "reason": "weak"}]}
        self.assertEqual(rejected_entries(decision, accept_legacy_exclusions=False), [])
        entries = rejected_entries(decision, accept_legacy_exclusions=True)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0][1])

    def test_record_matches_schema(self) -> None:
        decision = {
            "approvalSource": "user",
            "approvedAt": "2026-08-18T00:00:00+00:00",
            "rejected": [{"order": 4, "key": "weak-style", "workingTitle": "弱机制", "reason": "Y 结构弱", "cover": "reject.png"}],
        }
        self.decision_path.write_text(json.dumps(decision), encoding="utf-8")
        entry = rejected_entries(decision, accept_legacy_exclusions=False)[0]
        record = build_item(self.decision_path, decision, entry[0], legacy_exclusion=entry[1])
        corpus = {
            "artifactType": "style_badcase_corpus",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "updatedAt": "2026-08-18T00:00:00+00:00",
            "count": 1,
            "items": [record],
        }
        schema_path = Path(__file__).parents[1] / "contracts" / "style-badcase-corpus.schema.json"
        Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(corpus)

    def test_logical_identity_replaces_enriched_revision_record(self) -> None:
        before = {"sourceDecisionPath": "/decision.json", "candidateIndex": 4, "title": "渐变嵌套"}
        after = {**before, "afterImage": "/after.png", "x": "gradient-contour"}
        self.assertEqual(logical_identity(before), logical_identity(after))


if __name__ == "__main__":
    unittest.main()
