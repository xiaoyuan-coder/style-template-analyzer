#!/usr/bin/env python3
"""Tests for durable experience closure and snapshot freshness."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from style_experience_store import DurableExperienceStore, ExperienceStoreError


def event(verdict: str = "pass", revision: int = 1) -> dict:
    return {
        "casePool": "goodcase" if verdict == "pass" else "badcase",
        "reviewRoot": "/tmp/review",
        "decision": {
            "templateKey": "ink-outline",
            "revision": revision,
            "verdict": verdict,
            "reason": "人工验收结论",
            "coverSha256": "a" * 64,
            "promptSha256": "b" * 64,
        },
    }


class ExperienceStoreTests(unittest.TestCase):
    def test_deposit_is_idempotent_and_rebuilds_current_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = DurableExperienceStore(Path(directory))
            first = store(event())
            second = store(event())
            self.assertEqual(first["eventId"], second["eventId"])
            self.assertEqual(first["snapshotSha256"], second["snapshotSha256"])
            snapshot = store.load_fresh_snapshot()
            self.assertEqual(snapshot["caseCount"], 1)
            self.assertEqual(snapshot["activeGoodcaseKeys"], ["ink-outline"])

    def test_manual_corpus_change_makes_snapshot_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = DurableExperienceStore(Path(directory))
            store(event())
            corpus = json.loads(store.corpus_file.read_text(encoding="utf-8"))
            corpus["cases"].append(dict(corpus["cases"][0], eventId="c" * 64))
            store.corpus_file.write_text(json.dumps(corpus), encoding="utf-8")
            with self.assertRaisesRegex(ExperienceStoreError, "experience_snapshot_stale"):
                store.load_fresh_snapshot()

    def test_legacy_goodcase_and_badcase_are_merged_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            goodcase = root / "goodcase.json"
            badcase = root / "badcase.json"
            goodcase.write_text(json.dumps({"items": [{"goodcaseId": "g-1", "key": "ink-outline", "revision": 2}]}), encoding="utf-8")
            badcase.write_text(json.dumps({"items": [
                {"badcaseId": "b-1", "key": "weak-frame", "reasons": ["结构无效"]},
                {"badcaseId": "b-2", "reasons": ["缺少模板身份"]},
            ]}), encoding="utf-8")
            store = DurableExperienceStore(root / "experience")
            first = store.merge_legacy_corpora(goodcase, badcase)
            second = store.merge_legacy_corpora(goodcase, badcase)
            self.assertEqual(first["added"], 3)
            self.assertEqual(second["added"], 0)
            self.assertEqual(store.load_fresh_snapshot()["caseCount"], 3)


if __name__ == "__main__":
    unittest.main()
