#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("validate_style_evaluation.py")
SPEC = importlib.util.spec_from_file_location("validate_style_evaluation", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


PASSING_DIMENSIONS = {
    "imagingMedium": 19,
    "marksAndTexture": 18,
    "colorOrganization": 14,
    "linesAndEdges": 14,
    "shapeAndDetail": 9,
    "toneAndSpace": 8,
    "globalCoverage": 9,
}


def evaluation(root: Path, case_count: int = 4) -> dict:
    cases = []
    for index in range(case_count):
        input_name = f"input-{index}.png"
        output_name = f"output-{index}.png"
        (root / input_name).write_bytes(b"input")
        (root / output_name).write_bytes(b"output")
        cases.append(
            {
                "id": f"case-{index}",
                "input": f"./{input_name}",
                "output": f"./{output_name}",
                "score": 91,
                "verdict": "pass",
                "hardFailures": [],
                "dimensionScores": dict(PASSING_DIMENSIONS),
                "evidence": "目标媒介、核心纹理、配色、线条与形体均接近参考图，输入内容保持稳定。",
            }
        )
    return {
        "schemaVersion": "1.0",
        "templateKey": "high-gloss-chrome-rendering",
        "testProtocol": {
            "candidateCountPerInput": 4,
            "independentReviewer": True,
        },
        "cases": cases,
        "aggregate": {
            "score": 91,
            "verdict": "pass",
            "evidence": "四个跨内容案例全部达到九十分，关键风格维度均超过各自最低线。",
        },
    }


class EvaluationValidatorTests(unittest.TestCase):
    def test_accepts_four_case_independent_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(MODULE.validate_data(evaluation(root), root / "style-evaluation.json"), [])

    def test_rejects_single_case_false_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = evaluation(root, case_count=1)
            errors = MODULE.validate_data(data, root / "style-evaluation.json")
            self.assertTrue(any("至少 4 个" in error for error in errors))

    def test_rejects_pass_with_weak_critical_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = evaluation(root)
            case = data["cases"][0]
            case["dimensionScores"] = {
                "imagingMedium": 20,
                "marksAndTexture": 15,
                "colorOrganization": 15,
                "linesAndEdges": 15,
                "shapeAndDetail": 10,
                "toneAndSpace": 10,
                "globalCoverage": 10,
            }
            case["score"] = 95
            data["aggregate"]["score"] = 92
            errors = MODULE.validate_data(data, root / "style-evaluation.json")
            self.assertTrue(any("marksAndTexture" in error and "最低线" in error for error in errors))

    def test_rejects_non_independent_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = evaluation(root)
            data["testProtocol"]["independentReviewer"] = False
            errors = MODULE.validate_data(data, root / "style-evaluation.json")
            self.assertTrue(any("独立复核" in error for error in errors))

    def test_rejects_hard_failure_with_nonzero_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = evaluation(root)
            case = data["cases"][0]
            case["hardFailures"] = ["参考内容泄漏"]
            errors = MODULE.validate_data(data, root / "style-evaluation.json")
            self.assertTrue(any("hardFailures" in error and "score=0" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
