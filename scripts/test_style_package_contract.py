#!/usr/bin/env python3
"""Contract tests for package manifests and the unified validation seam."""

from __future__ import annotations

import json
import base64
import tempfile
import unittest
from pathlib import Path

from style_contracts import ARTIFACT_SPECS, LEGACY_STAGE_REQUIREMENTS, V3_STAGE_REQUIREMENTS, V6_STAGE_REQUIREMENTS, V7_STAGE_REQUIREMENTS, build_manifest
from test_validate_style_analysis import analysis
from test_validate_style_evaluation import evaluation
from test_validate_style_template import template
from validate_style_manifest import validate_data as validate_manifest
from validate_style_package import validate_package
from validate_style_template import validate_data as validate_template


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class StylePackageContractTests(unittest.TestCase):
    def test_registry_and_runtime_contracts_match(self) -> None:
        root = Path(__file__).parents[1]
        registry = json.loads((root / "contracts" / "contract-registry.json").read_text(encoding="utf-8"))
        schema = json.loads((root / "contracts" / "artifact-manifest.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {key: value["schemaVersion"] for key, value in registry["artifactTypes"].items()},
            {key: value["schemaVersion"] for key, value in ARTIFACT_SPECS.items()},
        )
        self.assertEqual(
            {key: set(value) for key, value in registry["legacyStages"].items()},
            LEGACY_STAGE_REQUIREMENTS,
        )
        self.assertEqual(
            {key: set(value) for key, value in registry["v3Stages"].items()},
            V3_STAGE_REQUIREMENTS,
        )
        self.assertEqual(
            {key: set(value) for key, value in registry["v6Stages"].items()},
            V6_STAGE_REQUIREMENTS,
        )
        self.assertEqual(
            {key: set(value) for key, value in registry["v7Stages"].items()},
            V7_STAGE_REQUIREMENTS,
        )
        self.assertIn(registry["schemaVersion"], schema["properties"]["schemaVersion"]["enum"])

    def package(self, root: Path, *, with_evaluation: bool) -> None:
        (root / "style.png").write_bytes(b"image")
        analysis_data = analysis()
        analysis_data["templateKey"] = "high-gloss-chrome-rendering"
        write_json(root / "style-analysis.json", analysis_data)
        write_json(root / "style-template.json", template())
        if with_evaluation:
            data = evaluation(root)
            write_json(root / "style-evaluation.json", data)

    def test_authoring_manifest_and_package_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.package(root, with_evaluation=False)
            manifest = build_manifest(root, "authoring")
            write_json(root / "artifact-manifest.json", manifest)
            self.assertEqual(validate_manifest(manifest, root / "artifact-manifest.json"), [])
            errors, summary = validate_package(root, "authoring", "local", "", "")
            self.assertEqual(errors, [])
            self.assertEqual(summary["manifests"], 1)

    def test_release_requires_passing_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.package(root, with_evaluation=True)
            manifest = build_manifest(root, "evaluation")
            write_json(root / "artifact-manifest.json", manifest)
            errors, _ = validate_package(root, "release", "local", "", "")
            self.assertEqual(errors, [])

    def test_manifest_detects_business_file_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.package(root, with_evaluation=False)
            manifest = build_manifest(root, "authoring")
            write_json(root / "style-template.json", {"changed": True})
            errors = validate_manifest(manifest, root / "artifact-manifest.json")
            self.assertTrue(any("sha256" in error for error in errors))

    def test_legacy_profile_accepts_packages_without_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.package(root, with_evaluation=False)
            legacy = analysis()
            legacy["templateKey"] = "high-gloss-chrome-rendering"
            legacy["schemaVersion"] = "2.0"
            legacy["transformationContract"]["contentInvariants"] = [
                "subject-set",
                "subject-features",
                "associated-objects",
                "key-relationships",
                "source-frame",
            ]
            legacy["transformationContract"]["framePolicy"] = "inherit-source-aspect-ratio"
            write_json(root / "style-analysis.json", legacy)
            errors, _ = validate_package(root, "legacy", "local", "", "")
            self.assertEqual(errors, [])

    def test_legacy_profile_accepts_effect_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "effect.png").write_bytes(b"legacy")
            data = template("effect.png")
            write_json(root / "style-template.json", data)
            errors, _ = validate_package(root, "legacy", "local", "", "")
            self.assertEqual(errors, [])

    def test_remote_sample_is_self_validating(self) -> None:
        sample = Path(__file__).parents[1] / "references" / "style-template-import.sample.json"
        data = json.loads(sample.read_text(encoding="utf-8"))
        self.assertEqual(
            validate_template(data, sample, "remote", "assets.memebuy.local", ""),
            [],
        )

    def test_v3_fast_package_manifest_and_two_file_package_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "package"
            internal = root / "internal"
            package.mkdir()
            internal.mkdir()
            data = template()
            data["cover"] = "cover.png"
            write_json(package / "style-template.json", data)
            (package / "cover.png").write_bytes(PNG)
            analysis_data = analysis()
            analysis_data["templateKey"] = data["key"]
            write_json(internal / "style-analysis.json", analysis_data)
            write_json(internal / "test-image-assignment.json", {
                "artifactType": "test_image_assignment",
                "schemaVersion": "1.0.0",
                "producer": "style-template-analyzer",
                "deliverySetId": "delivery-1",
                "templateKey": data["key"],
                "revision": 1,
                "assetId": "asset-a",
                "assignedAt": "2026-08-17T00:00:00Z",
                "status": "committed",
            })
            write_json(internal / "cover-generation-receipt.json", {
                "artifactType": "cover_generation_receipt",
                "schemaVersion": "1.0.0",
                "producer": "style-template-analyzer",
                "templateKey": data["key"],
                "revision": 1,
                "assetId": "asset-a",
                "provider": {"model": "fake"},
            })

            manifest = build_manifest(root, "package", schema_version="2.0.0")
            write_json(root / "artifact-manifest.json", manifest)

            self.assertEqual(validate_manifest(manifest, root / "artifact-manifest.json"), [])
            errors, summary = validate_package(root, "fast-package", "local", "", "")
            self.assertEqual(errors, [])
            self.assertEqual(summary["covers"], 1)
            self.assertEqual(sorted(path.name for path in package.iterdir()), ["cover.png", "style-template.json"])

            assignment_file = internal / "test-image-assignment.json"
            assignment = json.loads(assignment_file.read_text(encoding="utf-8"))
            assignment["revision"] = "bad"
            write_json(assignment_file, assignment)
            write_json(root / "artifact-manifest.json", build_manifest(root, "package", schema_version="2.0.0"))
            errors, _ = validate_package(root, "fast-package", "local", "", "")
            self.assertTrue(any("'bad' is not of type 'integer'" in error for error in errors))

            assignment["revision"] = 1
            write_json(assignment_file, assignment)
            receipt_file = internal / "cover-generation-receipt.json"
            receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
            receipt["provider"] = []
            write_json(receipt_file, receipt)
            write_json(root / "artifact-manifest.json", build_manifest(root, "package", schema_version="2.0.0"))
            errors, _ = validate_package(root, "fast-package", "local", "", "")
            self.assertTrue(any("[] is not of type 'object'" in error for error in errors))

            receipt["provider"] = {"model": "fake"}
            write_json(receipt_file, receipt)
            write_json(root / "artifact-manifest.json", build_manifest(root, "package", schema_version="2.0.0"))

            (package / "leak").mkdir()
            (package / "leak" / "private.txt").write_text("no", encoding="utf-8")
            errors, _ = validate_package(root, "fast-package", "local", "", "")
            self.assertTrue(any("必须且只能包含" in error for error in errors))

    def test_v3_fast_package_rejects_unknown_manifest_major(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "artifactType": "style_template_package",
                "schemaVersion": "7.0.0",
                "producer": "style-template-analyzer",
                "status": "completed",
                "revision": 1,
                "contractStatus": "verified",
                "stage": "package",
                "templateKey": "high-gloss-chrome-rendering",
                "artifacts": [{
                    "path": "package/style-template.json",
                    "artifactType": "style_template",
                    "schemaVersion": "1.0.0",
                    "officialShape": True,
                    "sha256": "0" * 64,
                }],
            }
            errors = validate_manifest(manifest, root / "artifact-manifest.json", verify_files=False)
            self.assertIn("failed: contract_version_unsupported", errors)


if __name__ == "__main__":
    unittest.main()
