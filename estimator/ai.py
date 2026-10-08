"""Thin wrapper around the Claude API for structured (JSON-schema) answers."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path

import anthropic

MODEL = os.environ.get("ESTIMATOR_MODEL", "claude-opus-5-5")

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    return _client


class AIError(RuntimeError):
    pass


def file_block(path: Path) -> dict:
    """Turn a PDF or image into a content block Claude can read directly."""
    data = base64.standard_b64encode(path.read_bytes()).decode()
    mime = mimetypes.guess_type(path.name)[0] or ""
    if mime == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": mime, "data": data},
                "title": path.name}
    if mime in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}}
    raise ValueError(f"Can't send {path.name} to Claude as a file (type {mime or 'unknown'})")


def structured(system: str, content: list[dict] | str, schema: dict, effort: str = "high",
               max_tokens: int = 64000) -> dict:
    """Ask Claude for a JSON answer that is guaranteed to match `schema`."""
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    with client().beta.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": content}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise AIError("Claude declined this request.")
    if msg.stop_reason == "max_tokens":
        raise AIError("Response was cut off (max_tokens). Try splitting the job into smaller parts.")
    text = next((b.text for b in msg.content if b.type == "text"), None)
    if text is None:
        raise AIError("No answer returned.")
    return json.loads(text)


def obj(properties: dict, required: list[str] | None = None) -> dict:
    """JSON-schema object helper (structured outputs needs additionalProperties: false)."""
    return {"type": "object", "properties": properties,
            "required": required if required is not None else list(properties), "additionalProperties": False}


STR = {"type": "string"}
NUM = {"type": "number"}
NUM_OR_NULL = {"type": ["number", "null"]}

LINE_ITEM_SCHEMA = obj({
    "category": STR, "selector": STR, "description": STR,
    "quantity": NUM, "unit": STR, "unit_price": NUM, "tax": NUM,
})

ROOM_SCHEMA = obj({
    "name": STR, "length_ft": NUM_OR_NULL, "width_ft": NUM_OR_NULL, "height_ft": NUM_OR_NULL,
    "floor_sf": NUM_OR_NULL, "ceiling_sf": NUM_OR_NULL, "wall_sf": NUM_OR_NULL,
    "perimeter_lf": NUM_OR_NULL, "notes": STR,
})
