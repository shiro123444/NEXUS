#!/usr/bin/env python3
"""
Billing Gateway for CLIProxyAPI
- Intercepts all /v1/* requests
- Counts tokens and converts to USD
- Supports per-model pricing, per-API-key quotas
- Admin endpoints for price configuration and billing reports
"""

import os
import sys
import json
import time
import math
import yaml
import asyncio
import httpx
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from collections import defaultdict
from fastapi import FastAPI, Request, Response, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ─── Configuration ──────────────────────────────────────────────────────────
BASE_DIR = Path("/opt/billing-gateway")
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CLIPROXY_URL = "http://127.0.0.1:8317"
MIMO_UPSTREAM_URL = os.environ.get("MIMO_UPSTREAM_URL", "https://fufu.iqach.top/v1")
MIMO_UPSTREAM_PROXY = os.environ.get("MIMO_UPSTREAM_PROXY", "http://127.0.0.1:7890")
ARK_PROVIDER_NAME = os.environ.get("ARK_PROVIDER_NAME", "Ark")
ADMIN_KEYS = {"admin_fyz040913"}  # admin-only endpoints

# ─── Model Pricing (USD per 1M tokens) ──────────────────────────────────────
# Prices are configurable via admin API; these are defaults.
DEFAULT_PRICES = {
    # ── OpenAI / Codex ──────────────────────────────────
    "gpt-5.2":              {"input": 1.50,  "output": 6.00},
    "gpt-5.3":              {"input": 1.50,  "output": 6.00},
    "gpt-5.3-codex":        {"input": 1.50,  "output": 6.00},
    "gpt-5.3-codex-spark":  {"input": 1.50,  "output": 6.00},
    "gpt-5.4":              {"input": 2.50,  "output": 10.00},
    "gpt-5.4-mini":         {"input": 0.15,  "output": 0.60},
    "gpt-5.5":              {"input": 5.00,  "output": 15.00},
    "gpt-image-2":          {"input": 0.50,  "output": 2.00},
    "codex-auto-review":    {"input": 1.50,  "output": 6.00},
    "gpt-4o":               {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":          {"input": 0.15,  "output": 0.60},
    "gpt-4-turbo":          {"input": 10.00, "output": 30.00},
    "gpt-4":                {"input": 30.00, "output": 60.00},
    "o1-preview":           {"input": 15.00, "output": 60.00},
    "o1-mini":              {"input": 3.00,  "output": 12.00},
    "o3-mini":              {"input": 1.10,  "output": 4.40},
    "text-embedding-3-large":  {"input": 0.13, "output": 0.0},
    "text-embedding-3-small":  {"input": 0.02, "output": 0.0},
    "dall-e-3":             {"input": 0.0,   "output": 4.00},
    "whisper-1":            {"input": 0.006, "output": 0.0},   # per minute
    "tts-1":                {"input": 0.0,   "output": 15.00},
    "tts-1-hd":             {"input": 0.0,   "output": 30.00},

    # ── Anthropic / Claude ──────────────────────────────
    "claude-sonnet-4.6":    {"input": 3.00,  "output": 15.00},
    "claude-sonnet-4.5":    {"input": 3.00,  "output": 15.00},
    "claude-sonnet-4":      {"input": 3.00,  "output": 15.00},
    "claude-haiku-4.5":     {"input": 1.00,  "output": 5.00, "cache_read": 0.10},
    "claude-opus-4.5":      {"input": 15.00, "output": 75.00},
    "claude-opus-4.6":      {"input": 15.00, "output": 75.00},
    "claude-opus-4.7":      {"input": 15.00, "output": 75.00},
    "claude-3-7-sonnet":    {"input": 3.00,  "output": 15.00},
    "claude-3-5-sonnet":    {"input": 3.00,  "output": 15.00},
    "claude-3-5-haiku":     {"input": 0.80,  "output": 4.00},
    "claude-3-haiku":       {"input": 0.25,  "output": 1.25},
    "claude-3-opus":        {"input": 15.00, "output": 75.00},
    "claude-4-sonnet":      {"input": 3.00,  "output": 15.00},
    "claude-4-opus":        {"input": 15.00, "output": 75.00},

    # ── Google / Gemini ─────────────────────────────────
    "gemini-2.5-pro":       {"input": 1.25,  "output": 10.00},
    "gemini-2.5-flash":     {"input": 0.15,  "output": 0.60},
    "gemini-2.0-pro":       {"input": 1.25,  "output": 10.00},
    "gemini-2.0-flash":     {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro":       {"input": 1.25,  "output": 5.00},
    "gemini-1.5-flash":     {"input": 0.075, "output": 0.30},
    "gemini-1.0-pro":       {"input": 0.50,  "output": 1.50},
    "gemini-embedding":     {"input": 0.002, "output": 0.0},

    # ── Kimi / Moonshot ─────────────────────────────────
    "kimi-k2.6":            {"input": 0.95186, "output": 3.95001, "cache_read": 0.16095},
    "kimi-k2-128k":         {"input": 0.60,  "output": 0.60},
    "kimi-k2-200k":         {"input": 1.20,  "output": 1.20},
    "kimi-k1.5":            {"input": 0.30,  "output": 1.20},
    "kimi-moonshot-128k":   {"input": 0.60,  "output": 0.60},
    "kimi-moonshot-8k":     {"input": 0.012, "output": 0.012},
    "kimi-turbo":           {"input": 0.10,  "output": 0.50},
    "kimi-turbo-32k":       {"input": 0.20,  "output": 1.00},

    # ── MIMO ────────────────────────────────────────────
    "mimo-v2.5-pro":               {"input": 1.00,  "output": 3.00},
    "mimo-v2.5":                   {"input": 1.00,  "output": 3.00},
    "mimo-v2.5-tts":               {"input": 1.00,  "output": 3.00},
    "mimo-v2.5-tts-voicedesign":   {"input": 1.00,  "output": 3.00},
    "mimo-v2.5-tts-voiceclone":    {"input": 1.00,  "output": 3.00},
    "mimo-v2-pro":                 {"input": 1.00,  "output": 3.00},
    "mimo-v2-flash":               {"input": 1.00,  "output": 3.00},
    "mimo-v2-omni":                {"input": 1.00,  "output": 3.00},
    "mimo-v2-tts":                 {"input": 1.00,  "output": 3.00},

    # ── DeepSeek ────────────────────────────────────────
    "deepseek-chat":        {"input": 0.14,  "output": 0.28},
    "deepseek-reasoner":    {"input": 0.55,  "output": 2.19},
    "deepseek-coder":       {"input": 0.14,  "output": 0.28},
    "deepseek-v3":          {"input": 0.27,  "output": 1.10},

    # ── Qwen / Alibaba ──────────────────────────────────
    "qwen2.5-72b":          {"input": 0.50,  "output": 0.50},
    "qwen2.5-14b":          {"input": 0.10,  "output": 0.10},
    "qwen2.5-7b":           {"input": 0.05,  "output": 0.05},
    "qwen-turbo":           {"input": 0.50,  "output": 2.00},
    "qwen-plus":            {"input": 0.40,  "output": 1.20},
    "qwen-max":             {"input": 2.40,  "output": 9.60},

    # ── Llama / Meta ────────────────────────────────────
    "llama-3.1-405b":       {"input": 1.60,  "output": 1.60},
    "llama-3.1-70b":        {"input": 0.52,  "output": 0.52},
    "llama-3.1-8b":         {"input": 0.05,  "output": 0.05},
    "llama-3-70b":          {"input": 0.59,  "output": 0.79},
    "llama-3-8b":           {"input": 0.05,  "output": 0.08},

    # ── Mistral ─────────────────────────────────────────
    "mistral-large":        {"input": 2.00,  "output": 6.00},
    "mistral-medium":       {"input": 2.70,  "output": 8.10},
    "mistral-small":        {"input": 0.20,  "output": 0.60},
    "mistral-tiny":         {"input": 0.14,  "output": 0.41},

    # ── Other / Fallback ────────────────────────────────
    "default":              {"input": 1.00,  "output": 3.00},
}

PRICE_FILE = DATA_DIR / "model_prices.json"
BILL_FILE  = DATA_DIR / "billing_records.jsonl"
KEY_BALANCE_FILE = DATA_DIR / "key_balances.json"
KEY_QUOTA_FILE   = DATA_DIR / "key_quotas.json"

# ─── State ─────────────────────────────────────────────────────────────────
_prices = {}
_balances = {}      # api_key -> {"usd": float, " updated_at": str}
_quotas   = {}      # api_key -> {"daily_usd": float, "monthly_usd": float}
_lock = asyncio.Lock()

# ─── Persistence helpers ───────────────────────────────────────────────────
def _load_json(path: Path, default):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default

def _save_json(path: Path, data):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

def init_data():
    global _prices, _balances, _quotas
    _prices = _load_json(PRICE_FILE, dict(DEFAULT_PRICES))
    _balances = _load_json(KEY_BALANCE_FILE, {})
    _quotas   = _load_json(KEY_QUOTA_FILE, {})

def get_price(model: str):
    """Return price for model, falling back to regex prefix match then default."""
    if model in _prices:
        return _prices[model]
    # prefix match  (e.g. gpt-5.3-codex-spark → gpt-5.3-codex)
    parts = model.split("-")
    for i in range(len(parts), 0, -1):
        prefix = "-".join(parts[:i])
        if prefix in _prices:
            return _prices[prefix]
    return _prices.get("default", {"input": 1.0, "output": 3.0})

# ─── Token estimation (TikToken-style fallback) ────────────────────────────
def estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars per token for CJK, ~4 chars per token for EN."""
    if not text:
        return 0
    # Mix of heuristics
    total_chars = len(text)
    # roughly 1 token ≈ 4 chars for English, 1 token ≈ 1 char for CJK
    return max(1, total_chars // 4 + total_chars % 4 // 2)

def _flatten_text(value) -> str:
    """Flatten nested OpenAI-compatible content blocks into plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            parts.append(_flatten_text(item))
        return "".join(parts)
    if isinstance(value, dict):
        parts = []
        for key in ("text", "content", "reasoning_content", "input_text", "output_text", "transcript"):
            if value.get(key):
                parts.append(_flatten_text(value.get(key)))
        return "".join(parts)
    return str(value)

def _extract_request_input_text(req_json: dict) -> str:
    """Collect user input text from OpenAI-compatible request payloads."""
    parts = []
    for msg in req_json.get("messages", []) or []:
        parts.append(_flatten_text(msg.get("content")))

    request_input = req_json.get("input")
    if isinstance(request_input, str):
        parts.append(request_input)
    elif isinstance(request_input, list):
        for item in request_input:
            parts.append(_flatten_text(item))

    prompt = req_json.get("prompt")
    if isinstance(prompt, str):
        parts.append(prompt)
    elif isinstance(prompt, list):
        for item in prompt:
            parts.append(_flatten_text(item))

    return "".join(parts)

def _extract_response_output_text(body: dict) -> str:
    """Collect assistant output text from several upstream response formats."""
    parts = []

    for choice in body.get("choices", []) or []:
        parts.append(_flatten_text(choice.get("text")))
        parts.append(_flatten_text(choice.get("message")))
        parts.append(_flatten_text(choice.get("delta")))

    parts.append(_flatten_text(body.get("output_text")))
    parts.append(_flatten_text(body.get("content")))

    for item in body.get("output", []) or []:
        parts.append(_flatten_text(item))

    if body.get("data") and isinstance(body["data"], list):
        for item in body["data"]:
            if isinstance(item, dict) and "embedding" not in item:
                parts.append(_flatten_text(item))

    return "".join(parts)

def extract_request_tokens(body: dict, req_json: dict | None = None) -> dict:
    """Extract token counts from upstream response body; fallback to estimation."""
    result = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cached_tokens": 0}
    req_json = req_json or {}

    # OpenAI format
    if "usage" in body:
        u = body["usage"]
        result["prompt_tokens"] = u.get("prompt_tokens", 0)
        result["completion_tokens"] = u.get("completion_tokens", 0)
        result["total_tokens"] = u.get("total_tokens", 0)
        result["input_tokens"] = result["prompt_tokens"]
        result["output_tokens"] = result["completion_tokens"]
        # cache discounts
        if "prompt_tokens_details" in u:
            d = u["prompt_tokens_details"]
            result["cached_tokens"] = d.get("cached_tokens", 0)
    # Anthropic format
    elif "input_tokens" in body:
        result["input_tokens"] = body.get("input_tokens", 0)
        result["output_tokens"] = body.get("output_tokens", 0)

    if not result["total_tokens"] and (result["input_tokens"] or result["output_tokens"]):
        result["total_tokens"] = result["input_tokens"] + result["output_tokens"]

    needs_estimate = result["total_tokens"] <= 0 and result["input_tokens"] <= 0 and result["output_tokens"] <= 0
    if needs_estimate:
        input_text = _extract_request_input_text(req_json)
        output_text = _extract_response_output_text(body)
        if input_text:
            result["input_tokens"] = estimate_tokens(input_text)
        if output_text:
            result["output_tokens"] = estimate_tokens(output_text)
        if result["input_tokens"] or result["output_tokens"]:
            result["total_tokens"] = result["input_tokens"] + result["output_tokens"]
            result["_estimated"] = True
    return result

# ─── 促销活动 ────────────────────────────────────────────────────────────
# Opus 系列模型限时 0.4 倍率（2026-05-09 ~ 2026-05-12）
import datetime as _dt

OPUS_PROMO_START = _dt.date(2026, 5, 9)
OPUS_PROMO_END = _dt.date(2026, 5, 12)
OPUS_PROMO_MULTIPLIER = 0.4


def _is_opus_promo() -> bool:
    today = _dt.date.today()
    return OPUS_PROMO_START <= today <= OPUS_PROMO_END


def _get_promo_multiplier(model: str) -> float:
    if _is_opus_promo() and "opus" in model.lower():
        return OPUS_PROMO_MULTIPLIER
    return 1.0


def calculate_cost(model: str, tokens: dict) -> dict:
    """Calculate USD cost from token counts."""
    price = get_price(model)
    promo_mult = _get_promo_multiplier(model)
    input_price = price.get("input", 1.0) * promo_mult    # per 1M tokens
    output_price = price.get("output", 3.0) * promo_mult

    input_tok = tokens.get("input_tokens", 0) or tokens.get("prompt_tokens", 0)
    output_tok = tokens.get("output_tokens", 0) or tokens.get("completion_tokens", 0)

    # Cache discount: cached input is typically 50% of input price
    cached_tok = tokens.get("cached_tokens", 0)
    cache_read_price = price.get("cache_read", input_price * 0.5)
    actual_input_cost = ((input_tok - cached_tok) * input_price + cached_tok * cache_read_price) / 1e6
    output_cost = output_tok * output_price / 1e6

    return {
        "model": model,
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "cached_tokens": cached_tok,
        "input_cost_usd": round(actual_input_cost, 8),
        "output_cost_usd": round(output_cost, 8),
        "total_cost_usd": round(actual_input_cost + output_cost, 8),
        "price_per_1m": price,
        "promo_multiplier": promo_mult if promo_mult != 1.0 else None,
    }

# ─── Billing record ────────────────────────────────────────────────────────
async def record_billing(api_key: str, model: str, cost: dict, meta: dict = None):
    ts = datetime.now(timezone.utc).isoformat()
    record = {
        "timestamp": ts,
        "api_key_hash": "sha256:" + __import__("hashlib").sha256(api_key.encode()).hexdigest()[:16],
        "model": model,
        **cost,
        "meta": meta or {},
    }
    # append to journal
    with open(BILL_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # deduct balance
    async with _lock:
        key_hash = api_key[:16] + "..."
        bal = _balances.get(api_key, {"usd": 0.0, "updated_at": ts})
        bal["usd"] = round(bal.get("usd", 0.0) - cost["total_cost_usd"], 8)
        bal["updated_at"] = ts
        _balances[api_key] = bal
        _save_json(KEY_BALANCE_FILE, _balances)

# ─── FastAPI App ───────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_data()
    yield

app = FastAPI(title="Billing Gateway", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

http_client = httpx.AsyncClient(timeout=600.0)
mimo_http_client = httpx.AsyncClient(timeout=600.0, proxy=MIMO_UPSTREAM_PROXY)

ARK_CHAT_MODELS = {"gpt-5.2", "gpt-5.4", "gpt-5.4-mini"}


def _is_mimo_audio_speech(path: str, req_json: dict) -> bool:
    model = str(req_json.get("model") or "").strip().lower()
    return path == "v1/audio/speech" and model.startswith("mimo-")


def _is_ark_chat_completion(path: str, req_json: dict) -> bool:
    model = str(req_json.get("model") or "").strip()
    return path == "v1/chat/completions" and model in ARK_CHAT_MODELS


def _build_openai_completion_from_sse(model: str, chunks: list[str]) -> tuple[dict, dict]:
    content_parts = []
    usage = {}
    response_id = f"chatcmpl-{int(time.time() * 1000)}"
    created = int(time.time())
    finish_reason = "stop"

    for chunk in chunks:
        for line in chunk.split("\n"):
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                payload = json.loads(data)
            except Exception:
                continue
            response_id = payload.get("id") or response_id
            created = int(payload.get("created") or created)
            if payload.get("usage"):
                usage = payload.get("usage") or usage
            for choice in payload.get("choices", []) or []:
                delta = choice.get("delta") or {}
                text = delta.get("content")
                if text:
                    content_parts.append(text)
                if choice.get("finish_reason"):
                    finish_reason = choice.get("finish_reason")

    content = "".join(content_parts)
    result = {
        "id": response_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": finish_reason,
        }],
        "usage": usage or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
    return result, usage or {}


async def _proxy_ark_chat_completion(request: Request, path: str, body: bytes, req_json: dict, api_key: str):
    model = req_json.get("model", "")
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    upstream_body = dict(req_json)
    upstream_body["stream"] = True
    url = f"{CLIPROXY_URL}/api/provider/{ARK_PROVIDER_NAME}/v1/chat/completions"
    method = request.method

    if req_json.get("stream", False):
        async def sse_stream():
            chunks = []
            async with http_client.stream(method, url, headers=headers, content=json.dumps(upstream_body).encode("utf-8")) as resp:
                async for chunk in resp.aiter_text():
                    chunks.append(chunk)
                    yield chunk.encode("utf-8")

            payload, usage = _build_openai_completion_from_sse(model, chunks)
            tokens = {
                "input_tokens": int(usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
                "cached_tokens": int(((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)) or 0),
            }
            if tokens["total_tokens"] == 0 and (tokens["input_tokens"] or tokens["output_tokens"]):
                tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]
            if tokens["total_tokens"] > 0 or tokens["input_tokens"] > 0 or tokens["output_tokens"] > 0:
                cost = calculate_cost(model, tokens)
                await record_billing(api_key, model, cost, {"path": path, "stream": True, "provider": "ark"})

        return StreamingResponse(sse_stream(), media_type="text/event-stream", status_code=200)

    try:
        resp = await http_client.request(method, url, headers=headers, content=json.dumps(upstream_body).encode("utf-8"), timeout=600.0)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})

    chunks = [resp.text]
    payload, usage = _build_openai_completion_from_sse(model, chunks)
    tokens = {
        "input_tokens": int(usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
        "cached_tokens": int(((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)) or 0),
    }
    if tokens["total_tokens"] == 0 and (tokens["input_tokens"] or tokens["output_tokens"]):
        tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]
    if tokens["total_tokens"] > 0 or tokens["input_tokens"] > 0 or tokens["output_tokens"] > 0:
        cost = calculate_cost(model, tokens)
        await record_billing(api_key, model, cost, {"path": path, "estimated": False, "provider": "ark"})

    return JSONResponse(payload, status_code=resp.status_code)


async def _proxy_mimo_audio_speech(request: Request, path: str, body: bytes, req_json: dict, api_key: str):
    """CLIProxyAPI does not currently expose /v1/audio/speech for openai-compatibility.
    For MIMO TTS, proxy directly to upstream through mihomo.
    """
    model = req_json.get("model", "")
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "authorization", "x-api-key")
    }
    url = f"{MIMO_UPSTREAM_URL}/audio/speech"
    try:
        resp = await mimo_http_client.request(request.method, url, headers=headers, content=body)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})

    if resp.is_success:
        input_tokens = estimate_tokens(_extract_request_input_text(req_json))
        if input_tokens > 0:
            cost = calculate_cost(model, {
                "input_tokens": input_tokens,
                "output_tokens": 0,
                "total_tokens": input_tokens,
            })
            await record_billing(
                api_key,
                model,
                cost,
                {"path": path, "estimated": True, "direct_upstream": "mimo_audio"},
            )

    forward_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in ("transfer-encoding", "connection")
    }
    return Response(content=resp.content, status_code=resp.status_code, headers=forward_headers)

