"""Tool-use loop: user text + page images -> placements -> render -> short reply."""

import base64
import io
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
from hwai.models import Chat, ChatFile, Message, Render
from hwai.page.analyze import draw_regions, load_pages
from hwai.page.regions import Region
from hwai.routes.renders import render_placements, target_file
from hwai.schemas import Placement

MAX_MODEL_CALLS = 6
MAX_IMAGE_EDGE = 1200
MAX_CONTEXT_PAGES = 3
HISTORY_TURNS = 6
APOLOGY = "Sorry, I could not finish that. Please try again with a simpler request."


class LazyLlmClient:
    """Resolves the real Anthropic client on first use, so a missing key only raises the
    503 when a model call is actually needed (after ownership/readiness/file checks)."""

    def __init__(self) -> None:
        self._client: Any = None

    @property
    def messages(self) -> Any:
        if self._client is None:
            settings = get_settings()
            if not settings.anthropic_api_key:
                raise ApiError(503, "agent_not_configured", "The chat assistant is not set up yet.")
            import anthropic

            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return self._client.messages


def get_llm_client() -> Any:
    """FastAPI dependency and injection point. Tests override it with a scripted fake.
    Never raises: the 503 is deferred to first use of `.messages`."""
    return LazyLlmClient()


def check_chat_file_allowed(chat_file: ChatFile) -> None:
    """HOOK for Prompt 9: raise ApiError if this file must not be written on.
    Currently allows everything."""
    return None


def downscale(img: Image.Image, max_edge: int = MAX_IMAGE_EDGE) -> Image.Image:
    """Long edge <= max_edge, aspect kept (never upscales)."""
    scale = max_edge / max(img.size)
    if scale >= 1:
        return img
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))))


def image_block(img: Image.Image) -> dict[str, Any]:
    buf = io.BytesIO()
    downscale(img.convert("RGB")).save(buf, format="PNG", optimize=True)
    data = base64.b64encode(buf.getvalue()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}


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
            {"id": r.id, "kind": r.kind, "bbox_px": r.bbox_px, "baseline_px": r.baseline_px}
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
