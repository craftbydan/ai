"""Internal dev-only endpoints (no UI)."""

import json
from typing import Any

from fastapi import APIRouter

from hwai.config import get_settings
from hwai.errors import ApiError

router = APIRouter()


@router.get("/admin/cost")
def cost_report() -> dict[str, Any]:
    """Measured seconds and baht per page from scripts/measure_cost.py. ENV=dev only."""
    settings = get_settings()
    if settings.env != "dev":
        raise ApiError(404, "not_found", "Not found.")
    path = settings.data_dir / "cost_report.json"
    if not path.is_file():
        raise ApiError(404, "no_cost_report", "No cost report yet. Run scripts/measure_cost.py.")
    data: dict[str, Any] = json.loads(path.read_text())
    return data
