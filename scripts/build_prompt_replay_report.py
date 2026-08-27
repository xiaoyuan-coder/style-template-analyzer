#!/usr/bin/env python3
"""Build a hash-bound dynamic replay report from reviewed candidate outputs."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recompile_approved_runtime_prompts import COMPILER_VERSION, sha256_file
from style_atomic import atomic_write_json


def resolve_from(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def relative_to_report(path: Path, report_file: Path) -> str:
    return os.path.relpath(path, report_file.parent)


def mechanism_rows(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list) or not values or not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError("mechanisms must be a non-empty string array")
    return [{"name": value.strip(), "status": "pass"} for value in values]


def replay_row(
    *,
    source: Path,
    generated: Path,
    score: Any,
    mechanisms: Any,
    prompt_sha256: str,
    report_file: Path,
) -> dict[str, Any]:
    if not source.is_file() or not generated.is_file():
        raise ValueError(f"missing replay asset: source={source}, generated={generated}")
    if not isinstance(score, (int, float)) or not 0 <= score <= 100:
        raise ValueError(f"score must be 0-100: {score}")
    required = mechanism_rows(mechanisms)
    verdict = "pass" if score >= 95 else "fail"
    return {
        "verdict": verdict,
        "score": score,
        "promptSha256": prompt_sha256,
        "sourcePath": relative_to_report(source, report_file),
        "sourceSha256": sha256_file(source),
        "imageInputCount": 1,
        "approvedAfterUsedAsRuntimeInput": False,
        "requiredMechanisms": required,
        "generatedPath": relative_to_report(generated, report_file),
        "generatedSha256": sha256_file(generated),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates_root", type=Path)
    parser.add_argument("assessment", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    candidates_root = args.candidates_root.resolve()
    assessment_file = args.assessment.resolve()
    output_file = args.output.resolve()
    assessment = json.loads(assessment_file.read_text(encoding="utf-8"))
    transfer_sources = [resolve_from(assessment_file.parent, value) for value in assessment.get("transferSources", [])]
    if len(transfer_sources) != 2:
        raise ValueError("assessment.transferSources must contain exactly two paths")

    items = []
    for reviewed in assessment.get("items", []):
        key = reviewed["key"]
        candidate_root = candidates_root / key
        receipt = json.loads((candidate_root / "candidate-receipt.json").read_text(encoding="utf-8"))
        source = next(path for path in sorted((candidate_root / "runtime-input").glob("source.*")) if path.is_file())
        prompt_sha256 = receipt["newPromptSha256"]
        scores = reviewed["scores"]
        mechanisms = reviewed["mechanisms"]
        original = replay_row(
            source=source,
            generated=candidate_root / "replay" / "original.png",
            score=scores["original"],
            mechanisms=mechanisms,
            prompt_sha256=prompt_sha256,
            report_file=output_file,
        )
        transfers = [
            replay_row(
                source=transfer_source,
                generated=candidate_root / "replay" / f"transfer-{index + 1}.png",
                score=scores[f"transfer{index + 1}"],
                mechanisms=mechanisms,
                prompt_sha256=prompt_sha256,
                report_file=output_file,
            )
            for index, transfer_source in enumerate(transfer_sources)
        ]
        items.append({
            "key": key,
            "assessmentNote": reviewed.get("note", ""),
            "originalReplay": original,
            "transferReplays": transfers,
        })

    atomic_write_json(output_file, {
        "artifactType": "style_prompt_replay_batch",
        "schemaVersion": "1.0.0",
        "producer": "style-template-analyzer",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "compilerVersion": COMPILER_VERSION,
        "assessmentAuthority": "visual-comparison-against-approved-after-and-mechanism-checklist",
        "status": "pass" if all(
            item["originalReplay"]["verdict"] == "pass"
            and all(replay["verdict"] == "pass" for replay in item["transferReplays"])
            for item in items
        ) else "fail",
        "items": items,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