# ─── Public proxy (all /v1/* go through here) ─────────────────────────────

async def _proxy_request(request: Request, path: str):
    """Proxy to CLIProxyAPI 8317 with billing interception."""
    auth = request.headers.get("authorization", "")
    api_key = auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else ""

    body = await request.body()
    req_json = {}
    try:
        req_json = json.loads(body) if body else {}
    except Exception:
        pass

    model = req_json.get("model", "")

    # ── Quota check ────────────────────────────────────────────────────────
    async with _lock:
        bal = _balances.get(api_key, {"usd": 0.0})
        quota = _quotas.get(api_key, {})
        if quota:
            if bal.get("usd", 0) <= 0:
                return JSONResponse(
                    status_code=429,
                    content={"error": {"message": "Quota exceeded. Please top up.", "type": "insufficient_quota"}},
                )

    # ── Prepare upstream request ───────────────────────────────────────────
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    url = f"{CLIPROXY_URL}/{path}"
    method = request.method

    if _is_mimo_audio_speech(path, req_json):
        return await _proxy_mimo_audio_speech(request, path, body, req_json, api_key)
    if _is_ark_chat_completion(path, req_json):
        return await _proxy_ark_chat_completion(request, path, body, req_json, api_key)

    # ── Non-streaming or unknown ───────────────────────────────────────────
    is_stream = req_json.get("stream", False)

    if not is_stream:
        try:
            resp = await http_client.request(method, url, headers=headers, content=body)
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": str(e)})

        resp_body = resp.content
        try:
            resp_json = json.loads(resp_body)
        except Exception:
            resp_json = {}

        # Bill: extract tokens, fallback to estimation
        tokens = extract_request_tokens(resp_json, req_json)
        if resp.is_success and (tokens["total_tokens"] > 0 or tokens["input_tokens"] > 0 or tokens["output_tokens"] > 0):
            cost = calculate_cost(model, tokens)
            await record_billing(api_key, model, cost, {"path": path, "estimated": tokens.get("_estimated", False)})

        return Response(content=resp_body, status_code=resp.status_code, headers=dict(resp.headers))

    # ── Streaming (SSE) ────────────────────────────────────────────────────
    async def sse_stream():
        chunks = []
        tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        async with http_client.stream(method, url, headers=headers, content=body) as resp:
            async for chunk in resp.aiter_text():
                chunks.append(chunk)
                yield chunk.encode("utf-8")

                # Try to extract usage from final chunk
                for line in chunk.split("\n"):
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            continue
                        try:
                            delta = json.loads(data)
                            if "usage" in delta and delta["usage"]:
                                u = delta["usage"]
                                tokens["input_tokens"] = u.get("prompt_tokens", 0) or u.get("input_tokens", 0)
                                tokens["output_tokens"] = u.get("completion_tokens", 0) or u.get("output_tokens", 0)
                                tokens["total_tokens"] = u.get("total_tokens", 0)
                        except Exception:
                            pass

        # Fallback: if no usage in stream, estimate from output text
        if tokens["total_tokens"] == 0:
            output_payload = {"choices": [], "output": []}
            for chunk in chunks:
                for line in chunk.split("\n"):
                    if line.startswith("data: ") and line[6:] not in ("[DONE]", ""):
                        try:
                            payload = json.loads(line[6:])
                            if isinstance(payload.get("choices"), list):
                                output_payload["choices"].extend(payload["choices"])
                            elif payload.get("delta") or payload.get("message") or payload.get("text"):
                                output_payload["choices"].append(payload)
                            if isinstance(payload.get("output"), list):
                                output_payload["output"].extend(payload["output"])
                        except Exception:
                            pass

            output_text = _extract_response_output_text(output_payload)
            if output_text:
                tokens["output_tokens"] = estimate_tokens(output_text)
                tokens["input_tokens"] = estimate_tokens(_extract_request_input_text(req_json))
                tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]
                tokens["_estimated"] = True

        if resp.is_success and (tokens["total_tokens"] > 0 or tokens["input_tokens"] > 0 or tokens["output_tokens"] > 0):
            cost = calculate_cost(model, tokens)
            await record_billing(api_key, model, cost, {"path": path, "stream": True, "estimated": tokens.get("_estimated", False)})

    return StreamingResponse(sse_stream(), media_type="text/event-stream", status_code=200)


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def v1_proxy(request: Request, path: str):
    return await _proxy_request(request, f"v1/{path}")


