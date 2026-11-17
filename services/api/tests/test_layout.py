import io
from pathlib import Path

import numpy as np
import pikepdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from hwai.layout.place import PlacedText, compose, layout_text
from hwai.page.analyze import analyze_page, load_pages
from hwai.page.regions import Region
from hwai.render.fake import FakeRenderer

from .conftest import FIXTURES
from .test_page_analysis import _other_client


def _region(name: str, rid: str) -> tuple[Image.Image, Region]:
    page = load_pages(FIXTURES / name)[0]
    return page, next(r for r in analyze_page(page).regions if r.id == rid)


def _place(region: Region, text: str, seed: int = 1, **kw: object) -> PlacedText:
    args: dict[str, object] = {
        "align": "center",
        "size_scale": 1.0,
        "slant_deg": 0.0,
        "jitter": 0.5,
    }
    args.update(kw)
    return layout_text(region, text, seed=seed, renderer=FakeRenderer(), style_refs=[], **args)  # type: ignore[arg-type]


def _ink_bbox(pt: PlacedText) -> tuple[int, int, int, int]:
    x0 = min(w.x for w in pt.words)
    y0 = min(w.y for w in pt.words)
    x1 = max(w.x + w.image.width for w in pt.words)
    y1 = max(w.y + w.image.height for w in pt.words)
    return x0, y0, x1, y1


def _inside(pt: PlacedText) -> bool:
    bx0, by0, bx1, by1 = pt.bbox_px
    return all(
        w.x >= bx0 and w.y >= by0 and w.x + w.image.width <= bx1 and w.y + w.image.height <= by1
        for w in pt.words
    )


def test_card_text_centred_and_inside_region() -> None:
    page, region = _region("card.pdf", "p1-blank-01")
    pt = _place(region, "Happy birthday! Wishing you a great year.")
    assert pt.fit and pt.words and _inside(pt)
    x0, y0, x1, y1 = _ink_bbox(pt)
    rx0, ry0, rx1, ry1 = region.bbox_px
    assert abs((x0 + x1) / 2 - (rx0 + rx1) / 2) <= 0.05 * region.width
    assert abs((y0 + y1) / 2 - (ry0 + ry1) / 2) <= 0.05 * region.height
    # every changed pixel of the composed page lies inside the region box
    out = np.array(compose(page, [pt])).astype(int)
    diff = np.abs(out - np.array(page).astype(int)).sum(axis=2) > 0
    ys, xs = np.nonzero(diff)
    assert ys.size and xs.min() >= rx0 and xs.max() < rx1 and ys.min() >= ry0 and ys.max() < ry1


def test_three_lines_sit_on_planner_baselines() -> None:
    page = load_pages(FIXTURES / "planner.pdf")[0]
    regions = [r for r in analyze_page(page).regions if r.kind == "line"][:3]
    placed = [_place(r, "Monday more work", align="left") for r in regions]
    for r, pt in zip(regions, placed, strict=True):
        assert r.baseline_px is not None and _inside(pt)
        # ink bottoms of non-descending letters: take the lower quartile mass
        bottoms = sorted(w.y + w.image.height for w in pt.words)
        assert any(abs(b - r.baseline_px) <= 6 for b in bottoms)
        assert min(bottoms) <= r.baseline_px + 6


def test_too_long_text_reports_no_fit_and_stays_inside() -> None:
    page, region = _region("planner.pdf", "p1-box-01")
    pt = _place(region, "lorem ipsum dolor sit amet " * 30)
    assert not pt.fit and pt.cut_words > 0 and pt.words
    assert _inside(pt)
    small = _place(region, "x " * 400)
    assert _inside(small)


def test_seed_determinism() -> None:
    page, region = _region("card.pdf", "p1-blank-01")
    a = compose(page, [_place(region, "Hello there friend", seed=1)])
    b = compose(page, [_place(region, "Hello there friend", seed=1)])
    c = compose(page, [_place(region, "Hello there friend", seed=2)])
    assert a.tobytes() == b.tobytes()
    assert a.tobytes() != c.tobytes()


def test_repeated_word_gives_distinct_images() -> None:
    _, region = _region("card.pdf", "p1-blank-01")
    pt = _place(region, "the the the the the")
    assert len(pt.words) == 5
    assert len({w.image.tobytes() for w in pt.words}) == 5


def _setup(client: TestClient, name: str = "card.pdf") -> str:
    chat_id = client.post("/chats").json()["id"]
    with (FIXTURES / name).open("rb") as f:
        assert client.post(f"/chats/{chat_id}/files", files={"file": (name, f)}).status_code == 201
    return chat_id


def _body(text: str, rid: str = "p1-blank-01", seed: int = 1) -> dict[str, object]:
    return {
        "placements": [
            {
                "region_id": rid,
                "text": text,
                "align": "center",
                "size_scale": 1.0,
                "slant_deg": 0,
                "jitter": 0.5,
                "seed": seed,
            }
        ]
    }


