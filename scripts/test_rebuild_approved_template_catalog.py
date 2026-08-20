#!/usr/bin/env python3

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rebuild_approved_template_catalog import ApprovedEntry, CatalogError, publish_entry


class ApprovedCatalogMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "style-template.json").write_text(
            json.dumps({"key": "sample-style", "title": "示例", "cover": "https://assets.example/a.png"}),
            encoding="utf-8",
        )
        (self.source / "cover.png").write_bytes(b"approved-cover")
        self.evidence = self.root / "decision.json"
        self.evidence.write_text('{"verdict":"pass"}', encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def entry(self, *, rewrite_cover_local: bool = False) -> ApprovedEntry:
        return ApprovedEntry(
            key="sample-style",
            revision=1,
            title="示例",
            template_source=self.source / "style-template.json",
            cover_source=self.source / "cover.png",
            approval_provenance="legacy-batch-human-pass",
            approval_evidence=self.evidence,
            source_package=self.source,
            rewrite_cover_local=rewrite_cover_local,
        )

    def test_publish_is_additive_and_idempotent(self) -> None:
        output = self.root / "approved"
        publish_entry(self.entry(), output, self.root, "2026-08-20T00:00:00+00:00")
        publish_entry(self.entry(), output, self.root, "2026-08-20T00:00:01+00:00")
        package = output / "sample-style/1/package"
        self.assertTrue((package / "style-template.json").is_file())
        self.assertEqual((package / "cover.png").read_bytes(), b"approved-cover")

    def test_local_cover_rewrite_marks_approved_visual(self) -> None:
        output = self.root / "approved"
        publish_entry(self.entry(rewrite_cover_local=True), output, self.root, "2026-08-20T00:00:00+00:00")
        template = json.loads((output / "sample-style/1/package/style-template.json").read_text(encoding="utf-8"))
        record = json.loads(
            (output / "sample-style/1/internal/catalog-migration-record.json").read_text(encoding="utf-8")
        )
        self.assertEqual(template["cover"], "cover.png")
        self.assertEqual(record["coverPolicy"], "local-approved-cover-awaiting-oss")

    def test_conflicting_destination_aborts(self) -> None:
        output = self.root / "approved"
        publish_entry(self.entry(), output, self.root, "2026-08-20T00:00:00+00:00")
        (output / "sample-style/1/package/cover.png").write_bytes(b"changed")
        with self.assertRaisesRegex(CatalogError, "destination_conflict"):
            publish_entry(self.entry(), output, self.root, "2026-08-20T00:00:01+00:00")


if __name__ == "__main__":
    unittest.main()