@app.api_route("/v1beta/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def v1beta_proxy(request: Request, path: str):
    return await _proxy_request(request, f"v1beta/{path}")


# ─── Admin-only API ────────────────────────────────────────────────────────

def admin_auth(x_admin_key: str = Header("", alias="X-Admin-Key")):
    if x_admin_key not in ADMIN_KEYS:
        raise HTTPException(status_code=403, detail="Admin key invalid")
    return x_admin_key

@app.get("/admin/prices")
async def list_prices(_=Depends(admin_auth)):
    return {"prices": _prices, "default": _prices.get("default")}

@app.post("/admin/prices")
async def set_price(data: dict, _=Depends(admin_auth)):
    """Set price for a model: {"model": "kimi-k2.6", "input": 0.5, "output": 2.0}"""
    model = data.get("model", "")
    if not model:
        raise HTTPException(status_code=400, detail="model required")
    _prices[model] = {"input": float(data.get("input", 1.0)), "output": float(data.get("output", 3.0))}
    _save_json(PRICE_FILE, _prices)
    return {"ok": True, "model": model, "price": _prices[model]}

@app.delete("/admin/prices/{model}")
async def delete_price(model: str, _=Depends(admin_auth)):
    if model in _prices:
        del _prices[model]
        _save_json(PRICE_FILE, _prices)
    return {"ok": True}

@app.get("/admin/billing")
async def get_billing(
    api_key: str = "",
    model: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
    _=Depends(admin_auth),
):
    """Query billing records. api_key can be partial match."""
    records = []
    if BILL_FILE.exists():
        with open(BILL_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if api_key and api_key not in r.get("api_key_hash", ""):
                    continue
                if model and r.get("model") != model:
                    continue
                if date_from and r.get("timestamp", "") < date_from:
                    continue
                if date_to and r.get("timestamp", "") > date_to:
                    continue
                records.append(r)
                if len(records) >= limit:
                    break
    # aggregate
    total_usd = sum(r.get("total_cost_usd", 0) for r in records)
    return {"records": records, "total_cost_usd": round(total_usd, 6), "count": len(records)}

@app.get("/admin/balances")
async def list_balances(_=Depends(admin_auth)):
    return {"balances": _balances}

@app.post("/admin/balances")
async def top_up(data: dict, _=Depends(admin_auth)):
    """Top up balance: {"api_key": "sk-xxx", "amount_usd": 10.0}"""
    api_key = data.get("api_key", "")
    amount = float(data.get("amount_usd", 0))
    if not api_key or amount <= 0:
        raise HTTPException(status_code=400, detail="api_key and positive amount_usd required")
    async with _lock:
        bal = _balances.get(api_key, {"usd": 0.0, "updated_at": ""})
        bal["usd"] = round(bal.get("usd", 0) + amount, 8)
        bal["updated_at"] = datetime.now(timezone.utc).isoformat()
        _balances[api_key] = bal
        _save_json(KEY_BALANCE_FILE, _balances)
    return {"ok": True, "api_key": api_key[:16] + "...", "balance_usd": bal["usd"]}

@app.post("/admin/quotas")
async def set_quota(data: dict, _=Depends(admin_auth)):
    """Set quota: {"api_key": "sk-xxx", "daily_usd": 5.0, "monthly_usd": 50.0}"""
    api_key = data.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key required")
    _quotas[api_key] = {
        "daily_usd": float(data.get("daily_usd", 0)),
        "monthly_usd": float(data.get("monthly_usd", 0)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_json(KEY_QUOTA_FILE, _quotas)
    return {"ok": True, "quota": _quotas[api_key]}

@app.get("/health")
async def health():
    return {"status": "ok", "prices_loaded": len(_prices), "backend": CLIPROXY_URL}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8300)
