"""Agent tools: list_regions, render, finish. No code execution, no filesystem access."""

from typing import Any

PLACEMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "region_id": {"type": "string", "description": "An id from list_regions."},
        "text": {"type": "string"},
        "align": {"type": "string", "enum": ["left", "center", "right"]},
        "size_scale": {"type": "number", "minimum": 0.5, "maximum": 1.5},
        "slant_deg": {"type": "number", "minimum": -15, "maximum": 15},
        "jitter": {"type": "number", "minimum": 0, "maximum": 1},
        "seed": {"type": "integer"},
    },
    "required": ["region_id", "text"],
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_regions",
        "description": "List the writeable regions (id, kind, bbox_px, baseline_px) of a page.",
        "input_schema": {
            "type": "object",
            "properties": {"page": {"type": "integer", "minimum": 1}},
            "required": ["page"],
        },
    },
    {
        "name": "render",
        "description": (
            "Render ALL placements (the complete set, not a delta) in the user's handwriting. "
            "Returns a fit report and a small preview image."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"placements": {"type": "array", "items": PLACEMENT_SCHEMA}},
            "required": ["placements"],
        },
    },
    {
        "name": "finish",
        "description": "End the turn with a short message (max two sentences) to the user.",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
]
