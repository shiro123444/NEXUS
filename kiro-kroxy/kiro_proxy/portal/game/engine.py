"""Engine: orchestrates LLM calls for world generation and turn progression.

Design choices:
- Talks to kiro.rs (``localhost:8990``) via Anthropic Messages API by default.
- Can route text calls to an OpenAI-compatible provider for narrative models
  such as DeepSeek by setting GAME_MODEL_PROVIDER=openai.
- Sonnet for world generation (needs cohesion), Haiku for each turn (speed + cost)
  unless overridden by GAME_TEXT_MODEL / GAME_WORLD_MODEL / GAME_TURN_MODEL.
- Image generation via SoruxGPT Responses API (optional, skipped if key not set).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx

from . import db as game_db
from .parser import OpeningScene, ParseError, TurnResult, WorldBible, parse_turn, parse_world_and_opening
from .prompts import (
    TURN_SYSTEM,
    GenreProfile,
    get_genre,
    pick_random_genre,
    turn_user_prompt,
    world_bible_system,
    world_bible_user,
)

logger = logging.getLogger(__name__)

# ── Anthropic gateway config ──────────────────────────────────────────────────

KIRO_BASE_URL = (
    os.environ.get("ANTHROPIC_BASE_URL")
    or os.environ.get("KIRO_PROXY_TARGET")
    or "http://127.0.0.1:8990"
).rstrip("/")
KIRO_API_KEY = (
    os.environ.get("ANTHROPIC_AUTH_TOKEN")
    or os.environ.get("KIRO_UPSTREAM_API_KEY")
    or os.environ.get("KIRO_API_KEY")
    or ""
).strip()

# Model selection. GAME_TEXT_MODEL is a convenient one-knob override for the
# main narrative model; specific env vars still win.
TEXT_MODEL = os.environ.get("GAME_TEXT_MODEL", "").strip()
WORLD_MODEL = os.environ.get("GAME_WORLD_MODEL", TEXT_MODEL or "claude-sonnet-4.6")
TURN_MODEL = os.environ.get("GAME_TURN_MODEL", TEXT_MODEL or "claude-haiku-4.5")
STRONG_TURN_MODEL = os.environ.get("GAME_STRONG_TURN_MODEL", WORLD_MODEL)
SUMMARY_MODEL = os.environ.get("GAME_SUMMARY_MODEL", TURN_MODEL)
GAME_MAX_TURNS = int(os.environ.get("GAME_MAX_TURNS", "26"))

# Optional OpenAI-compatible route for models that are not served by kiro.rs.
# Example:
#   GAME_MODEL_PROVIDER=openai
#   GAME_OPENAI_BASE_URL=https://...
#   GAME_OPENAI_API_KEY=...
#   GAME_TEXT_MODEL=DeepSeek-V4-Flash
GAME_MODEL_PROVIDER = os.environ.get("GAME_MODEL_PROVIDER", "anthropic").strip().lower()
GAME_OPENAI_BASE_URL = os.environ.get("GAME_OPENAI_BASE_URL", "").strip().rstrip("/")
GAME_OPENAI_API_KEY = os.environ.get("GAME_OPENAI_API_KEY", "").strip()

# ── SoruxGPT image gen (optional) ─────────────────────────────────────────────

SORUXGPT_BASE_URL = "https://app.soruxgpt.com/api/codex/v1"
SORUXGPT_API_KEY = (os.environ.get("SORUXGPT_API_KEY") or "").strip()

STATIC_DIR = Path(__file__).parent.parent.parent / "web" / "static"
GAME_IMAGE_DIR = STATIC_DIR / "game_images"
GAME_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
GAME_IMAGE_URL_PREFIX = "/static/game_images"

# httpx clients
_kiro_client = httpx.AsyncClient(base_url=KIRO_BASE_URL, timeout=300.0)
_openai_client: httpx.AsyncClient | None = None
_soruxgpt_client: httpx.AsyncClient | None = None


def _get_openai_client() -> httpx.AsyncClient | None:
    global _openai_client
    if not GAME_OPENAI_BASE_URL or not GAME_OPENAI_API_KEY:
        return None
    if _openai_client is None:
        _openai_client = httpx.AsyncClient(base_url=GAME_OPENAI_BASE_URL, timeout=300.0)
    return _openai_client


def _get_soruxgpt_client() -> httpx.AsyncClient | None:
    global _soruxgpt_client
    if not SORUXGPT_API_KEY:
        return None
    if _soruxgpt_client is None:
        _soruxgpt_client = httpx.AsyncClient(base_url=SORUXGPT_BASE_URL, timeout=None, proxy=None)
    return _soruxgpt_client


# ── Text model calls ─────────────────────────────────────────────────────────


def _provider_for_model(model: str) -> str:
    provider = GAME_MODEL_PROVIDER or "anthropic"
    if provider == "auto":
        if "deepseek" in (model or "").lower() and GAME_OPENAI_BASE_URL and GAME_OPENAI_API_KEY:
            return "openai"
        return "anthropic"
    return provider


def _turn_model_for(turn_idx: int | None) -> str:
    """Use the stronger model on drama-heavy turns if configured."""
    if not STRONG_TURN_MODEL or STRONG_TURN_MODEL == TURN_MODEL or turn_idx is None:
        return TURN_MODEL
    t = int(turn_idx)
    if t == 1 or 8 <= t <= 12 or t >= max(20, GAME_MAX_TURNS - 6):
        return STRONG_TURN_MODEL
    return TURN_MODEL


# ── Anthropic Messages call (via kiro.rs) ─────────────────────────────────────


async def call_claude(
    *, system: str, user: str, model: str, max_tokens: int = 4096
) -> tuple[str, dict[str, int]]:
    """Returns (assistant_text, usage_dict). Non-streaming, for world-gen + final parse."""
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": KIRO_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    resp = await _kiro_client.post("/v1/messages", json=payload, headers=headers)
    if resp.status_code >= 400:
        snippet = (await resp.aread())[:500]
        raise RuntimeError(f"kiro.rs call failed status={resp.status_code} body={snippet!r}")
    body = resp.json()
    content_blocks = body.get("content") or []
    text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
    usage = body.get("usage") or {}
    usage_dict = {
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
    }
    if not text.strip():
        raise RuntimeError("claude call returned empty content; likely upstream moderation or transient failure")
    return text, usage_dict


async def call_openai_chat(
    *, system: str, user: str, model: str, max_tokens: int = 4096
) -> tuple[str, dict[str, int]]:
    """OpenAI-compatible non-streaming text call."""
    client = _get_openai_client()
    if client is None:
        raise RuntimeError("OpenAI-compatible game model is not configured")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Authorization": f"Bearer {GAME_OPENAI_API_KEY}", "Content-Type": "application/json"}
    resp = await client.post("/chat/completions", json=payload, headers=headers)
    if resp.status_code >= 400:
        snippet = (await resp.aread())[:500]
        raise RuntimeError(f"openai-compatible call failed status={resp.status_code} body={snippet!r}")
    body = resp.json()
    choices = body.get("choices") or []
    text = ""
    if choices:
        msg = choices[0].get("message") or {}
        text = msg.get("content") or ""
    usage = body.get("usage") or {}
    usage_dict = {
        "input_tokens": int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
        "output_tokens": int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
    }
    if not text.strip():
        raise RuntimeError("openai-compatible call returned empty content")
    return text, usage_dict


async def call_text_model(
    *, system: str, user: str, model: str, max_tokens: int = 4096
) -> tuple[str, dict[str, int]]:
    """Dispatch a text call to the configured provider."""
    if _provider_for_model(model) == "openai":
        return await call_openai_chat(system=system, user=user, model=model, max_tokens=max_tokens)
    return await call_claude(system=system, user=user, model=model, max_tokens=max_tokens)


# ── Image gen (tag-hash cache, via SoruxGPT — optional) ───────────────────────


def _tag_hash(visual_tag: str, art_style: str) -> str:
    payload = json.dumps({"tag": visual_tag.strip(), "style": art_style.strip()}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def generate_pixel_image(visual_tag: str, art_style: str, *, kind: str = "scene") -> tuple[str, float, bool]:
    """Return (url, cost_usd, cache_hit). Uses SoruxGPT image generation."""
    tag_hash = _tag_hash(visual_tag, art_style)
    cached = await game_db.get_cached_image(tag_hash)
    if cached:
        with open("/tmp/game_image_gen.log", "a") as logf:
            logf.write(f"{time.strftime('%H:%M:%S')} cache_hit kind={kind} url={cached}\n")
        return cached, 0.0, True

    client = _get_soruxgpt_client()
    if client is None:
        with open("/tmp/game_image_gen.log", "a") as logf:
            logf.write(f"{time.strftime('%H:%M:%S')} NO_CLIENT kind={kind} api_key_set={bool(SORUXGPT_API_KEY)}\n")
        return "", 0.0, False

    prompt_parts = ["pixel art", "16-bit style", "crisp pixel edges", "no text", "no watermark"]
    if art_style:
        prompt_parts.append(art_style)
    if visual_tag:
        prompt_parts.append(visual_tag)
    prompt = ", ".join(prompt_parts)

    headers = {"Authorization": f"Bearer {SORUXGPT_API_KEY}", "Content-Type": "application/json"}

    def _log(message: str) -> None:
        with open("/tmp/game_image_gen.log", "a") as logf:
            logf.write(f"{time.strftime('%H:%M:%S')} {message}\n")

    def _collect_b64_values(obj: Any, found: list[str]) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in {"b64_json", "image_b64", "partial_image_b64"} and isinstance(value, str) and value:
                    found.append(value)
                else:
                    _collect_b64_values(value, found)
        elif isinstance(obj, list):
            for item in obj:
                _collect_b64_values(item, found)

    async def _save_image_bytes(image_bytes: bytes) -> str:
        fname = f"{kind}_{tag_hash[:16]}_{int(time.time())}.png"
        fpath = GAME_IMAGE_DIR / fname
        await asyncio.to_thread(fpath.write_bytes, image_bytes)
        url = f"{GAME_IMAGE_URL_PREFIX}/{fname}"
        await game_db.cache_image(tag_hash, url, 0.04)
        return url

    async def _try_responses_stream() -> tuple[str, str]:
        payload = {
            "model": "gpt-5.4-mini",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            "tools": [
                {
                    "type": "image_generation",
                    "model": "gpt-image-2",
                    "size": "1024x1024",
                    "quality": "auto",
                    "output_format": "png",
                    "moderation": "auto",
                }
            ],
            "tool_choice": "auto",
            "store": False,
            "stream": True,
        }
        last_err = ""
        for attempt in range(2):
            latest_b64 = ""
            completed_b64s: list[str] = []
            _log(f"STREAM_START kind={kind} hash={tag_hash[:16]} attempt={attempt + 1}")
            try:
                async with client.stream("POST", "/responses", headers=headers, json=payload, timeout=None) as resp:
                    _log(f"STREAM_STATUS kind={kind} status={resp.status_code} attempt={attempt + 1}")
                    if resp.status_code >= 400:
                        body = (await resp.aread())[:500]
                        last_err = f"stream HTTP {resp.status_code}: {body!r}"
                        if resp.status_code in {408, 502, 503, 504} and attempt < 1:
                            await asyncio.sleep(2.0)
                            continue
                        return "", last_err

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            event = json.loads(raw)
                        except Exception:
                            continue
                        event_type = event.get("type", "")
                        if event_type == "response.image_generation_call.partial_image":
                            b64 = event.get("partial_image_b64")
                            if b64:
                                latest_b64 = b64
                        elif event_type == "response.completed":
                            _collect_b64_values(event.get("response", {}), completed_b64s)
                        elif event_type in {"response.failed", "response.incomplete"}:
                            last_err = event_type

                    b64 = completed_b64s[-1] if completed_b64s else latest_b64
                    if b64:
                        url = await _save_image_bytes(base64.b64decode(b64))
                        _log(f"STREAM_SUCCESS kind={kind} url={url}")
                        return url, ""
                    last_err = last_err or "stream returned no image"
            except Exception as exc:
                last_err = f"stream exception: {exc!r}"
                _log(f"STREAM_EXCEPTION kind={kind} attempt={attempt + 1}: {exc!r}")
            if attempt < 1:
                await asyncio.sleep(2.0)
        return "", last_err

    async def _try_images_generation(response_format: str) -> tuple[str, str]:
        max_attempts = 2 if response_format == "url" else 1
        last_err = ""
        for attempt in range(max_attempts):
            _log(f"START kind={kind} hash={tag_hash[:16]} fmt={response_format} attempt={attempt + 1}")
            try:
                resp = await client.post(
                    "/images/generations",
                    headers=headers,
                    json={
                        "model": "gpt-image-2",
                        "prompt": prompt,
                        "n": 1,
                        "size": "1024x1024",
                        "response_format": response_format,
                    },
                    timeout=300.0,
                )
                _log(f"STATUS kind={kind} fmt={response_format} status={resp.status_code} attempt={attempt + 1}")
                if resp.status_code >= 400:
                    last_err = resp.text[:500] or f"HTTP {resp.status_code}"
                    if resp.status_code in {408, 502, 503, 504} and attempt < max_attempts - 1:
                        await asyncio.sleep(2.0)
                        continue
                    return "", last_err

                data = resp.json()
                images = data.get("data", [])
                if not images:
                    return "", "no image data"

                b64 = images[0].get("b64_json", "")
                url = images[0].get("url", "")
                if b64:
                    image_bytes = base64.b64decode(b64)
                elif url:
                    dl_resp = await client.get(url)
                    if dl_resp.status_code >= 400:
                        last_err = f"url download HTTP {dl_resp.status_code}"
                        continue
                    image_bytes = dl_resp.content
                else:
                    return "", "no b64_json or url in image data"

                saved_url = await _save_image_bytes(image_bytes)
                _log(f"SUCCESS kind={kind} fmt={response_format} url={saved_url}")
                return saved_url, ""
            except Exception as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                _log(f"EXCEPTION kind={kind} fmt={response_format} attempt={attempt + 1}: {exc!r}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2.0)
        return "", last_err

    url, err = await _try_responses_stream()
    if not url:
        _log(f"STREAM_FAILED kind={kind} hash={tag_hash[:16]} err={err}")
        url, err = await _try_images_generation("url")
    if not url:
        _log(f"URL_FAILED kind={kind} hash={tag_hash[:16]} err={err}")
        url, err = await _try_images_generation("b64_json")
    if not url:
        _log(f"FAILED kind={kind} hash={tag_hash[:16]} err={err}")
        return "", 0.0, False

    return url, 0.04, False


# ── High-level orchestration ─────────────────────────────────────────────────


async def generate_world(
    *,
    genre: str | None = None,
    avoid_recent: list[str] | tuple[str, ...] | None = None,
    max_retries: int = 2,
) -> tuple[WorldBible, OpeningScene, dict[str, int], GenreProfile]:
    profile = get_genre(genre) if genre else pick_random_genre(avoid_recent=avoid_recent)
    system_prompt = world_bible_system(profile)
    user_prompt = world_bible_user(profile)

    last_err: Exception | None = None
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    for attempt in range(max_retries + 1):
        try:
            text, usage = await call_text_model(
                system=system_prompt, user=user_prompt, model=WORLD_MODEL, max_tokens=6000,
            )
        except RuntimeError as exc:
            last_err = exc
            logger.warning("world gen upstream failed (attempt %d): %s", attempt, exc)
            continue
        total_usage["input_tokens"] += usage["input_tokens"]
        total_usage["output_tokens"] += usage["output_tokens"]
        try:
            wb, scene = parse_world_and_opening(text)
            return wb, scene, total_usage, profile
        except ParseError as exc:
            last_err = exc
            logger.warning("world gen parse failed genre=%s (attempt %d): %s", profile.slug, attempt, exc)
            continue
    raise RuntimeError(f"world gen failed after {max_retries + 1} attempts (genre={profile.slug}): {last_err}")


async def generate_turn(
    *,
    world_bible: dict[str, Any],
    current_state: dict[str, Any],
    recent_summary: str,
    player_action: str,
    turn_idx: int | None = None,
    max_retries: int = 2,
) -> tuple[TurnResult, dict[str, int]]:
    wb_xml = json.dumps(world_bible, ensure_ascii=False, sort_keys=True)
    state_json = json.dumps(current_state, ensure_ascii=False, sort_keys=True)
    user = turn_user_prompt(
        wb_xml,
        state_json,
        recent_summary,
        player_action,
        turn_idx=turn_idx,
        max_turns=GAME_MAX_TURNS,
    )

    last_err: Exception | None = None
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    model = _turn_model_for(turn_idx)
    for attempt in range(max_retries + 1):
        try:
            text, usage = await call_text_model(
                system=TURN_SYSTEM, user=user, model=model, max_tokens=2400,
            )
        except RuntimeError as exc:
            last_err = exc
            logger.warning("turn upstream failed (attempt %d): %s", attempt, exc)
            continue
        total_usage["input_tokens"] += usage["input_tokens"]
        total_usage["output_tokens"] += usage["output_tokens"]
        try:
            return parse_turn(text), total_usage
        except ParseError as exc:
            last_err = exc
            logger.warning("turn parse failed (attempt %d): %s", attempt, exc)
            continue
    raise RuntimeError(f"turn gen failed after {max_retries + 1} attempts: {last_err}")


# ── State helpers ────────────────────────────────────────────────────────────


def apply_state_delta(state: dict[str, Any], delta: list[dict[str, str]]) -> dict[str, Any]:
    new_state = dict(state)
    for change in delta:
        key = change.get("key")
        op = (change.get("op") or "set").lower()
        val = change.get("value")
        if not key:
            continue
        if op == "set":
            new_state[key] = val
        elif op == "add":
            current = new_state.get(key)
            if not isinstance(current, list):
                current = [] if current is None else [current]
            if val not in current:
                current = [*current, val]
            new_state[key] = current
        elif op == "remove":
            current = new_state.get(key)
            if isinstance(current, list) and val in current:
                new_state[key] = [x for x in current if x != val]
    return new_state


def apply_codex_delta(codex: dict[str, Any], delta: list[dict[str, str]], *, turn_idx: int) -> dict[str, Any]:
    type_to_bucket = {"relation": "relations", "keynote": "keynotes", "secret": "secrets"}
    new_codex = {
        "relations": dict(codex.get("relations") or {}),
        "keynotes": dict(codex.get("keynotes") or {}),
        "secrets": dict(codex.get("secrets") or {}),
    }
    for entry in delta:
        bucket = type_to_bucket.get((entry.get("type") or "keynote").lower())
        if not bucket:
            continue
        key = (entry.get("key") or "").strip()
        if not key:
            continue
        op = (entry.get("op") or "set").lower()
        if op == "remove":
            new_codex[bucket].pop(key, None)
            continue
        value = (entry.get("value") or "").strip()
        if not value:
            continue
        new_codex[bucket][key] = {"note": value, "turn": int(turn_idx)}
    return new_codex


# ── Scoring ──────────────────────────────────────────────────────────────────

_ENDING_KEYWORDS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("hidden", "secret", "mystery"), 80),
    (("ascend", "triumph", "perfect", "win", "good", "rise"), 50),
    (("bad", "doom", "fall", "death", "fail", "corrupt", "demon"), 10),
)


def compute_score(turn_idx: int, ending_slug: str | None) -> int:
    bonus = 25
    slug = (ending_slug or "").lower()
    for keys, value in _ENDING_KEYWORDS:
        if any(k in slug for k in keys):
            bonus = value
            break
    return max(1, int(turn_idx)) * 10 + bonus


# ── Streaming (via kiro.rs Anthropic SSE) ─────────────────────────────────────


async def call_claude_stream(
    *, system: str, user: str, model: str, max_tokens: int = 2400
) -> AsyncGenerator[dict[str, Any], None]:
    """Async generator over kiro.rs Anthropic SSE stream.

    Yields:
      - ``{"type": "text", "text": "..."}`` for each content_block_delta
      - ``{"type": "usage", "usage": {...}}`` at end
    """
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "stream": True,
    }
    headers = {
        "x-api-key": KIRO_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }

    input_tokens = 0
    output_tokens = 0
    async with _kiro_client.stream(
        "POST", "/v1/messages", headers=headers, content=json.dumps(payload).encode("utf-8")
    ) as resp:
        if resp.status_code >= 400:
            snippet = (await resp.aread())[:500]
            raise RuntimeError(f"kiro.rs stream failed status={resp.status_code} body={snippet!r}")
        async for line in resp.aiter_lines():
            if not line:
                continue
            # Anthropic SSE: "event: <name>" then "data: <json>"
            if line.startswith("data: "):
                data = line[6:]
                try:
                    event = json.loads(data)
                except Exception:
                    continue
                et = event.get("type", "")
                if et == "content_block_delta":
                    delta = event.get("delta") or {}
                    text = delta.get("text", "")
                    if text:
                        yield {"type": "text", "text": text}
                elif et == "message_start":
                    msg = event.get("message") or {}
                    usage = msg.get("usage") or {}
                    if usage.get("input_tokens"):
                        input_tokens = int(usage["input_tokens"])
                elif et == "message_delta":
                    usage = event.get("usage") or {}
                    if usage.get("output_tokens"):
                        output_tokens = int(usage["output_tokens"])
                elif et == "message_stop":
                    pass

    yield {
        "type": "usage",
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


async def call_openai_chat_stream(
    *, system: str, user: str, model: str, max_tokens: int = 2400
) -> AsyncGenerator[dict[str, Any], None]:
    """OpenAI-compatible SSE stream, normalized to the same events as Claude."""
    client = _get_openai_client()
    if client is None:
        raise RuntimeError("OpenAI-compatible game model is not configured")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    headers = {"Authorization": f"Bearer {GAME_OPENAI_API_KEY}", "Content-Type": "application/json"}
    usage_dict = {"input_tokens": 0, "output_tokens": 0}
    async with client.stream(
        "POST", "/chat/completions", headers=headers, content=json.dumps(payload).encode("utf-8")
    ) as resp:
        if resp.status_code >= 400:
            snippet = (await resp.aread())[:500]
            raise RuntimeError(f"openai-compatible stream failed status={resp.status_code} body={snippet!r}")
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except Exception:
                continue
            usage = event.get("usage") or {}
            if usage:
                usage_dict = {
                    "input_tokens": int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
                    "output_tokens": int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
                }
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            text = delta.get("content") or ""
            if text:
                yield {"type": "text", "text": text}
    yield {"type": "usage", "usage": usage_dict}


async def call_text_model_stream(
    *, system: str, user: str, model: str, max_tokens: int = 2400
) -> AsyncGenerator[dict[str, Any], None]:
    """Dispatch a streaming text call to the configured provider."""
    if _provider_for_model(model) == "openai":
        async for event in call_openai_chat_stream(
            system=system, user=user, model=model, max_tokens=max_tokens
        ):
            yield event
        return
    async for event in call_claude_stream(system=system, user=user, model=model, max_tokens=max_tokens):
        yield event


class _NarrativeExtractor:
    """Streaming extractor for the ``<narrative>…</narrative>`` section."""

    _OPEN = "<narrative>"
    _CLOSE = "</narrative>"
    _TAIL_HOLD = len("</narrative>") - 1

    def __init__(self) -> None:
        self.raw = ""
        self.pending = ""
        self.state = "before"

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self.raw += text
        if self.state == "before":
            idx = self.raw.find(self._OPEN)
            if idx < 0:
                return ""
            self.pending = self.raw[idx + len(self._OPEN):]
            self.state = "inside"
        elif self.state == "inside":
            self.pending += text
        if self.state != "inside":
            return ""
        close_idx = self.pending.find(self._CLOSE)
        if close_idx >= 0:
            out = self.pending[:close_idx]
            self.pending = ""
            self.state = "after"
            return out
        safe_len = max(0, len(self.pending) - self._TAIL_HOLD)
        if safe_len > 0:
            out = self.pending[:safe_len]
            self.pending = self.pending[safe_len:]
            return out
        return ""

    def flush_pending(self) -> str:
        if self.state == "inside" and self.pending:
            out = self.pending
            self.pending = ""
            return out
        return ""

    def feed_chunk(self, text: str) -> str:
        if text:
            self.raw += text
        return ""


class _HtmlStripper:
    """Remove stray HTML/XML tags and markdown markers from narrative."""

    _TAG_RE = re.compile(r"<[^<>]{0,40}>")
    _MD_MARKERS = ("**", "__")
    _MAX_PENDING = 48

    def __init__(self) -> None:
        self.pending = ""

    def feed(self, text: str) -> str:
        if not text:
            return ""
        buf = self.pending + text
        lt = buf.rfind("<")
        gt = buf.rfind(">")
        if lt > gt and (len(buf) - lt) < self._MAX_PENDING:
            ready = buf[:lt]
            self.pending = buf[lt:]
        else:
            ready = buf
            self.pending = ""
        ready = self._TAG_RE.sub("", ready)
        for m in self._MD_MARKERS:
            ready = ready.replace(m, "")
        return ready

    def flush(self) -> str:
        if not self.pending:
            return ""
        out = self._TAG_RE.sub("", self.pending)
        for m in self._MD_MARKERS:
            out = out.replace(m, "")
        self.pending = ""
        return out


class _VisualTagExtractor:
    """Scan the raw stream for a complete ``<visual_tag>…</visual_tag>`` block."""

    _OPEN = "<visual_tag>"
    _CLOSE = "</visual_tag>"

    def __init__(self) -> None:
        self._buf = ""
        self._fired = False

    def feed(self, text: str) -> str | None:
        if self._fired or not text:
            return None
        self._buf += text
        start = self._buf.find(self._OPEN)
        if start < 0:
            if len(self._buf) > 4096:
                self._buf = self._buf[-len(self._OPEN):]
            return None
        end = self._buf.find(self._CLOSE, start + len(self._OPEN))
        if end < 0:
            return None
        inner = self._buf[start + len(self._OPEN):end].strip()
        self._fired = True
        self._buf = ""
        return inner or None


async def generate_turn_stream(
    *,
    world_bible: dict[str, Any],
    current_state: dict[str, Any],
    recent_summary: str,
    player_action: str,
    turn_idx: int | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Async generator for a single turn, streaming narrative + final result.

    Yields:
      - ``{"type": "narrative", "text": "<chunk>"}``
      - ``{"type": "visual_tag", "tag": "..."}``
      - ``{"type": "final", "result": TurnResult, "usage": {...}}``
    """
    wb_xml = json.dumps(world_bible, ensure_ascii=False, sort_keys=True)
    state_json = json.dumps(current_state, ensure_ascii=False, sort_keys=True)
    user = turn_user_prompt(
        wb_xml,
        state_json,
        recent_summary,
        player_action,
        turn_idx=turn_idx,
        max_turns=GAME_MAX_TURNS,
    )

    extractor = _NarrativeExtractor()
    stripper = _HtmlStripper()
    visual_tag_extractor = _VisualTagExtractor()
    usage = {"input_tokens": 0, "output_tokens": 0}
    model = _turn_model_for(turn_idx)
    async for event in call_text_model_stream(
        system=TURN_SYSTEM, user=user, model=model, max_tokens=2400
    ):
        et = event.get("type")
        if et == "text":
            text = event.get("text", "")
            tag = visual_tag_extractor.feed(text)
            if tag:
                yield {"type": "visual_tag", "tag": tag}
            if extractor.state == "after":
                extractor.feed_chunk(text)
                continue
            emitted = extractor.feed(text)
            if emitted:
                cleaned = stripper.feed(emitted)
                if cleaned:
                    yield {"type": "narrative", "text": cleaned}
        elif et == "usage":
            usage = event.get("usage") or usage

    tail = extractor.flush_pending()
    if tail:
        cleaned = stripper.feed(tail)
        if cleaned:
            yield {"type": "narrative", "text": cleaned}
    residual = stripper.flush()
    if residual:
        yield {"type": "narrative", "text": residual}

    result = parse_turn(extractor.raw)
    yield {"type": "final", "result": result, "usage": usage}
