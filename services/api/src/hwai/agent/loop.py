"""Tool-use loop: user text + page images -> placements -> render -> short reply."""

import json
from dataclasses import dataclass
from typing import Any

from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from hwai import storage
from hwai.agent.prompts import SYSTEM_PROMPT
from hwai.agent.tools import TOOLS
from hwai.config import get_settings
from hwai.errors import ApiError
from hwai.llm import (  # noqa: F401  (re-exported: the injection point lives in hwai.llm)
    LazyLlmClient,
    downscale,
    get_llm_client,
    image_block,
)
from hwai.models import Chat, ChatFile, Message, Render
from hwai.page.analyze import draw_regions, load_pages
from hwai.page.regions import Region
from hwai.routes.renders import render_placements, target_file
from hwai.safety.rules import SIGNATURE_REFUSAL, check_file_allowed
from hwai.safety.signature import looks_like_signature_text
from hwai.schemas import Placement

MAX_MODEL_CALLS = 6
MAX_CONTEXT_PAGES = 3
HISTORY_TURNS = 6
APOLOGY = "Sorry, I could not finish that. Please try again with a simpler request."


def mock_agent_enabled() -> bool:
    """AGENT=mock test switch (fixed placement, no API key). Never active in production."""
    s = get_settings()
    return s.agent == "mock" and s.env.lower() not in ("prod", "production")


def run_mock_agent(db: Session, chat: Chat, text: str) -> "AgentResult":
    """Fixed placement for end-to-end tests: the user's text, centred, on the first blank
    region (else the first line or box) that is not a signature area. Uses the real render
    code, so previews and exports are genuine."""
    chat_file = target_file(db, chat)
    analysis: dict[str, Any] = chat_file.analysis_json or {"pages": []}
    regions = [Region.model_validate(r) for pg in analysis["pages"] for r in pg["regions"]]
    usable = [r for r in regions if not r.signature]
    pick = next((r for r in usable if r.kind == "blank"), usable[0] if usable else None)
    _save(db, chat, "user", {"text": text, "usage": _usage()})
    if pick is None:
        reply = "I could not find a free area to write on this file."
        _save(db, chat, "assistant", {"reply": reply, "content": [], "usage": _usage()})
        return AgentResult(reply=reply, render_version=None, preview_url=None)
    words = text.strip()
    if words.lower().startswith("write "):
        words = words[6:].strip() or text.strip()
    out = render_placements(
        db, chat, [Placement(region_id=pick.id, text=words, align="center", seed=1)]
    )
    reply = f"Done. I wrote \u201c{words}\u201d in the {pick.kind} area. Ask for changes any time."
    _save(db, chat, "assistant", {"reply": reply, "content": [], "usage": _usage(), "mock": True})
    return AgentResult(reply=reply, render_version=out.version, preview_url=out.preview_url)


def check_chat_file_allowed(chat_file: ChatFile) -> None:
    """Raise ApiError (403 file_refused) if this file was refused at upload."""
    check_file_allowed(chat_file)


def estimate_thb(input_tokens: int, output_tokens: int) -> float:
    s = get_settings()
    usd = (input_tokens * s.agent_usd_per_mtok_in + output_tokens * s.agent_usd_per_mtok_out) / 1e6
    return round(usd * s.usd_thb, 5)


def _usage(input_tokens: int = 0, output_tokens: int = 0) -> dict[str, Any]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "est_thb": estimate_thb(input_tokens, output_tokens),
    }


