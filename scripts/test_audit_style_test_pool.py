#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audit_style_test_pool import audit
from style_test_pool import TestImagePool
from test_style_v3_foundations import TestImagePoolTests


class AuditStyleTestPoolTests(unittest.TestCase):
    def test_reports_catalog_and_global_available_capacity(self) -> None:
        fixture = TestImagePoolTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool_file = root / "pool.json"
            ledger_file = root / "ledger.json"
            pool = TestImagePool([
                fixture.asset("asset-a", "a" * 64, "0" * 16),
                fixture.asset("asset-b", "b" * 64, "f" * 16),
            ])
            pool.save(pool_file, ledger_file)
            pool.reserve_persisted("delivery-1", "template-a", 1, ledger_file)
            result = audit(pool_file, ledger_file)
            self.assertEqual(result["capacity"]["catalogReady"], 2)
            self.assertEqual(result["capacity"]["ready"], 1)
            self.assertEqual(result["assignmentCount"], 1)
            self.assertEqual(result["sameDeliverySetHistoricalReuseCount"], 0)
            self.assertFalse(result["migrationRequired"])


if __name__ == "__main__":
    unittest.main()
