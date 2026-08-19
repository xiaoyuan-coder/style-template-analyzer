#!/usr/bin/env python3

from __future__ import annotations

import unittest

from migrate_test_image_ledger_v2 import migrate
from style_test_pool import TestPoolError


def assignment(key: str, asset_id: str) -> dict:
    return {
        "artifactType": "test_image_assignment",
        "schemaVersion": "1.0.0",
        "producer": "style-template-analyzer",
        "deliverySetId": "legacy-delivery",
        "templateKey": key,
        "revision": 1,
        "assetId": asset_id,
        "assignedAt": "2026-08-17T00:00:00Z",
        "status": "committed",
    }


def decision(key: str, verdict: str) -> dict:
    return {
        "deliverySetId": "legacy-delivery",
        "templateKey": key,
        "revision": 1,
        "verdict": verdict,
        "decidedAt": "2026-08-19T00:00:00Z",
        "reason": "人工核对历史效果",
        "coverSha256": "a" * 64,
        "promptSha256": "b" * 64,
    }


class TestImageLedgerMigrationTests(unittest.TestCase):
    def test_explicit_pass_and_reject_create_consumed_and_released(self) -> None:
        ledger = {
            "artifactType": "test_image_assignment_ledger",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "assignments": [assignment("template-a", "asset-a"), assignment("template-b", "asset-b")],
        }
        decisions = {
            "artifactType": "legacy_test_image_decisions",
            "schemaVersion": "1.0.0",
            "producer": "human-review",
            "decisions": [decision("template-a", "pass"), decision("template-b", "reject")],
        }
        migrated = migrate(ledger, decisions)
        self.assertEqual([item["status"] for item in migrated["assignments"]], ["consumed", "released"])

    def test_incomplete_decision_table_is_rejected(self) -> None:
        ledger = {
            "artifactType": "test_image_assignment_ledger",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "assignments": [assignment("template-a", "asset-a")],
        }
        decisions = {
            "artifactType": "legacy_test_image_decisions",
            "schemaVersion": "1.0.0",
            "producer": "human-review",
            "decisions": [],
        }
        with self.assertRaisesRegex(TestPoolError, "legacy_decisions_incomplete"):
            migrate(ledger, decisions)

    def test_two_passes_cannot_consume_one_legacy_asset(self) -> None:
        ledger = {
            "artifactType": "test_image_assignment_ledger",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "assignments": [assignment("template-a", "asset-a"), assignment("template-b", "asset-a")],
        }
        decisions = {
            "artifactType": "legacy_test_image_decisions",
            "schemaVersion": "1.0.0",
            "producer": "human-review",
            "decisions": [decision("template-a", "pass"), decision("template-b", "pass")],
        }
        with self.assertRaisesRegex(TestPoolError, "assignment_ledger_invalid"):
            migrate(ledger, decisions)


if __name__ == "__main__":
    unittest.main()