def _blocks_to_json(content: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for b in content:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


@dataclass
class AgentResult:
    reply: str
    render_version: int | None
    preview_url: str | None


def _save(db: Session, chat: Chat, role: str, content: dict[str, Any]) -> None:
    db.add(Message(chat_id=chat.id, role=role, content_json=content))
    db.commit()


def _latest_render(db: Session, chat: Chat) -> Render | None:
    return db.scalar(
        select(Render).where(Render.chat_id == chat.id).order_by(Render.version.desc()).limit(1)
    )


def _history(db: Session, chat: Chat) -> list[dict[str, Any]]:
    """Prior turns as plain text (user text, final assistant reply), alternating."""
    rows = db.scalars(
        select(Message).where(Message.chat_id == chat.id).order_by(Message.created_at, Message.id)
    ).all()
    clean: list[dict[str, Any]] = []
    for m in rows:
        c = m.content_json or {}
        if m.role == "user" and c.get("text"):
            turn = {"role": "user", "content": c["text"]}
        elif m.role == "assistant" and c.get("reply"):
            turn = {"role": "assistant", "content": c["reply"]}
        else:
            continue
        if clean and clean[-1]["role"] == turn["role"]:
            clean[-1] = turn
        else:
            clean.append(turn)
    clean = clean[-HISTORY_TURNS:]
    while clean and clean[0]["role"] != "user":
        clean.pop(0)
    if clean and clean[-1]["role"] == "user":
        clean.pop()  # an unanswered earlier user turn; the new message follows
    return clean


def run_agent(db: Session, chat: Chat, text: str, client: Any) -> AgentResult:
    chat_file = target_file(db, chat)
    check_chat_file_allowed(chat_file)
    if looks_like_signature_text(text):
        # Deterministic guard: a signature request never reaches the model or the renderer.
        _save(db, chat, "user", {"text": text, "usage": _usage()})
        _save(db, chat, "assistant", {"reply": SIGNATURE_REFUSAL, "content": [], "usage": _usage()})
        last = _latest_render(db, chat)
        return AgentResult(
            reply=SIGNATURE_REFUSAL,
            render_version=last.version if last else None,
            preview_url=f"/chats/{chat.id}/renders/{last.version}/preview.png" if last else None,
        )
    if mock_agent_enabled():
        return run_mock_agent(db, chat, text)
    _ = client.messages  # resolve the client (503 if unconfigured) before any DB write
    analysis: dict[str, Any] = chat_file.analysis_json or {"pages": []}
    regions_by_page: dict[int, list[Region]] = {
        n: [Region.model_validate(r) for r in pg["regions"]]
        for n, pg in enumerate(analysis["pages"], 1)
    }

    history = _history(db, chat)
    last = _latest_render(db, chat)
    pages = load_pages(storage.absolute_path(chat_file.file_path))[:MAX_CONTEXT_PAGES]
    content: list[dict[str, Any]] = []
    for n, img in enumerate(pages, 1):
        content.append({"type": "text", "text": f"Page {n} with region overlay:"})
        content.append(image_block(draw_regions(img, regions_by_page.get(n, []))))
    if last is not None:
        content.append(
            {
                "type": "text",
                "text": f"Last render (version {last.version}) placements: "
                + json.dumps(last.placements_json),
            }
        )
    content.append({"type": "text", "text": f"User: {text}"})
    messages: list[dict[str, Any]] = [*history, {"role": "user", "content": content}]

    _save(db, chat, "user", {"text": text, "usage": _usage()})
    settings = get_settings()
    render_version = last.version if last else None
    preview_url = f"/chats/{chat.id}/renders/{last.version}/preview.png" if last else None
    reply: str | None = None

    for call in range(1, MAX_MODEL_CALLS + 1):
        resp = client.messages.create(
            model=settings.agent_model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        usage = _usage(resp.usage.input_tokens, resp.usage.output_tokens)
        blocks = _blocks_to_json(resp.content)
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        texts = " ".join(b.text for b in resp.content if b.type == "text").strip()

        results: list[dict[str, Any]] = []
        log: list[dict[str, Any]] = []
        for tu in tool_uses:
            if tu.name == "finish":
                reply = str(tu.input.get("message", "")).strip() or texts or "Done."
                out: list[dict[str, Any]] = [{"type": "text", "text": "ok"}]
                is_error = False
            else:
                out, is_error, info = _run_tool(db, chat, tu, regions_by_page)
                if info is not None:
                    render_version = info["version"]
                    preview_url = info["preview_url"]
            results.append(
                {"type": "tool_result", "tool_use_id": tu.id, "content": out, "is_error": is_error}
            )
            log.append(
                {
                    "tool_use_id": tu.id,
                    "name": tu.name,
                    "is_error": is_error,
                    "result": next((o["text"] for o in out if o["type"] == "text"), ""),
                }
            )
        if not tool_uses:
            reply = texts or "Done."

        row: dict[str, Any] = {
            "content": blocks,
            "usage": usage,
            "model": settings.agent_model,
            "call": call,
        }
        if reply is not None:
            row["reply"] = reply
        _save(db, chat, "assistant", row)
        if tool_uses:
            _save(db, chat, "tool", {"results": log, "usage": _usage()})
        if reply is not None:
            break
        messages.append({"role": "assistant", "content": blocks})
        messages.append({"role": "user", "content": results})

    if reply is None:
        reply = APOLOGY
        _save(
            db,
            chat,
            "assistant",
            {"reply": reply, "content": [], "usage": _usage(), "capped": True},
        )
    return AgentResult(reply=reply, render_version=render_version, preview_url=preview_url)


def _run_tool(
    db: Session, chat: Chat, tu: Any, regions_by_page: dict[int, list[Region]]
) -> tuple[list[dict[str, Any]], bool, dict[str, Any] | None]:
    """Returns (tool_result content, is_error, render info if a render was stored)."""

    def err(msg: str) -> tuple[list[dict[str, Any]], bool, None]:
        return [{"type": "text", "text": msg}], True, None

    inp = tu.input if isinstance(tu.input, dict) else {}
    if tu.name == "list_regions":
        page = inp.get("page")
        if not isinstance(page, int) or page not in regions_by_page:
            return err(f"No page {page}. Pages: {sorted(regions_by_page)}.")
        data = [
            {
                "id": r.id,
                "kind": r.kind,
                "bbox_px": r.bbox_px,
                "baseline_px": r.baseline_px,
                "signature": r.signature,
            }
            for r in regions_by_page[page]
        ]
        return [{"type": "text", "text": json.dumps(data)}], False, None
    if tu.name == "render":
        try:
            placements = [Placement.model_validate(p) for p in inp.get("placements", [])]
            out = render_placements(db, chat, placements)
        except ValidationError as exc:
            first = exc.errors()[0]
            return err(f"Invalid placement: {first['loc']} {first['msg']}")
        except ApiError as exc:
            return err(exc.message)
        render = db.scalar(
            select(Render).where(Render.chat_id == chat.id, Render.version == out.version)
        )
        assert render is not None and render.preview_path is not None
        preview = Image.open(storage.absolute_path(render.preview_path))
        text = json.dumps({"version": out.version, "fit_report": out.fit_report.model_dump()})
        info = {"version": out.version, "preview_url": out.preview_url}
        return [{"type": "text", "text": text}, image_block(preview)], False, info
    return err(f"Unknown tool '{tu.name}'.")
