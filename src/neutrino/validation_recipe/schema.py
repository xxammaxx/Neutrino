"""JSON Schema export helper for Validation Recipes — Issue #18.

This module provides an optional JSON Schema export function for
tooling and documentation purposes.

IMPORTANT: The Python validator (``validators.validate_recipe()``)
remains the SOURCE OF TRUTH for validation. The JSON Schema is a
helper artifact for external tooling and should NOT be relied upon
as the sole mechanism for recipe validation.

It cannot express the full recursive forbidden-key detection,
scope subset validation, or conservative target classification
that the Python validator performs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neutrino.validation_recipe.models import ValidationRecipe


def export_json_schema() -> dict[str, Any]:
    """Generate a JSON Schema (Draft 2020-12) from the ValidationRecipe model.

    Returns a dict representation of the JSON Schema. This can be
    serialized to a ``.schema.json`` file for external tooling.

    The generated schema includes:
        - All required fields from ValidationRecipe and ValidationStep.
        - Enum values for step_type and safety_class.
        - Basic type constraints (string, boolean, array, object).
        - additionalProperties: false on all objects.
        - Bounds hints (but NOT the full recursive forbidden-key check).

    Returns:
        Dict representation of the JSON Schema.
    """
    schema = ValidationRecipe.model_json_schema()

    # Add schema metadata
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "ValidationRecipe"
    schema["description"] = (
        "JSON Schema for Neutrino Validation Recipes. "
        "WARNING: This schema is a helper artifact. The Python "
        "validator in neutrino.validation_recipe.validators is the "
        "source of truth for safety validation."
    )

    return schema


def export_json_schema_file(filepath: str | Path) -> Path:
    """Export the JSON Schema to a file.

    Args:
        filepath: Path to write the schema file to.

    Returns:
        Path of the written file.
    """
    filepath = Path(filepath)
    schema = export_json_schema()
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    return filepath
