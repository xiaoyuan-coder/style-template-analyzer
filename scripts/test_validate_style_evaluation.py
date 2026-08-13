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
    "signatureMechanismFidelity": 28,
    "subjectFeatureContinuity": 19,
    "contentAndRelations": 14,
    "authorizedStructureAndDerivation": 14,
    "nonPhotographicCoverage": 8,
    "frameAndComposition": 8,
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
                "evidence": "标志性变换机制稳定，主体特征、服饰配件、内容关系和画幅比例均符合契约。",
            }
        )
    return {
        "schemaVersion": "2.0",
        "templateKey": "high-gloss-chrome-rendering",
        "testProtocol": {
            "candidateCountPerInput": 4,
            "independentReviewer": True,
        },
        "cases": cases,
        "aggregate": {
            "score": 91,
            "verdict": "pass",
            "evidence": "四个跨内容案例全部达到九十分，标志性机制、主体连续性与其他维度均超过最低线。",
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
                "signatureMechanismFidelity": 30,
                "subjectFeatureContinuity": 15,
                "contentAndRelations": 15,
                "authorizedStructureAndDerivation": 15,
                "nonPhotographicCoverage": 10,
                "frameAndComposition": 10,
            }
            case["score"] = 95
            data["aggregate"]["score"] = 92
            errors = MODULE.validate_data(data, root / "style-evaluation.json")
            self.assertTrue(any("subjectFeatureContinuity" in error and "最低线" in error for error in errors))

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
