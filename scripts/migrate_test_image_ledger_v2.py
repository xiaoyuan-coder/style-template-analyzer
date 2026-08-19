#!/usr/bin/env python3
"""Migrate legacy assignments only from an explicit human decision table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from style_test_pool import TestImagePool, TestPoolError, _validate_contract


def _identity(item: dict[str, Any]) -> tuple[str, str, int]:
    return (str(item["deliverySetId"]), str(item["templateKey"]), int(item["revision"]))


def migrate(ledger: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    _validate_contract(ledger, "test-image-assignment-ledger.schema.json", "assignment_ledger_invalid")
    schema_file = Path(__file__).parents[1] / "contracts" / "legacy-test-image-decisions.schema.json"
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    if list(Draft202012Validator(schema).iter_errors(decisions)):
        raise TestPoolError("legacy_decisions_invalid")
    by_identity: dict[tuple[str, str, int], dict[str, Any]] = {}
    for decision in decisions["decisions"]:
        identity = _identity(decision)
        if identity in by_identity:
            raise TestPoolError("legacy_decision_duplicate")
        by_identity[identity] = decision
    legacy_identities = {
        _identity(item) for item in ledger["assignments"]
        if item.get("schemaVersion") == "1.0.0"
    }
    if set(by_identity) != legacy_identities:
        raise TestPoolError("legacy_decisions_incomplete")

    migrated: list[dict[str, Any]] = []
    for item in ledger["assignments"]:
        if item.get("schemaVersion") != "1.0.0":
            migrated.append(dict(item))
            continue
        decision = by_identity[_identity(item)]
        verdict = decision["verdict"]
        status = "consumed" if verdict == "pass" else "awaiting_approval" if verdict == "pending" else "released"
        current: dict[str, Any] = {
            "artifactType": "test_image_assignment",
            "schemaVersion": "2.0.0",
            "producer": "style-template-analyzer",
            "deliverySetId": item["deliverySetId"],
            "templateKey": item["templateKey"],
            "revision": item["revision"],
            "assetId": item["assetId"],
            "assignedAt": item["assignedAt"],
            "status": status,
            "reviewReadyAt": decision["decidedAt"],
        }
        if verdict != "pending":
            current["decision"] = {
                "verdict": verdict,
                "authority": "human",
                "decidedAt": decision["decidedAt"],
                "reason": decision["reason"],
                "coverSha256": decision["coverSha256"],
                "promptSha256": decision["promptSha256"],
            }
        migrated.append(current)
    TestImagePool(assignments=migrated)
    return {
        "artifactType": "test_image_assignment_ledger",
        "schemaVersion": "2.0.0",
        "producer": "style-template-analyzer",
        "assignments": migrated,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("decisions", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("output_conflict")
    result = migrate(
        json.loads(args.ledger.read_text(encoding="utf-8")),
        json.loads(args.decisions.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

