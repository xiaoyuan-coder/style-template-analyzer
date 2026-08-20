#!/usr/bin/env python3
"""Tests for reference semantics and independent visual comparison."""

from __future__ import annotations

import hashlib
import unittest

from style_reference_gate import validate_reference_interpretation, validate_visual_gate


def interpretation() -> dict:
    return {
        "artifactType": "reference_interpretation",
        "schemaVersion": "1.0.0",
        "producer": "reference-semantics-agent",
        "templateKey": "ink-outline",
        "referenceType": "annotated-paired-comparison",
        "extractionMode": "paired-difference",
        "sourceImages": [{
            "path": "reference.jpg",
            "sha256": hashlib.sha256(b"reference").hexdigest(),
            "roles": ["before", "target-effect", "annotation-ui", "explanatory-layout"],
        }],
        "excludedElements": ["before/after divider", "title", "color bar", "registration marks"],
        "templateConstants": [{
            "name": "rough ink contour",
            "aestheticFunction": "preserve an irregular handmade edge",
            "category": "style-effect",
            "explicitlyAuthorized": True,
        }],
        "ambiguities": [],
    }


def visual_gate() -> dict:
    scores = {
        "imagingMedium": 92,
        "shapeAndDetail": 91,
        "linesAndEdges": 94,
        "marksAndTexture": 90,
        "colorOrganization": 91,
        "compositionAndSpace": 92,
    }
    return {
        "artifactType": "reference_visual_gate_receipt",
        "schemaVersion": "1.0.0",
        "producer": "style-template-analyzer",
        "templateKey": "ink-outline",
        "revision": 1,
        "attempt": 1,
        "reviewer": "independent-vision-agent",
        "independenceDeclaration": "reviewer-did-not-author-analysis-or-prompt",
        "referenceInterpretationSha256": "a" * 64,
        "coverSha256": "b" * 64,
        "verdict": "pass",
        "scores": scores,
        "evidence": {name: f"evidence for {name}" for name in scores},
        "hardFailures": [],
    }


class ReferenceGateTests(unittest.TestCase):
    def test_paired_reference_requires_before_and_target_roles(self) -> None:
        data = interpretation()
        data["sourceImages"][0]["roles"] = ["target-effect", "annotation-ui"]
        self.assertTrue(any("before" in error for error in validate_reference_interpretation(data)))

    def test_unauthorized_explanatory_constant_is_rejected(self) -> None:
        data = interpretation()
        data["templateConstants"].append({
            "name": "before/after title",
            "aestheticFunction": "explain the comparison",
            "category": "explanatory-element",
            "explicitlyAuthorized": False,
        })
        self.assertTrue(any("未获明确授权" in error for error in validate_reference_interpretation(data)))

    def test_visual_gate_rejects_self_review(self) -> None:
        data = visual_gate()
        data["reviewer"] = "reference-semantics-agent"
        self.assertTrue(any("必须独立" in error for error in validate_visual_gate(
            data,
            analysis_producer="reference-semantics-agent",
        )))

    def test_visual_gate_rejects_pass_below_threshold(self) -> None:
        data = visual_gate()
        data["scores"]["shapeAndDetail"] = 79
        self.assertTrue(any("不得低于 80" in error for error in validate_visual_gate(data)))


if __name__ == "__main__":
    unittest.main()
