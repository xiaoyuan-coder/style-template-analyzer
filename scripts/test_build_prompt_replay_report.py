#!/usr/bin/env python3

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from build_prompt_replay_report import replay_row


class PromptReplayReportTests(unittest.TestCase):
    def test_replay_row_binds_assets_and_uses_95_point_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            generated = root / "generated.png"
            report = root / "reports" / "prompt-replay-report.json"
            source.write_bytes(b"source")
            generated.write_bytes(b"generated")

            row = replay_row(
                source=source,
                generated=generated,
                score=95,
                mechanisms=["主结构出现", "来源角色完成映射"],
                prompt_sha256="a" * 64,
                report_file=report,
            )

            self.assertEqual(row["verdict"], "pass")
            self.assertEqual(row["imageInputCount"], 1)
            self.assertFalse(row["approvedAfterUsedAsRuntimeInput"])
            self.assertEqual(len(row["sourceSha256"]), 64)
            self.assertEqual(len(row["generatedSha256"]), 64)

    def test_report_schema_accepts_two_transfer_replays(self) -> None:
        schema_path = Path(__file__).parents[1] / "contracts" / "prompt-replay-report.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        replay = {
            "verdict": "pass",
            "score": 95,
            "promptSha256": "a" * 64,
            "sourcePath": "inputs/source.png",
            "sourceSha256": "b" * 64,
            "imageInputCount": 1,
            "approvedAfterUsedAsRuntimeInput": False,
            "requiredMechanisms": [{"name": "主结构出现", "status": "pass"}],
            "generatedPath": "outputs/generated.png",
            "generatedSha256": "c" * 64,
        }
        report = {
            "artifactType": "style_prompt_replay_batch",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "createdAt": "2026-08-26T00:00:00Z",
            "compilerVersion": "3.0.0",
            "assessmentAuthority": "human-visual-review",
            "status": "pass",
            "items": [{
                "key": "fixture-style",
                "assessmentNote": "通过",
                "originalReplay": replay,
                "transferReplays": [dict(replay), dict(replay)],
            }],
        }
        Draft202012Validator(schema).validate(report)


if __name__ == "__main__":
    unittest.main()
