#!/usr/bin/env python3
"""Fixture tests for non-API Smithsonian and LOC metadata adapters."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from style_institutional_source import collect_source, parse_loc_jsonl, parse_smithsonian_jsonl


class InstitutionalSourceTests(unittest.TestCase):
    def test_smithsonian_cc0_record_requires_visual_confirmation(self) -> None:
        item = {
            "id": "fixture",
            "unitCode": "NMAH",
            "content": {"descriptiveNonRepeating": {
                "record_ID": "fixture",
                "record_link": "https://www.si.edu/object/fixture",
                "title": {"content": "Fixture object"},
                "online_media": {"media": [{
                    "type": "Images", "usage": {"access": "CC0"},
                    "content": "https://ids.si.edu/ids/deliveryService?id=fixture",
                }]},
            }},
        }
        records = parse_smithsonian_jsonl(json.dumps(item), "object", True, 1)
        self.assertEqual(records[0]["license"], "CC0")
        self.assertFalse(records[0]["photographic"])
        self.assertIn("museum-object-review", records[0]["riskLabels"])

    def test_loc_public_domain_photo_requires_visual_person_check(self) -> None:
        item = {
            "Id": "fixture",
            "Url": "https://www.loc.gov/pictures/item/fixture/",
            "Title": "Woman cooking in a kitchen",
            "Medium": ["1 photographic print"],
            "Genre": ["Photographs"],
            "Description": "A woman cooking dinner",
            "Rights": ["Public domain"],
            "Preview_url": ["https://tile.loc.gov/storage-services/service/pnp/fixture.jpg#h=1024&w=800"],
            "Creators": [{"Name": "Fixture Photographer"}],
        }
        records = parse_loc_jsonl(json.dumps(item), 1)
        self.assertEqual(records[0]["rightsStatus"], "verified")
        self.assertEqual(records[0]["category"], "food")
        self.assertFalse(records[0]["photographic"])

    def test_completed_checkpoint_is_reused_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "loc.json"
            checkpoint.write_text(json.dumps({
                "artifactType": "style_source_metadata_checkpoint",
                "schemaVersion": "2.0.0",
                "producer": "style-template-analyzer",
                "source": "loc",
                "records": [{"sourcePageUrl": "fixture"}],
                "status": "completed",
            }), encoding="utf-8")
            result = collect_source("loc", 1, checkpoint, fetcher=lambda _: self.fail("network called"))
            self.assertEqual(result["records"][0]["sourcePageUrl"], "fixture")


if __name__ == "__main__":
    unittest.main()
