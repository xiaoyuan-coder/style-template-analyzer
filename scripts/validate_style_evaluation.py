#!/usr/bin/env python3
"""Validate independent multi-case style fidelity evaluations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


KEY_RE = re.compile(r"^[a-z][a-z0-9-]{1,59}$")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
DIMENSION_LIMITS = {
    "imagingMedium": 20,
    "marksAndTexture": 20,
    "colorOrganization": 15,
    "linesAndEdges": 15,
    "shapeAndDetail": 10,
    "toneAndSpace": 10,
    "globalCoverage": 10,
}
PASSING_FLOORS = {field: maximum * 0.8 for field, maximum in DIMENSION_LIMITS.items()}


def check_text(errors: list[str], path: str, value: Any, minimum: int, maximum: int) -> None:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        errors.append(f"{path} 必须是长度 {minimum}-{maximum} 的非空字符串")


def check_asset(errors: list[str], evaluation_file: Path, path: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} 必须是图片路径或 HTTPS URL")
        return
    parsed = urlparse(value)
    if parsed.scheme:
        if parsed.scheme != "https":
            errors.append(f"{path} 远端资源必须使用 HTTPS")
        return
    resolved = (evaluation_file.parent / value).resolve()
    if resolved.suffix.lower() not in IMAGE_EXTENSIONS:
        errors.append(f"{path} 使用了不支持的图片格式")
    elif not resolved.is_file():
        errors.append(f"{path} 本地图片不存在：{resolved}")


def check_case(errors: list[str], case: Any, index: int, evaluation_file: Path) -> float | None:
    path = f"cases[{index}]"
    if not isinstance(case, dict):
        errors.append(f"{path} 必须是 object")
        return None
    required = {"id", "input", "output", "score", "verdict", "hardFailures", "dimensionScores", "evidence"}
    for field in sorted(required - set(case)):
        errors.append(f"{path}.{field} 缺失")
    check_text(errors, f"{path}.id", case.get("id"), 1, 80)
    check_asset(errors, evaluation_file, f"{path}.input", case.get("input"))
    check_asset(errors, evaluation_file, f"{path}.output", case.get("output"))
    check_text(errors, f"{path}.evidence", case.get("evidence"), 20, 1000)

    score = case.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
        errors.append(f"{path}.score 必须在 0-100 之间")
        score = None
    verdict = case.get("verdict")
    if verdict not in {"pass", "fail"}:
        errors.append(f"{path}.verdict 只能是 pass 或 fail")
    hard_failures = case.get("hardFailures")
    if not isinstance(hard_failures, list) or any(not isinstance(item, str) or not item.strip() for item in hard_failures):
        errors.append(f"{path}.hardFailures 必须是非空字符串数组")
        hard_failures = []

    dimensions = case.get("dimensionScores")
    valid_dimensions = isinstance(dimensions, dict) and set(dimensions) == set(DIMENSION_LIMITS)
    total = 0.0
    if not valid_dimensions:
        errors.append(f"{path}.dimensionScores 必须且只能包含七个评分维度")
    else:
        for field, maximum in DIMENSION_LIMITS.items():
            value = dimensions.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= maximum:
                errors.append(f"{path}.dimensionScores.{field} 必须在 0-{maximum} 之间")
                valid_dimensions = False
            else:
                total += float(value)
        if score is not None and valid_dimensions and abs(float(score) - total) > 0.001:
            errors.append(f"{path}.score 必须等于七个维度分数之和")

    if hard_failures:
        if score != 0 or verdict != "fail":
            errors.append(f"{path} 存在 hardFailures 时必须 score=0 且 verdict=fail")
    if verdict == "pass":
        if score is None or score < 90:
            errors.append(f"{path}.verdict=pass 要求 score >= 90")
        if hard_failures:
            errors.append(f"{path}.verdict=pass 要求 hardFailures 为空")
        if isinstance(dimensions, dict):
            for field, floor in PASSING_FLOORS.items():
                value = dimensions.get(field)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value < floor:
                    errors.append(f"{path}.dimensionScores.{field} 低于通过最低线 {floor:g}")
    return float(score) if score is not None else None


def validate_data(data: Any, evaluation_file: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["根节点必须是 JSON object"]
    required = {"schemaVersion", "templateKey", "testProtocol", "cases", "aggregate"}
    for field in sorted(required - set(data)):
        errors.append(f"{field} 缺失")
    if data.get("schemaVersion") != "1.0":
        errors.append("schemaVersion 必须为 1.0")
    if not isinstance(data.get("templateKey"), str) or not KEY_RE.fullmatch(data.get("templateKey", "")):
        errors.append("templateKey 格式不合法")

    protocol = data.get("testProtocol")
    if not isinstance(protocol, dict):
        errors.append("testProtocol 必须是 object")
        candidate_count = None
        independent = False
    else:
        candidate_count = protocol.get("candidateCountPerInput")
        independent = protocol.get("independentReviewer") is True
        if isinstance(candidate_count, bool) or not isinstance(candidate_count, int) or not 2 <= candidate_count <= 8:
            errors.append("testProtocol.candidateCountPerInput 必须是 2-8 的整数")

    cases = data.get("cases")
    scores: list[float] = []
    case_verdicts: list[Any] = []
    if not isinstance(cases, list) or not cases:
        errors.append("cases 必须是非空数组")
        cases = []
    ids: set[str] = set()
    for index, case in enumerate(cases):
        score = check_case(errors, case, index, evaluation_file)
        if score is not None:
            scores.append(score)
        if isinstance(case, dict):
            case_id = case.get("id")
            if isinstance(case_id, str):
                if case_id in ids:
                    errors.append(f"cases[{index}].id 重复")
                ids.add(case_id)
            case_verdicts.append(case.get("verdict"))

    aggregate = data.get("aggregate")
    if not isinstance(aggregate, dict):
        errors.append("aggregate 必须是 object")
        return errors
    aggregate_score = aggregate.get("score")
    aggregate_verdict = aggregate.get("verdict")
    check_text(errors, "aggregate.evidence", aggregate.get("evidence"), 20, 1000)
    if isinstance(aggregate_score, bool) or not isinstance(aggregate_score, (int, float)) or not 0 <= aggregate_score <= 100:
        errors.append("aggregate.score 必须在 0-100 之间")
    elif scores:
        expected = round(sum(scores) / len(scores), 2)
        if abs(float(aggregate_score) - expected) > 0.01:
            errors.append(f"aggregate.score 必须等于案例平均分 {expected:g}")
    if aggregate_verdict not in {"pass", "fail"}:
        errors.append("aggregate.verdict 只能是 pass 或 fail")
    if aggregate_verdict == "pass":
        if len(cases) < 4:
            errors.append("aggregate.verdict=pass 至少 4 个跨内容测试案例")
        if not independent:
            errors.append("aggregate.verdict=pass 必须由独立复核者评分")
        if aggregate_score is None or isinstance(aggregate_score, bool) or aggregate_score < 90:
            errors.append("aggregate.verdict=pass 要求平均分 >= 90")
        if any(verdict != "pass" for verdict in case_verdicts):
            errors.append("aggregate.verdict=pass 要求全部案例通过")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    file = args.target.resolve()
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL\n{file}: JSON 读取失败：{error}")
        return 1
    errors = validate_data(data, file)
    if errors:
        print("FAIL")
        print("\n".join(f"{file}: {error}" for error in errors))
        return 1
    print("PASS 1 evaluation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
