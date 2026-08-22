#!/usr/bin/env python3
"""Single version router for test-image assignment contracts."""

from __future__ import annotations


ASSIGNMENT_SCHEMA_BY_VERSION = {
    "1.0.0": "test-image-assignment-v1.schema.json",
    "2.0.0": "test-image-assignment-v2.schema.json",
    "3.0.0": "test-image-assignment.schema.json",
}


def assignment_schema_name(version: object) -> str:
    """Return the matching schema; unknown values fail against the current contract."""
    return ASSIGNMENT_SCHEMA_BY_VERSION.get(
        str(version),
        ASSIGNMENT_SCHEMA_BY_VERSION["3.0.0"],
    )