def test_render_endpoint_flow(client: TestClient) -> None:
    chat_id = _setup(client)
    original = Image.open(
        io.BytesIO(
            client.get(f"/chats/{chat_id}/files/{_fid(client, chat_id)}/pages/1.png").content
        )
    ).convert("RGB")
    r1 = client.post(f"/chats/{chat_id}/render", json=_body("Happy birthday! Wishing you."))
    assert r1.status_code == 200, r1.text
    assert r1.json()["version"] == 1 and r1.json()["fit_report"]["all_fit"] is True
    p1 = client.get(r1.json()["preview_url"]).content
    r1b = client.post(f"/chats/{chat_id}/render", json=_body("Happy birthday! Wishing you."))
    assert r1b.json()["version"] == 2
    assert client.get(r1b.json()["preview_url"]).content == p1
    r2 = client.post(f"/chats/{chat_id}/render", json=_body("Happy birthday! Wishing you.", seed=2))
    assert client.get(r2.json()["preview_url"]).content != p1

    region = next(r for r in analyze_page(original).regions if r.id == "p1-blank-01")
    prev = Image.open(io.BytesIO(p1)).convert("RGB")
    diff = np.abs(np.array(prev).astype(int) - np.array(original).astype(int)).sum(axis=2) > 0
    ys, xs = np.nonzero(diff)
    x0, y0, x1, y1 = region.bbox_px
    assert ys.size and xs.min() >= x0 and xs.max() < x1 and ys.min() >= y0 and ys.max() < y1


def _fid(client: TestClient, chat_id: str) -> str:
    return str(client.get(f"/chats/{chat_id}").json()["files"][0]["id"])


def test_render_validation_and_small_box(client: TestClient) -> None:
    chat_id = _setup(client)
    assert client.post(f"/chats/{chat_id}/render", json=_body("a" * 3000)).status_code == 422
    bad = _body("hi")
    bad["placements"][0]["size_scale"] = 3  # type: ignore[index]
    assert client.post(f"/chats/{chat_id}/render", json=bad).status_code == 422
    unknown = client.post(f"/chats/{chat_id}/render", json=_body("hi", rid="p9-box-99"))
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "unknown_region"
    assert "p9-box-99" in unknown.json()["error"]["message"]

    planner = _setup(client, "planner.pdf")
    res = client.post(f"/chats/{planner}/render", json=_body("word " * 80, rid="p1-box-01"))
    assert res.status_code == 200
    item = res.json()["fit_report"]["placements"][0]
    assert item["fit"] is False or item["shrink"] < 1.0


def test_export_pdf_png_and_ownership(client: TestClient) -> None:
    chat_id = _setup(client)
    v = client.post(f"/chats/{chat_id}/render", json=_body("Happy birthday!")).json()["version"]
    pdf = client.post(f"/chats/{chat_id}/export?version={v}&format=pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    with pikepdf.open(io.BytesIO(pdf.content)) as doc:
        assert "AI-generated" in str(doc.docinfo["/Keywords"])
        box = [float(x) for x in doc.pages[0].MediaBox]
    orig = pikepdf.open(FIXTURES / "card.pdf")
    obox = [float(x) for x in orig.pages[0].MediaBox]
    assert box == pytest.approx(obox, abs=0.5)
    png = client.post(f"/chats/{chat_id}/export?version={v}&format=png")
    assert png.status_code == 200
    img = Image.open(io.BytesIO(png.content))
    assert img.size == (750, 1050) and img.text.get("ai_generated") == "true"

    assert client.post(f"/chats/{chat_id}/export?version=99&format=pdf").status_code == 404
    other = _other_client()
    assert other.post(f"/chats/{chat_id}/export?version={v}&format=pdf").status_code == 404
    assert other.get(f"/chats/{chat_id}/renders/{v}/preview.png").status_code == 404
    assert other.post(f"/chats/{chat_id}/render", json=_body("hi")).status_code == 404


def test_multi_page_render(client: TestClient, tmp_path: Path) -> None:
    from hwai.export import export_pdf

    pages = [Image.open(FIXTURES / "blank.png").convert("RGB")] * 2
    pdf = tmp_path / "two.pdf"
    pdf.write_bytes(export_pdf([p.resize((750, 1050)) for p in pages], (360, 504)))
    chat_id = client.post("/chats").json()["id"]
    with pdf.open("rb") as f:
        assert (
            client.post(f"/chats/{chat_id}/files", files={"file": ("t.pdf", f)}).status_code == 201
        )
    regions = client.get(f"/chats/{chat_id}/files/{_fid(client, chat_id)}/analysis").json()["pages"]
    assert len(regions) == 2
    rid = next((r["id"] for r in regions[1]["regions"]), None)
    if rid is None:
        pytest.skip("no region on page 2 of the synthetic file")
    res = client.post(f"/chats/{chat_id}/render", json=_body("page two", rid=rid))
    assert res.status_code == 200
    assert client.get(res.json()["preview_url"] + "?page=2").status_code == 200
    assert client.get(res.json()["preview_url"] + "?page=3").status_code == 404
