import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

from hwai.auth import current_user
from hwai.db import make_engine
from hwai.main import create_app
from hwai.models import User
from hwai.page.analyze import PageAnalysis, analyze_page, analyze_pages, draw_regions, load_pages

from .conftest import FIXTURES


def _analyse(name: str) -> PageAnalysis:
    return analyze_page(load_pages(FIXTURES / name)[0])


def _kinds(a: PageAnalysis, kind: str) -> list:  # type: ignore[type-arg]
    return [r for r in a.regions if r.kind == kind]


def test_planner_has_ten_lines_and_two_boxes() -> None:
    a = _analyse("planner.pdf")
    assert 9 <= len(_kinds(a, "line")) <= 11
    assert len(_kinds(a, "box")) == 2
    for line in _kinds(a, "line"):
        assert line.baseline_px is not None and line.line_height_px is not None


def test_card_blank_region_near_centre_and_off_the_border() -> None:
    a = _analyse("card.pdf")
    blanks = _kinds(a, "blank")
    assert blanks
    cx, cy = a.width / 2, a.height / 2
    assert any(
        abs((r.bbox_px[0] + r.bbox_px[2]) / 2 - cx) <= 0.15 * a.width
        and abs((r.bbox_px[1] + r.bbox_px[3]) / 2 - cy) <= 0.15 * a.height
        for r in blanks
    )
    # the printed border is a 2pt stroke 0.3in (45 px) in from every edge
    inset = 45 + 4
    for r in a.regions:
        x0, y0, x1, y1 = r.bbox_px
        assert x0 >= inset and y0 >= inset
        assert x1 <= a.width - inset and y1 <= a.height - inset


def test_blank_page_has_exactly_one_blank_region() -> None:
    a = _analyse("blank.png")
    assert [r.kind for r in a.regions] == ["blank"]
    x0, y0, x1, y1 = a.regions[0].bbox_px
    assert x0 >= 0.03 * a.width - 1 and y0 >= 0.03 * a.height - 1
    assert x1 <= 0.97 * a.width + 1 and y1 <= 0.97 * a.height + 1


def test_ids_unique_stable_bounded_and_json_deterministic() -> None:
    for name in ("planner.pdf", "card.pdf", "blank.png"):
        pages = load_pages(FIXTURES / name)
        first = json.dumps(analyze_pages(pages), sort_keys=True)
        second = json.dumps(analyze_pages(load_pages(FIXTURES / name)), sort_keys=True)
        assert first == second
        a = analyze_page(pages[0])
        ids = [r.id for r in a.regions]
        assert len(ids) == len(set(ids))
        assert all(i.startswith("p1-") for i in ids)
        for r in a.regions:
            x0, y0, x1, y1 = r.bbox_px
            assert 0 <= x0 < x1 <= a.width and 0 <= y0 < y1 <= a.height
            assert x1 - x0 >= 40 and y1 - y0 >= 40
        assert len([r for r in a.regions if r.kind == "blank"]) <= 4
    planner = _analyse("planner.pdf")
    assert planner.regions[0].id.startswith("p1-")
    assert "p1-line-03" in [r.id for r in planner.regions]


def test_draw_regions_returns_annotated_copy() -> None:
    img = load_pages(FIXTURES / "planner.pdf")[0]
    out = draw_regions(img, analyze_page(img).regions)
    assert out.size == img.size and out.tobytes() != img.tobytes()


def _other_client() -> TestClient:
    with Session(make_engine()) as db:
        other = User(email="other@local")
        db.add(other)
        db.commit()
        other_id = other.id
    app2 = create_app()

    def _other() -> User:
        with Session(make_engine()) as db:
            return db.get_one(User, other_id)

    app2.dependency_overrides[current_user] = _other
    return TestClient(app2, raise_server_exceptions=False)


def test_analysis_and_page_endpoints_with_ownership(client: TestClient) -> None:
    chat_id = client.post("/chats").json()["id"]
    with (FIXTURES / "planner.pdf").open("rb") as f:
        res = client.post(f"/chats/{chat_id}/files", files={"file": ("p.pdf", f)})
    assert res.status_code == 201
    fid = res.json()["id"]

    res = client.get(f"/chats/{chat_id}/files/{fid}/analysis")
    assert res.status_code == 200
    regions = res.json()["pages"][0]["regions"]
    assert len([r for r in regions if r["kind"] == "line"]) == 10
    assert len([r for r in regions if r["kind"] == "box"]) == 2
    assert res.json() == analyze_pages(load_pages(FIXTURES / "planner.pdf"))

    png = client.get(f"/chats/{chat_id}/files/{fid}/pages/1.png")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(png.content)).size == (1241, 1754)
    assert client.get(f"/chats/{chat_id}/files/{fid}/pages/2.png").status_code == 404
    assert client.get(f"/chats/{chat_id}/files/nope/analysis").status_code == 404

    other = _other_client()
    assert other.get(f"/chats/{chat_id}/files/{fid}/analysis").status_code == 404
    assert other.get(f"/chats/{chat_id}/files/{fid}/pages/1.png").status_code == 404


def _notebook(
    spacing: int,
    rule: tuple[int, int, int],
    margin: tuple[int, int, int] | None,
    margin_x: int = 160,
    side_inset: int = 0,
) -> tuple[Image.Image, int]:
    """Synthetic lined page: rules every `spacing` px plus an optional vertical margin."""
    w, h, top = 1240, 1754, 150
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    ys = list(range(top, h - 100, spacing))
    for y in ys:
        d.line([(side_inset, y), (w - side_inset, y)], fill=rule, width=2)
    if margin is not None:
        d.line([(margin_x, 0), (margin_x, h)], fill=margin, width=2)
    return img, len(ys)


@pytest.mark.parametrize(
    ("spacing", "rule", "margin", "margin_x", "inset"),
    [
        (52, (0, 0, 0), (220, 40, 40), 160, 0),
        (90, (200, 30, 30), (220, 40, 40), 160, 0),
        (90, (30, 60, 200), (30, 60, 200), 120, 50),
        (52, (0, 0, 0), (0, 0, 0), 200, 0),
        (52, (30, 60, 200), None, 160, 0),
    ],
)
def test_margin_line_does_not_suppress_ruled_lines(
    spacing: int,
    rule: tuple[int, int, int],
    margin: tuple[int, int, int] | None,
    margin_x: int,
    inset: int,
) -> None:
    img, expected = _notebook(spacing, rule, margin, margin_x, inset)
    a = analyze_page(img)
    lines = _kinds(a, "line")
    assert len(lines) >= 0.8 * expected
    assert not _kinds(a, "box")
    ids = [r.id for r in a.regions]
    assert len(ids) == len(set(ids))
    for r in a.regions:
        x0, y0, x1, y1 = r.bbox_px
        assert 0 <= x0 < x1 <= a.width and 0 <= y0 < y1 <= a.height
    assert analyze_page(img).model_dump_json() == a.model_dump_json()
