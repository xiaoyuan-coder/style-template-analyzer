#!/usr/bin/env python3
"""Public-behaviour tests for atomic JSON persistence."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from style_atomic import atomic_write_json


class AtomicJsonTests(unittest.TestCase):
    def test_same_process_threads_can_replace_one_json_without_temp_file_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "shared.json"
            barrier = threading.Barrier(12)
            errors: list[Exception] = []

            def write(index: int) -> None:
                try:
                    barrier.wait()
                    atomic_write_json(target, {"writer": index})
                except Exception as error:  # pragma: no cover - asserted below
                    errors.append(error)

            threads = [threading.Thread(target=write, args=(index,)) for index in range(12)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(2)

            self.assertEqual(errors, [])
            self.assertIn(json.loads(target.read_text(encoding="utf-8"))["writer"], range(12))
            leftovers = [
                *target.parent.glob("shared.json.tmp-*"),
                *target.parent.glob(".shared.json.tmp-*"),
            ]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
