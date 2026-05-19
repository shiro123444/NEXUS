"""User Portal — Port 8080
Dashboard for AI Club members: register, login, manage API keys, view usage.
"""
import os
import time
import json
import base64
import shutil
import asyncio
import httpx
import uuid
import re
import ssl
import smtplib
import secrets
import hashlib
import hmac
import socket
from pathlib import Path
from typing import List
from email.message import EmailMessage
from fastapi import FastAPI, Request, Response, Depends, HTTPException, WebSocket, WebSocketDisconnect, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from . import db as portal_db
from .auth import create_user_session, verify_user_session, create_admin_session, verify_admin_session, _get_secret
from ..config import map_model_name
from .game import router as game_router, init_tables as game_init_tables, load_reward_overrides as game_load_rewards

# Ensure static directories exist
REACT_DIST_DIR = Path(os.environ.get("PORTAL_REACT_DIST_DIR", "/root/Kiro-Kroxy/portal-web/dist"))
PORTAL_FAVICON_PATH = Path(os.environ.get("PORTAL_FAVICON_PATH", "/root/Kiro-Kroxy/1.png"))
PLAYGROUND_DIST_DIR = Path(os.environ.get("PORTAL_PLAYGROUND_DIST_DIR", "/root/gpt_image_playground/dist"))
STATIC_DIR = Path(__file__).parent.parent / "web" / "static"
BG_DIR = STATIC_DIR / "backgrounds"
BG_DIR.mkdir(parents=True, exist_ok=True)
AVATAR_DIR = STATIC_DIR / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
MAX_AVATAR_SIZE = 5 * 1024 * 1024
ALLOWED_AVATAR_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
ACTIVE_BG_FILE = STATIC_DIR / "active_bg.txt"
ACTIVE_BG_OPACITY_FILE = STATIC_DIR / "active_bg_opacity.txt"
GAME_IMAGE_DIR = STATIC_DIR / "game_images"
GAME_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
GAME_IMAGE_URL_PREFIX = "/static/game_images"

# Super admin credentials (same as port 8081)
# ⚠️ 请勿修改下方默认值！生产环境通过环境变量 KIRO_ADMIN_USER / KIRO_ADMIN_PASS 覆盖
_PORTAL_ADMIN_USER = os.environ.get("KIRO_ADMIN_USER", "shiro")
_PORTAL_ADMIN_PASS = os.environ.get("KIRO_ADMIN_PASS", "fyz040913")
_EMAIL_VERIFICATION_REQUIRED = os.environ.get("PORTAL_EMAIL_VERIFICATION_REQUIRED", "0").lower() in {"1", "true", "yes", "on"}
_PORTAL_SMTP_HOST = os.environ.get("PORTAL_SMTP_HOST", "").strip()
_PORTAL_SMTP_PORT = int(os.environ.get("PORTAL_SMTP_PORT", "587") or 587)
_PORTAL_SMTP_USER = os.environ.get("PORTAL_SMTP_USER", "").strip()
_PORTAL_SMTP_PASS = os.environ.get("PORTAL_SMTP_PASS", "").strip()
_PORTAL_SMTP_FROM = os.environ.get("PORTAL_SMTP_FROM", "").strip()
_PORTAL_SMTP_SERVER_NAME = os.environ.get("PORTAL_SMTP_SERVER_NAME", "").strip()
_PORTAL_SMTP_IPV4_HOSTS = os.environ.get("PORTAL_SMTP_IPV4_HOSTS", "").strip()
_PORTAL_SMTP_STARTTLS = os.environ.get("PORTAL_SMTP_STARTTLS", "1").lower() in {"1", "true", "yes", "on"}
_PORTAL_SMTP_SSL = os.environ.get("PORTAL_SMTP_SSL", "0").lower() in {"1", "true", "yes", "on"}
_PORTAL_EMAIL_BRAND = os.environ.get("PORTAL_EMAIL_BRAND", "NEXUS")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await portal_db.init_db()
    await game_init_tables()
    await game_load_rewards()
    # Set default background if not set
    if not ACTIVE_BG_FILE.exists():
        ACTIVE_BG_FILE.write_text("")
    if not ACTIVE_BG_OPACITY_FILE.exists():
        ACTIVE_BG_OPACITY_FILE.write_text("1.0")
    yield

app = FastAPI(title="WBU User Portal", docs_url=None, redoc_url=None, lifespan=lifespan)

# Add CORS for external clients (e.g. Cherry Studio)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="kiro_proxy/web/static"), name="static")

# Game module routes (/api/game/*)
app.include_router(game_router)


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get("portal_session")
    if not token:
        return None
    return verify_user_session(token)


def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def get_current_admin(request: Request) -> dict | None:
    token = request.cookies.get("admin_session")
    if not token:
        return None
    return verify_admin_session(token)


def require_admin(request: Request) -> dict:
    admin = get_current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Admin access required")
    return admin


def _email_service_enabled() -> bool:
    return bool(_PORTAL_SMTP_HOST and _PORTAL_SMTP_FROM)


def _email_verification_enabled() -> bool:
    return _EMAIL_VERIFICATION_REQUIRED and _email_service_enabled()


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _is_valid_email(email: str) -> bool:
    return bool(re.fullmatch(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", email or ""))


def _hash_email_code(email: str, code: str, purpose: str = "register") -> str:
    normalized = _normalize_email(email)
    data = f"{normalized}:{purpose}:{code}".encode("utf-8")
    return hmac.new(_get_secret(), data, hashlib.sha256).hexdigest()


def _generate_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class _IPv4SMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        last_error = None
        configured_hosts = [h.strip() for h in re.split(r"[,\s]+", _PORTAL_SMTP_IPV4_HOSTS) if h.strip()]
        addresses = [(h, port) for h in configured_hosts]
        addresses.extend(addr[4] for addr in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM))
        for addr in addresses:
            try:
                return socket.create_connection(addr, timeout)
            except OSError as e:
                last_error = e
        if last_error:
            raise last_error
        raise OSError(f"Unable to resolve IPv4 address for {host}")


class _IPv4SMTPSSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        last_error = None
        configured_hosts = [h.strip() for h in re.split(r"[,\s]+", _PORTAL_SMTP_IPV4_HOSTS) if h.strip()]
        addresses = [(h, port) for h in configured_hosts]
        addresses.extend(addr[4] for addr in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM))
        server_name = _PORTAL_SMTP_SERVER_NAME or host
        for addr in addresses:
            try:
                raw = socket.create_connection(addr, timeout)
                return self.context.wrap_socket(raw, server_hostname=server_name)
            except OSError as e:
                last_error = e
        if last_error:
            raise last_error
        raise OSError(f"Unable to resolve IPv4 address for {host}")


def _send_verification_email(email: str, code: str, purpose: str = "register"):
    if not _PORTAL_SMTP_HOST or not _PORTAL_SMTP_FROM:
        raise RuntimeError("邮件服务未配置")

    if purpose == "bind_email":
      title = "绑定邮箱"
      intro = f"你正在为 {_PORTAL_EMAIL_BRAND} 账号绑定这个邮箱。请输入下面的验证码完成验证。"
      plain_intro = f"你正在为 {_PORTAL_EMAIL_BRAND} 账号绑定邮箱"
    elif purpose == "reset_password":
      title = "重置密码"
      intro = f"你正在重置 {_PORTAL_EMAIL_BRAND} 账号密码。请输入下面的验证码继续操作。"
      plain_intro = f"你正在重置 {_PORTAL_EMAIL_BRAND} 账号密码"
    elif purpose == "change_password":
      title = "修改密码"
      intro = f"你正在修改 {_PORTAL_EMAIL_BRAND} 账号密码。请输入下面的验证码继续操作。"
      plain_intro = f"你正在修改 {_PORTAL_EMAIL_BRAND} 账号密码"
    else:
      title = "完成注册"
      intro = f"你正在注册 {_PORTAL_EMAIL_BRAND} 账号。请输入下面的验证码完成邮箱验证。"
      plain_intro = f"你正在注册 {_PORTAL_EMAIL_BRAND} 账号"

    brand = _PORTAL_EMAIL_BRAND
    html = f"""
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">
      {brand} 验证码：{code}，10 分钟内有效。
    </div>
    <div style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;color:#334155">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;background:#f8fafc">
        <tr>
          <td align="center" style="padding:40px 16px">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:500px;border-collapse:separate;border-spacing:0;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e8ecf1">

              <!-- Logo — pure typography + minimal geometric accent -->
              <tr>
                <td style="padding:36px 44px 0">
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse">
                    <tr>
                      <td>
                        <div style="font-size:16px;font-weight:700;letter-spacing:0.10em;color:#1e293b;line-height:1">{brand}</div>
                      </td>
                      <td align="right">
                        <div style="width:6px;height:6px;background:#0f172a"></div>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>

              <!-- Thin rule -->
              <tr>
                <td style="padding:20px 44px 0">
                  <div style="height:1px;background:#e8ecf1"></div>
                </td>
              </tr>

              <!-- Body -->
              <tr>
                <td style="padding:32px 44px 36px">
                  <div style="font-size:18px;font-weight:700;line-height:1.3;color:#0f172a;letter-spacing:-0.01em">邮箱验证</div>
                  <div style="margin-top:8px;font-size:13px;line-height:1.7;color:#64748b">{intro}</div>

                  <!-- Code — asymmetric left-border frame -->
                  <div style="margin:32px 0 28px">
                    <div style="padding:28px 0 28px 36px;border-left:2px solid #0f172a">
                      <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:#94a3b8;margin-bottom:12px">验证码</div>
                      <div style="font-family:'SF Mono','SFMono-Regular','Roboto Mono','Cascadia Code',Consolas,monospace;font-size:44px;line-height:1.0;font-weight:700;letter-spacing:0.30em;color:#0f172a">{code}</div>
                    </div>
                    <div style="width:48px;height:1px;background:#cbd5e1;margin-top:0"></div>
                  </div>

                  <!-- Info -->
                  <table role="presentation" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin-bottom:28px">
                    <tr>
                      <td style="padding-bottom:6px;font-size:12px;color:#94a3b8;width:64px">有效期</td>
                      <td style="padding-bottom:6px;font-size:12px;font-weight:600;color:#334155">10 分钟</td>
                    </tr>
                    <tr>
                      <td style="font-size:12px;color:#94a3b8">最大尝试</td>
                      <td style="font-size:12px;font-weight:600;color:#334155">5 次</td>
                    </tr>
                  </table>

                  <!-- Safety -->
                  <div style="font-size:12px;line-height:1.8;color:#94a3b8">
                    如果这不是你本人操作，请忽略此邮件。<br>
                    验证码错误超过 5 次或 10 分钟后失效。
                  </div>
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="padding:0 44px 28px">
                  <div style="height:1px;background:#f1f5f9;margin-bottom:16px"></div>
                  <div style="font-size:11px;color:#cbd5e1">
                    {brand} &nbsp;·&nbsp; 自动发送 &nbsp;·&nbsp; 请勿回复
                  </div>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </div>
    """

    plain_text = (
        f"{plain_intro}。\n"
        f"验证码：{code}\n"
        "10 分钟内有效。验证码错误超过 5 次或超过 10 分钟后将失效。\n"
        "如果这不是你本人操作，请忽略此邮件。"
    )

    msg = EmailMessage()
    msg["Subject"] = f"[{_PORTAL_EMAIL_BRAND}] {title}验证码"
    msg["From"] = _PORTAL_SMTP_FROM
    msg["To"] = email
    msg.set_content(plain_text)
    msg.add_alternative(html, subtype="html")

    if _PORTAL_SMTP_SSL:
      with _IPv4SMTPSSL(_PORTAL_SMTP_HOST, _PORTAL_SMTP_PORT, context=ssl.create_default_context(), timeout=20) as server:
        if _PORTAL_SMTP_USER:
          server.login(_PORTAL_SMTP_USER, _PORTAL_SMTP_PASS)
        server.send_message(msg)
      return

    with _IPv4SMTP(_PORTAL_SMTP_HOST, _PORTAL_SMTP_PORT, timeout=20) as server:
      if _PORTAL_SMTP_STARTTLS:
        server.starttls(context=ssl.create_default_context())
      if _PORTAL_SMTP_USER:
        server.login(_PORTAL_SMTP_USER, _PORTAL_SMTP_PASS)
      server.send_message(msg)

# ─── WebSocket Manager ────────────────────────────────────────────────────────

import time
from collections import deque

# Store last 5 minutes of messages
# Each item: { "text": str, "style": str, "user": str, "timestamp": float }
DANMAKU_HISTORY = deque()

def cleanup_danmaku_history():
    """Remove messages older than 5 minutes"""
    now = time.time()
    while DANMAKU_HISTORY and (now - DANMAKU_HISTORY[0]["timestamp"] > 300):
        DANMAKU_HISTORY.popleft()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send history (messages within last 5 minutes)
        cleanup_danmaku_history()
        for msg in list(DANMAKU_HISTORY): # Iterate copy
             # Don't send timestamp to client to keep payload clean
            await websocket.send_json({
                "text": msg["text"],
                "style": msg["style"],
                "user": msg["user"]
            })

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # Add to history
        # We store it with timestamp, but broadcast without it
        DANMAKU_HISTORY.append({**message, "timestamp": time.time()})
        cleanup_danmaku_history()
        
        # Broadcast to all connected clients
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                try:
                    self.active_connections.remove(connection)
                except ValueError:
                    pass

manager = ConnectionManager()

@app.websocket("/ws/danmaku")
async def websocket_endpoint(websocket: WebSocket):
    # Try to identify user from cookies
    cookie_str = websocket.headers.get("cookie", "")
    user = None
    if "portal_session=" in cookie_str:
        try:
             for c in cookie_str.split(";"):
                 if "portal_session=" in c:
                     token = c.split("=")[1].strip()
                     user = verify_user_session(token)
                     break
        except:
            pass
    
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if not data.strip():
                continue
                
            # Determine style based on user identity (Admin check)
            is_admin = False
            # Check if user is admin (student_id == 'admin' or via notes/custom field if we had one)
            # For this scenario, let's assume 'admin' or 'root'
            if user and user.get("student_id") in ("admin", "root", "Administrator"): 
                is_admin = True
                
            msg_style = "admin" if is_admin else "normal"
            
            await manager.broadcast({
                "text": data[:50], # Limit length
                "style": msg_style,
                "user": user.get("student_id") if user else "guest"
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# ─── HTML Page ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
@app.get("/settings", response_class=HTMLResponse)
async def index(request: Request):
    index_file = REACT_DIST_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(
                f.read(),
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
    return HTMLResponse("<h1>Dashboard built not found. Run npm run build in portal-web.</h1>")

@app.get("/favicon.ico", response_class=Response)
async def get_favicon_ico():
  favicon = PORTAL_FAVICON_PATH if PORTAL_FAVICON_PATH.exists() else (REACT_DIST_DIR / "favicon.png")
  return FileResponse(favicon, media_type="image/png")

@app.get("/favicon.png", response_class=Response)
async def get_favicon():
  favicon = PORTAL_FAVICON_PATH if PORTAL_FAVICON_PATH.exists() else (REACT_DIST_DIR / "favicon.png")
  return FileResponse(favicon, media_type="image/png")

@app.get("/favicon.svg", response_class=Response)
async def get_favicon_svg():
  # Prefer the PNG favicon to avoid stale svg icon precedence.
  return RedirectResponse(url="/favicon.png", status_code=302)

@app.get("/vite.svg", response_class=Response)
async def get_vite_svg():
    """Legacy favicon path — redirect to current favicon."""
    return RedirectResponse(url="/favicon.png", status_code=302)

@app.get("/icons.svg", response_class=Response)
async def get_icons():
    return FileResponse(REACT_DIST_DIR / "icons.svg", media_type="image/svg+xml")

from fastapi.responses import FileResponse
app.mount("/assets", StaticFiles(directory=REACT_DIST_DIR / "assets"), name="assets")
app.mount("/static/backgrounds", StaticFiles(directory=STATIC_DIR / "backgrounds"), name="backgrounds")
app.mount("/static/avatars", StaticFiles(directory=str(AVATAR_DIR)), name="avatars")
if PLAYGROUND_DIST_DIR.exists():
    app.mount("/playground", StaticFiles(directory=PLAYGROUND_DIST_DIR, html=True), name="playground")

# ─── Auth API ─────────────────────────────────────────────────────────────────

# Proxy clients for LLM APIs
KIRO_PROXY_TARGET = (
  os.environ.get("ANTHROPIC_BASE_URL")
  or os.environ.get("KIRO_PROXY_TARGET")
  or "http://localhost:8990"
)
KIRO_UPSTREAM_API_KEY = (
  os.environ.get("ANTHROPIC_AUTH_TOKEN")
  or os.environ.get("KIRO_UPSTREAM_API_KEY")
  or "sk-kiro-rs-aa1ee38dec2c347d81a4b79ce297e10e"
).strip()
KIRO_NON_STREAM_TIMEOUT_SECS = float(os.environ.get("KIRO_NON_STREAM_TIMEOUT_SECS", "25"))
OPENAI_PROXY_TARGET = os.environ.get("OPENAI_PROXY_TARGET", "http://127.0.0.1:8300")
OPENAI_UPSTREAM_API_KEY = os.environ.get("OPENAI_UPSTREAM_API_KEY", "sk-wbuai-20260426-fd71f0d3").strip()
MIMO_ANTHROPIC_TARGET = os.environ.get("MIMO_ANTHROPIC_TARGET", "https://fufu.iqach.top/anthropic")
MIMO_ANTHROPIC_PROXY = os.environ.get("MIMO_ANTHROPIC_PROXY", "http://127.0.0.1:7890").strip()
MIMO_ANTHROPIC_API_KEY = os.environ.get("MIMO_ANTHROPIC_API_KEY", "").strip()
BILLING_PRICE_FILE = Path("/opt/billing-gateway/data/model_prices.json")
IMAGE_PLAYGROUND_DAILY_FREE_LIMIT = 20
IMAGE_PLAYGROUND_GENERIC_ERROR = "Image generation failed: service unavailable, please try again"
DEFAULT_OPENAI_MODEL_PRICES = {
  "kimi-k2.6": {"input": 0.95186, "output": 3.95001, "cache_read": 0.16095},
  "gpt-5.2": {"input": 1.50, "output": 6.00},
  "gpt-5.4": {"input": 2.50, "output": 10.00},
  "gpt-5.4-mini": {"input": 0.15, "output": 0.60},
  "mimo-v2.5-pro": {"input": 1.00, "output": 3.00},
  "mimo-v2.5": {"input": 1.00, "output": 3.00},
  "mimo-v2.5-tts": {"input": 1.00, "output": 3.00},
  "mimo-v2.5-tts-voicedesign": {"input": 1.00, "output": 3.00},
  "mimo-v2.5-tts-voiceclone": {"input": 1.00, "output": 3.00},
  "mimo-v2-pro": {"input": 1.00, "output": 3.00},
  "mimo-v2-flash": {"input": 1.00, "output": 3.00},
  "mimo-v2-omni": {"input": 1.00, "output": 3.00},
  "mimo-v2-tts": {"input": 1.00, "output": 3.00},
  "default": {"input": 1.00, "output": 3.00},
}

kiro_proxy_client = httpx.AsyncClient(base_url=KIRO_PROXY_TARGET, timeout=None)
openai_proxy_client = httpx.AsyncClient(base_url=OPENAI_PROXY_TARGET, timeout=None)
mimo_anthropic_client = httpx.AsyncClient(
  base_url=MIMO_ANTHROPIC_TARGET,
  timeout=None,
  proxy=MIMO_ANTHROPIC_PROXY or None,
)

# SoruxGPT Codex API for image generation via Responses API (SSE streaming)
SORUXGPT_BASE_URL = "https://app.soruxgpt.com/api/codex/v1"
SORUXGPT_API_KEY = "137eedbf-6bd6-429b-b1f8-4b520c4fde2c_a"
soruxgpt_image_client = httpx.AsyncClient(base_url=SORUXGPT_BASE_URL, timeout=None, proxy=None)


def _image_playground_log(message: str):
    print(f"[ImagePlayground] {message}", flush=True)


def _extract_error_message(data) -> str:
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("detail") or err.get("code")
            if msg:
                return str(msg)
        for key in ("detail", "message"):
            if data.get(key):
                return str(data[key])
    return ""


def _normalize_soruxgpt_image_size(size) -> str:
    size = str(size or "").strip().lower()
    if not size or size == "auto":
        return "1024x1024"
    return size

# Portal 对外模型：对外暴露名称 -> 实际转发模型
# 全部模型统一走上游网关（默认 8990 / kiro.rs）
PORTAL_MODEL_FORWARD_MAP = {
  "claude-haiku-4.5": "claude-haiku-4.5",
  "claude-haiku-4.5-thinking": "claude-haiku-4.5-thinking",
  "claude-haiku-4-5-thinking": "claude-haiku-4.5-thinking",
  "claude-haiku-4.5-agentic": "claude-haiku-4.5-agentic",
  "claude-haiku-4-5-agentic": "claude-haiku-4.5-agentic",
  "claude-sonnet-4.5": "claude-sonnet-4.5",
  "claude-sonnet-4.5-thinking": "claude-sonnet-4.5-thinking",
  "claude-sonnet-4-5-thinking": "claude-sonnet-4.5-thinking",
  "claude-sonnet-4.5-agentic": "claude-sonnet-4.5-agentic",
  "claude-sonnet-4-5-agentic": "claude-sonnet-4.5-agentic",
  "claude-sonnet-4.6": "claude-sonnet-4.6",
  "claude-sonnet-4-6": "claude-sonnet-4.6",
  "claude-sonnet-4.6-thinking": "claude-sonnet-4.6-thinking",
  "claude-sonnet-4-6-thinking": "claude-sonnet-4.6-thinking",
  "claude-sonnet-4.6-agentic": "claude-sonnet-4.6-agentic",
  "claude-sonnet-4-6-agentic": "claude-sonnet-4.6-agentic",
  "claude-opus-4.6": "claude-opus-4.6",
  "claude-opus-4-6": "claude-opus-4.6",
  "claude-opus-4.6-thinking": "claude-opus-4.6-thinking",
  "claude-opus-4-6-thinking": "claude-opus-4.6-thinking",
  "claude-opus-4.7": "claude-opus-4.7",
  "claude-opus-4-7": "claude-opus-4.7",
  "claude-opus-4.7-thinking": "claude-opus-4.7-thinking",
  "claude-opus-4-7-thinking": "claude-opus-4.7-thinking",
  "kimi-k2.6": "kimi-k2.6",
  "mimo-v2.5-pro": "mimo-v2.5-pro",
  "mimo-v2.5": "mimo-v2.5",
  "mimo-v2.5-tts": "mimo-v2.5-tts",
  "mimo-v2.5-tts-voicedesign": "mimo-v2.5-tts-voicedesign",
  "mimo-v2.5-tts-voiceclone": "mimo-v2.5-tts-voiceclone",
  "mimo-v2-pro": "mimo-v2-pro",
  "mimo-v2-flash": "mimo-v2-flash",
  "mimo-v2-omni": "mimo-v2-omni",
  "mimo-v2-tts": "mimo-v2-tts",
  "gpt-5.2": "gpt-5.2",
  "gpt-5.4": "gpt-5.4",
  "gpt-5.4-mini": "gpt-5.4-mini",
}

MESSAGE_PUBLIC_MODELS = {
  "claude-haiku-4.5",
  "claude-haiku-4.5-thinking",
  "claude-haiku-4-5-thinking",
  "claude-haiku-4.5-agentic",
  "claude-haiku-4-5-agentic",
  "claude-sonnet-4.5",
  "claude-sonnet-4.5-thinking",
  "claude-sonnet-4-5-thinking",
  "claude-sonnet-4.5-agentic",
  "claude-sonnet-4-5-agentic",
  "claude-sonnet-4.6",
  "claude-sonnet-4-6",
  "claude-sonnet-4.6-thinking",
  "claude-sonnet-4-6-thinking",
  "claude-sonnet-4.6-agentic",
  "claude-sonnet-4-6-agentic",
  "claude-opus-4.6",
  "claude-opus-4-6",
  "claude-opus-4.6-thinking",
  "claude-opus-4-6-thinking",
  "claude-opus-4.7",
  "claude-opus-4-7",
  "claude-opus-4.7-thinking",
  "claude-opus-4-7-thinking",
}

KIMI_PUBLIC_MODELS = {
  "kimi-k2.6",
}

MIMO_PUBLIC_MODELS = {
  "mimo-v2.5-pro",
  "mimo-v2.5",
  "mimo-v2.5-tts",
  "mimo-v2.5-tts-voicedesign",
  "mimo-v2.5-tts-voiceclone",
  "mimo-v2-pro",
  "mimo-v2-flash",
  "mimo-v2-omni",
  "mimo-v2-tts",
}

GPT_PUBLIC_MODELS = {
  "gpt-5.2",
  "gpt-5.4",
  "gpt-5.4-mini",
}

OPENAI_PUBLIC_MODELS = KIMI_PUBLIC_MODELS | MIMO_PUBLIC_MODELS | GPT_PUBLIC_MODELS

KEY_GROUP_MODEL_MAP = {
  "claude": MESSAGE_PUBLIC_MODELS,
  "kimi": KIMI_PUBLIC_MODELS,
  "mimo": MIMO_PUBLIC_MODELS,
  "gpt": GPT_PUBLIC_MODELS,
}

RESPONSES_PUBLIC_MODELS = set()

# 兼容不同客户端的模型写法
PORTAL_MODEL_ALIASES = {}

MARKETPLACE_MODEL_META = {
  "claude-haiku-4.5": {
    "family": "haiku",
    "context_window": 200000,
    "max_output_tokens": 64000,
    "description": "轻量低延迟，适合日常问答与工具编排。",
    "display_name": "Claude Haiku 4.5",
    "pricing_usd": {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
    "pricing_native": {"currency": "USD", "input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
  },
  "claude-sonnet-4.5": {
    "family": "sonnet",
    "context_window": 200000,
    "max_output_tokens": 64000,
    "description": "均衡性能与成本，适合大多数开发任务。",
    "display_name": "Claude Sonnet 4.5",
    "pricing_usd": {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "pricing_native": {"currency": "USD", "input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
  },
  "claude-sonnet-4.6": {
    "family": "sonnet",
    "context_window": 1000000,
    "max_output_tokens": 64000,
    "description": "长上下文场景优先，适合大仓库和长链路任务。",
    "display_name": "Claude Sonnet 4.6",
    "pricing_usd": {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "pricing_native": {"currency": "USD", "input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
  },
  "claude-opus-4.6": {
    "family": "opus",
    "context_window": 1000000,
    "max_output_tokens": 64000,
    "description": "旗舰推理模型，适合复杂分析、数学和深度代码任务。",
    "display_name": "Claude Opus 4.6",
    "pricing_usd": {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
    "pricing_native": {"currency": "USD", "input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
  },
  "claude-opus-4.7": {
    "family": "opus",
    "context_window": 1000000,
    "max_output_tokens": 64000,
    "description": "最新旗舰推理模型，顶尖复杂任务处理能力。",
    "display_name": "Claude Opus 4.7",
    "pricing_usd": {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
    "pricing_native": {"currency": "USD", "input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
  },
  "kimi-k2.6": {
    "family": "kimi",
    "context_window": 128000,
    "max_output_tokens": 32000,
    "description": "擅长长上下文理解、中文表达与通用推理，适合问答、总结、写作和代码辅助。",
    "display_name": "Kimi K2.6",
    "pricing_usd": {"input": 0.95186, "output": 3.95001, "cache_write": 0.95186, "cache_read": 0.16095},
    "pricing_native": {"currency": "CNY", "input": 6.5, "output": 27.0, "cache_write": 6.5, "cache_read": 1.1},
  },
  "mimo-v2.5-pro": {
    "family": "mimo",
    "context_window": 1048576,
    "max_output_tokens": 131072,
    "description": "MIMO 高配主力模型，适合复杂推理、长上下文分析与稳定代码任务。",
    "display_name": "MIMO V2.5 Pro",
    "pricing_usd": {"input": 1.00, "output": 3.00},
    "pricing_native": {"currency": "USD", "input": 1.00, "output": 3.00},
  },
  "mimo-v2.5": {
    "family": "mimo",
    "context_window": 1048576,
    "max_output_tokens": 131072,
    "description": "MIMO 通用主力模型，兼顾质量、速度与长上下文能力。",
    "display_name": "MIMO V2.5",
    "pricing_usd": {"input": 1.00, "output": 3.00},
    "pricing_native": {"currency": "USD", "input": 1.00, "output": 3.00},
  },
  "mimo-v2-pro": {
    "family": "mimo",
    "context_window": 1048576,
    "max_output_tokens": 131072,
    "description": "上一代高性能 MIMO 模型，适合推理、总结和通用开发问答。",
    "display_name": "MIMO V2 Pro",
    "pricing_usd": {"input": 1.00, "output": 3.00},
    "pricing_native": {"currency": "USD", "input": 1.00, "output": 3.00},
  },
  "mimo-v2-flash": {
    "family": "mimo",
    "context_window": 256000,
    "max_output_tokens": 131072,
    "description": "低延迟版本，适合高频调用、轻量生成和快速响应场景。",
    "display_name": "MIMO V2 Flash",
    "pricing_usd": {"input": 1.00, "output": 3.00},
    "pricing_native": {"currency": "USD", "input": 1.00, "output": 3.00},
  },
  "mimo-v2-omni": {
    "family": "mimo",
    "context_window": 256000,
    "max_output_tokens": 131072,
    "description": "多模态版本，适合文本与语音等综合交互场景。",
    "display_name": "MIMO V2 Omni",
    "pricing_usd": {"input": 1.00, "output": 3.00},
    "pricing_native": {"currency": "USD", "input": 1.00, "output": 3.00},
  },
  "mimo-v2.5-tts": {
    "family": "mimo",
    "context_window": 8192,
    "max_output_tokens": 8192,
    "description": "MIMO 语音合成模型，适合标准 TTS 输出。",
    "display_name": "MIMO V2.5 TTS",
    "pricing_usd": {"input": 1.00, "output": 3.00},
    "pricing_native": {"currency": "USD", "input": 1.00, "output": 3.00},
  },
  "mimo-v2.5-tts-voicedesign": {
    "family": "mimo",
    "context_window": 8192,
    "max_output_tokens": 8192,
    "description": "支持自定义声线设计的 TTS 版本。",
    "display_name": "MIMO V2.5 TTS VoiceDesign",
    "pricing_usd": {"input": 1.00, "output": 3.00},
    "pricing_native": {"currency": "USD", "input": 1.00, "output": 3.00},
  },
  "mimo-v2.5-tts-voiceclone": {
    "family": "mimo",
    "context_window": 8192,
    "max_output_tokens": 8192,
    "description": "支持音色克隆的 TTS 版本。",
    "display_name": "MIMO V2.5 TTS VoiceClone",
    "pricing_usd": {"input": 1.00, "output": 3.00},
    "pricing_native": {"currency": "USD", "input": 1.00, "output": 3.00},
  },
  "mimo-v2-tts": {
    "family": "mimo",
    "context_window": 8192,
    "max_output_tokens": 8192,
    "description": "轻量语音合成版本，适合基础语音输出需求。",
    "display_name": "MIMO V2 TTS",
    "pricing_usd": {"input": 1.00, "output": 3.00},
    "pricing_native": {"currency": "USD", "input": 1.00, "output": 3.00},
  },
  "gpt-5.2": {
    "family": "gpt",
    "context_window": 200000,
    "max_output_tokens": 128000,
    "description": "稳定通用型 GPT，适合日常问答、写作和通用开发任务。",
    "display_name": "GPT-5.2",
    "pricing_usd": {"input": 1.50, "output": 6.00},
    "pricing_native": {"currency": "USD", "input": 1.50, "output": 6.00},
  },
  "gpt-5.4": {
    "family": "gpt",
    "context_window": 200000,
    "max_output_tokens": 128000,
    "description": "更强推理与代码能力，适合复杂任务和长链路执行。",
    "display_name": "GPT-5.4",
    "pricing_usd": {"input": 2.50, "output": 10.00},
    "pricing_native": {"currency": "USD", "input": 2.50, "output": 10.00},
  },
  "gpt-5.4-mini": {
    "family": "gpt",
    "context_window": 200000,
    "max_output_tokens": 128000,
    "description": "低成本低延迟版本，适合高频轻量请求。",
    "display_name": "GPT-5.4 Mini",
    "pricing_usd": {"input": 0.15, "output": 0.60},
    "pricing_native": {"currency": "USD", "input": 0.15, "output": 0.60},
  },
}

MARKETPLACE_PRICING = {
  "unit": "usd_per_1m_tokens",
  "notes": [],
  "promo": {
    "title": "Opus 上新特惠",
    "description": "Opus 4.6 / 4.7 模型限时 0.4 倍率促销，仅限 5 月 9 日至 12 日！",
    "models": ["claude-opus-4.6", "claude-opus-4.7"],
    "multiplier": 0.4,
    "start_date": "2026-05-09",
    "end_date": "2026-05-12",
  },
}


def _message_model_catalog() -> list[dict]:
  """Public model list exposed to clients (aligned with current portal policy)."""
  return [
    {
      "id": "claude-haiku-4.5",
      "object": "model",
      "created": 1709251200,
      "owned_by": "anthropic",
      "display_name": "Claude Haiku 4.5",
      "model_type": "chat",
      "max_tokens": 64000,
    },
    {
      "id": "claude-sonnet-4.5",
      "object": "model",
      "created": 1709251200,
      "owned_by": "anthropic",
      "display_name": "Claude Sonnet 4.5",
      "model_type": "chat",
      "max_tokens": 64000,
    },
    {
      "id": "claude-sonnet-4.6",
      "object": "model",
      "created": 1718064000,
      "owned_by": "anthropic",
      "display_name": "Claude Sonnet 4.6",
      "model_type": "chat",
      "max_tokens": 64000,
    },
    {
      "id": "claude-opus-4.6",
      "object": "model",
      "created": 1770163200,
      "owned_by": "anthropic",
      "display_name": "Claude Opus 4.6",
      "model_type": "chat",
      "max_tokens": 64000,
    },
    {
      "id": "claude-opus-4.7",
      "object": "model",
      "created": 1775232000,
      "owned_by": "anthropic",
      "display_name": "Claude Opus 4.7",
      "model_type": "chat",
      "max_tokens": 64000,
    },
    {
      "id": "kimi-k2.6",
      "object": "model",
      "created": 1777196109,
      "owned_by": "kimi",
      "display_name": "Kimi K2.6",
      "model_type": "chat",
      "max_tokens": 32000,
    },
    {
      "id": "mimo-v2.5-pro",
      "object": "model",
      "created": 1735689600,
      "owned_by": "mimo",
      "display_name": "MIMO V2.5 Pro",
      "model_type": "chat",
      "max_tokens": 131072,
    },
    {
      "id": "mimo-v2.5",
      "object": "model",
      "created": 1735689600,
      "owned_by": "mimo",
      "display_name": "MIMO V2.5",
      "model_type": "chat",
      "max_tokens": 131072,
    },
    {
      "id": "mimo-v2-pro",
      "object": "model",
      "created": 1735689600,
      "owned_by": "mimo",
      "display_name": "MIMO V2 Pro",
      "model_type": "chat",
      "max_tokens": 131072,
    },
    {
      "id": "mimo-v2-flash",
      "object": "model",
      "created": 1735689600,
      "owned_by": "mimo",
      "display_name": "MIMO V2 Flash",
      "model_type": "chat",
      "max_tokens": 131072,
    },
    {
      "id": "mimo-v2-omni",
      "object": "model",
      "created": 1735689600,
      "owned_by": "mimo",
      "display_name": "MIMO V2 Omni",
      "model_type": "chat",
      "max_tokens": 131072,
    },
    {
      "id": "mimo-v2.5-tts",
      "object": "model",
      "created": 1735689600,
      "owned_by": "mimo",
      "display_name": "MIMO V2.5 TTS",
      "model_type": "audio",
      "max_tokens": 8192,
    },
    {
      "id": "mimo-v2.5-tts-voicedesign",
      "object": "model",
      "created": 1735689600,
      "owned_by": "mimo",
      "display_name": "MIMO V2.5 TTS VoiceDesign",
      "model_type": "audio",
      "max_tokens": 8192,
    },
    {
      "id": "mimo-v2.5-tts-voiceclone",
      "object": "model",
      "created": 1735689600,
      "owned_by": "mimo",
      "display_name": "MIMO V2.5 TTS VoiceClone",
      "model_type": "audio",
      "max_tokens": 8192,
    },
    {
      "id": "mimo-v2-tts",
      "object": "model",
      "created": 1735689600,
      "owned_by": "mimo",
      "display_name": "MIMO V2 TTS",
      "model_type": "audio",
      "max_tokens": 8192,
    },
    {
      "id": "gpt-5.2",
      "object": "model",
      "created": 1765440000,
      "owned_by": "Ark",
      "display_name": "GPT-5.2",
      "model_type": "chat",
      "max_tokens": 128000,
    },
    {
      "id": "gpt-5.4",
      "object": "model",
      "created": 1772668800,
      "owned_by": "Ark",
      "display_name": "GPT-5.4",
      "model_type": "chat",
      "max_tokens": 128000,
    },
    {
      "id": "gpt-5.4-mini",
      "object": "model",
      "created": 1773705600,
      "owned_by": "Ark",
      "display_name": "GPT-5.4 Mini",
      "model_type": "chat",
      "max_tokens": 128000,
    },
  ]


def _model_marketplace_payload() -> dict:
  """Public model square payload shown in portal dashboard.

  Pricing rules are aligned with the current quota implementation in portal DB.
  """
  import datetime as _dt
  promo_start = _dt.date(2026, 5, 9)
  promo_end = _dt.date(2026, 5, 12)
  promo_mult = 0.4
  is_promo = promo_start <= _dt.date.today() <= promo_end

  models = []
  for item in _message_model_catalog():
    model_id = item["id"]
    meta = MARKETPLACE_MODEL_META.get(model_id, {})
    family = meta.get("family") or model_id.split("-")[1]
    model_pricing = dict(meta.get("pricing_usd", {}))
    promo_info = None
    if is_promo and family == "opus":
      promo_info = {
        "multiplier": promo_mult,
        "start_date": "2026-05-09",
        "end_date": "2026-05-12",
        "title": "Opus 上新特惠",
      }
      promo_pricing = {k: round(v * promo_mult, 2) for k, v in model_pricing.items()}
    else:
      promo_pricing = None
    models.append({
      "id": model_id,
      "family": family,
      "context_window": meta.get("context_window", 200000),
      "max_output_tokens": meta.get("max_output_tokens", item.get("max_tokens", 64000)),
      "description": meta.get("description", ""),
      "display_name": meta.get("display_name", item.get("display_name", model_id)),
      "pricing_usd": model_pricing,
      "pricing_native": meta.get("pricing_native", {"currency": "USD"}),
      "pricing_promo": promo_pricing,
      "promo": promo_info,
      "variants": [model_id],
    })

  return {
    "object": "model_marketplace",
    "models": models,
    "pricing": MARKETPLACE_PRICING,
  }


def _normalize_portal_model_or_raise(raw_model) -> tuple[str, str, str]:
  """Normalize model id and return (public_model, backend_model, upstream)."""
  model = (raw_model or "").strip() if isinstance(raw_model, str) else ""
  if not model:
    raise HTTPException(status_code=400, detail="model is required")

  normalized = PORTAL_MODEL_ALIASES.get(model, model)
  if normalized not in PORTAL_MODEL_FORWARD_MAP:
    # 兼容 map_model_name 的旧别名转换
    mapped = map_model_name(model)
    normalized = PORTAL_MODEL_ALIASES.get(mapped, mapped)

  if normalized not in PORTAL_MODEL_FORWARD_MAP:
    raise HTTPException(
      status_code=400,
      detail=f"Unsupported model '{model}'. Allowed: {sorted(PORTAL_MODEL_FORWARD_MAP.keys())}",
    )
  upstream = "openai" if normalized in OPENAI_PUBLIC_MODELS else "kiro"
  return normalized, PORTAL_MODEL_FORWARD_MAP[normalized], upstream


def _ensure_key_group_allows_model(key_info: dict, public_model: str):
  group_name = (key_info.get("group_name") or "claude").strip().lower()
  allowed_models = KEY_GROUP_MODEL_MAP.get(group_name, MESSAGE_PUBLIC_MODELS)
  if public_model not in allowed_models:
    raise HTTPException(status_code=403, detail=f"API Key group '{group_name}' does not allow model '{public_model}'")


def _normalize_body_model_or_raise(body_bytes: bytes) -> tuple[str, str, str, bytes]:
  """Return (public_model, upstream, normalized_body_bytes)."""
  try:
    body = json.loads(body_bytes)
  except Exception:
    raise HTTPException(status_code=400, detail="Invalid JSON body")

  if not isinstance(body, dict):
    raise HTTPException(status_code=400, detail="JSON body must be an object")

  public_model, backend_model, upstream = _normalize_portal_model_or_raise(body.get("model"))
  body["model"] = backend_model
  return public_model, backend_model, upstream, json.dumps(body).encode("utf-8")


def _estimate_tokens(text: str) -> int:
  if not text:
    return 0
  total_chars = len(text)
  return max(1, total_chars // 4 + total_chars % 4 // 2)


def _flatten_text(value) -> str:
  if value is None:
    return ""
  if isinstance(value, str):
    return value
  if isinstance(value, list):
    return "".join(_flatten_text(item) for item in value)
  if isinstance(value, dict):
    parts = []
    for key in ("text", "content", "reasoning_content", "input_text", "output_text", "transcript"):
      if value.get(key):
        parts.append(_flatten_text(value.get(key)))
    return "".join(parts)
  return str(value)


def _extract_request_input_text(req_json: dict) -> str:
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


def _extract_openai_request_text(body: dict) -> str:
  parts = []
  for msg in body.get("messages", []) or []:
    parts.append(_flatten_text(msg.get("content")))
  request_input = body.get("input")
  if request_input:
    parts.append(_flatten_text(request_input))
  prompt = body.get("prompt")
  if prompt:
    parts.append(_flatten_text(prompt))
  return "".join(parts)


def _extract_openai_response_text(payload: dict) -> str:
  parts = []
  for choice in payload.get("choices", []) or []:
    parts.append(_flatten_text(choice.get("text")))
    parts.append(_flatten_text(choice.get("message")))
    parts.append(_flatten_text(choice.get("delta")))
  parts.append(_flatten_text(payload.get("content")))
  parts.append(_flatten_text(payload.get("output_text")))
  for item in payload.get("output", []) or []:
    parts.append(_flatten_text(item))
  return "".join(parts)


def _extract_openai_usage(payload: dict, request_body: dict | None = None) -> tuple[int, int]:
  request_body = request_body or {}
  usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
  input_tokens = int(usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0)
  output_tokens = int(usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0)
  if input_tokens or output_tokens:
    return input_tokens, output_tokens
  input_text = _extract_openai_request_text(request_body)
  output_text = _extract_openai_response_text(payload if isinstance(payload, dict) else {})
  return _estimate_tokens(input_text), _estimate_tokens(output_text)


def _get_openai_model_price(model: str) -> dict:
  prices = dict(DEFAULT_OPENAI_MODEL_PRICES)
  try:
    if BILLING_PRICE_FILE.exists():
      with open(BILLING_PRICE_FILE, "r", encoding="utf-8") as f:
        loaded = json.load(f)
      if isinstance(loaded, dict):
        prices.update(loaded)
  except Exception:
    pass

  if model in prices:
    return prices[model]

  parts = model.split("-")
  for i in range(len(parts), 0, -1):
    prefix = "-".join(parts[:i])
    if prefix in prices:
      return prices[prefix]
  return prices["default"]


def _calculate_openai_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
  price = _get_openai_model_price(model)
  input_cost = input_tokens * float(price.get("input", 1.0)) / 1e6
  output_cost = output_tokens * float(price.get("output", 3.0)) / 1e6
  return round(input_cost + output_cost, 8)


def _openai_content_to_text(content) -> str:
  if isinstance(content, str):
    return content
  if isinstance(content, list):
    parts = []
    for item in content:
      if isinstance(item, str):
        parts.append(item)
      elif isinstance(item, dict):
        if item.get("type") == "text":
          parts.append(item.get("text", ""))
        elif item.get("type") == "input_text":
          parts.append(item.get("text", ""))
    return "".join(parts)
  return ""


def _anthropic_content_to_text(content) -> str:
  if isinstance(content, str):
    return content
  if not isinstance(content, list):
    return ""

  parts = []
  for block in content:
    if isinstance(block, str):
      parts.append(block)
      continue
    if not isinstance(block, dict):
      continue
    block_type = block.get("type")
    if block_type in {"text", "input_text"}:
      parts.append(block.get("text", ""))
    elif block_type == "tool_result":
      parts.append(_flatten_text(block.get("content")))
  return "".join(parts)


def _anthropic_system_to_text(system) -> str:
  if isinstance(system, str):
    return system
  if not isinstance(system, list):
    return ""
  return "".join(
    block.get("text", "")
    for block in system
    if isinstance(block, dict) and block.get("type") in {"text", "input_text"}
  )


def _anthropic_tools_to_openai(tools) -> list[dict]:
  result = []
  for tool in tools or []:
    if not isinstance(tool, dict):
      continue
    name = (tool.get("name") or "").strip()
    if not name:
      continue
    result.append({
      "type": "function",
      "function": {
        "name": name,
        "description": tool.get("description", "") or "",
        "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
      },
    })
  return result


def _anthropic_messages_to_openai_body(body: dict, backend_model: str) -> dict:
  messages = []

  system_text = _anthropic_system_to_text(body.get("system"))
  if system_text:
    messages.append({"role": "system", "content": system_text})

  for msg in body.get("messages", []) or []:
    if not isinstance(msg, dict):
      continue
    role = msg.get("role", "user")
    content = msg.get("content")

    if role == "user":
      text_parts = []
      tool_messages = []
      blocks = content if isinstance(content, list) else [{"type": "text", "text": content}] if content else []
      for block in blocks:
        if isinstance(block, str):
          text_parts.append(block)
          continue
        if not isinstance(block, dict):
          continue
        block_type = block.get("type")
        if block_type in {"text", "input_text"}:
          text_parts.append(block.get("text", ""))
        elif block_type == "tool_result":
          tool_messages.append({
            "role": "tool",
            "tool_call_id": block.get("tool_use_id") or block.get("id") or f"tool_{uuid.uuid4().hex[:8]}",
            "content": _flatten_text(block.get("content")),
          })
      if text_parts:
        messages.append({"role": "user", "content": "".join(text_parts)})
      messages.extend(tool_messages)
      continue

    if role == "assistant":
      text_parts = []
      tool_calls = []
      blocks = content if isinstance(content, list) else [{"type": "text", "text": content}] if content else []
      for block in blocks:
        if isinstance(block, str):
          text_parts.append(block)
          continue
        if not isinstance(block, dict):
          continue
        block_type = block.get("type")
        if block_type in {"text", "input_text"}:
          text_parts.append(block.get("text", ""))
        elif block_type == "tool_use":
          tool_calls.append({
            "id": block.get("id") or f"call_{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {
              "name": block.get("name", ""),
              "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
            },
          })
      assistant_msg = {"role": "assistant", "content": "".join(text_parts) if text_parts else None}
      if tool_calls:
        assistant_msg["tool_calls"] = tool_calls
      messages.append(assistant_msg)

  openai_body = {
    "model": backend_model,
    "messages": messages,
    "stream": bool(body.get("stream", False)),
    "max_tokens": int(body.get("max_tokens") or body.get("max_completion_tokens") or 32000),
  }
  converted_tools = _anthropic_tools_to_openai(body.get("tools"))
  if converted_tools:
    openai_body["tools"] = converted_tools
  return openai_body


def _openai_chat_to_anthropic_body(body: dict, backend_model: str) -> dict:
  system_parts = []
  messages = []

  for msg in body.get("messages", []) or []:
    role = msg.get("role", "user")
    content = _openai_content_to_text(msg.get("content", ""))
    if role == "system":
      if content:
        system_parts.append(content)
      continue
    if role not in {"user", "assistant"}:
      continue
    messages.append({
      "role": role,
      "content": content,
    })

  anthropic_body = {
    "model": backend_model,
    "messages": messages,
    "stream": bool(body.get("stream", False)),
    "max_tokens": int(body.get("max_tokens") or 32000),
  }
  if system_parts:
    anthropic_body["system"] = "\n\n".join(system_parts)
  return anthropic_body


def _openai_usage_from_anthropic(usage: dict | None) -> dict | None:
  if not usage:
    return None
  prompt_tokens = int(usage.get("input_tokens", 0) or 0)
  completion_tokens = int(usage.get("output_tokens", 0) or 0)
  return {
    "prompt_tokens": prompt_tokens,
    "completion_tokens": completion_tokens,
    "total_tokens": prompt_tokens + completion_tokens,
  }


def _openai_response_from_anthropic(payload: dict, public_model: str) -> dict:
  content = payload.get("content", []) if isinstance(payload, dict) else []
  text_parts = []
  for block in content:
    if isinstance(block, dict) and block.get("type") == "text":
      text_parts.append(block.get("text", ""))
  usage = _openai_usage_from_anthropic(payload.get("usage", {}))
  return {
    "id": payload.get("id", f"chatcmpl-{uuid.uuid4().hex}"),
    "object": "chat.completion",
    "created": int(time.time()),
    "model": public_model,
    "choices": [
      {
        "index": 0,
        "message": {
          "role": "assistant",
          "content": "".join(text_parts),
        },
        "finish_reason": payload.get("stop_reason") or "stop",
      }
    ],
    "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
  }


def _anthropic_usage_from_openai(usage: dict | None) -> dict:
  usage = usage or {}
  prompt_tokens = int(usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0)
  completion_tokens = int(usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0)
  cached_tokens = int(((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)) or 0)
  result = {
    "input_tokens": prompt_tokens,
    "output_tokens": completion_tokens,
  }
  if cached_tokens:
    result["cache_read_input_tokens"] = cached_tokens
  return result


def _anthropic_stop_reason_from_openai(reason: str | None, has_tool_calls: bool = False) -> str:
  if has_tool_calls:
    return "tool_use"
  if reason in {None, "", "stop"}:
    return "end_turn"
  if reason == "length":
    return "max_tokens"
  return "end_turn"


def _anthropic_response_from_openai(payload: dict, public_model: str) -> dict:
  choice = ((payload or {}).get("choices") or [{}])[0]
  message = choice.get("message") or {}
  tool_calls = message.get("tool_calls") or []
  content_blocks = []

  text_content = message.get("content")
  if text_content:
    content_blocks.append({"type": "text", "text": text_content})

  for tool_call in tool_calls:
    function = tool_call.get("function") or {}
    raw_args = function.get("arguments") or "{}"
    try:
      parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except Exception:
      parsed_args = {"raw": raw_args}
    content_blocks.append({
      "type": "tool_use",
      "id": tool_call.get("id") or f"toolu_{uuid.uuid4().hex[:12]}",
      "name": function.get("name", ""),
      "input": parsed_args or {},
    })

  return {
    "id": payload.get("id", f"msg_{uuid.uuid4().hex}"),
    "type": "message",
    "role": "assistant",
    "model": public_model,
    "content": content_blocks,
    "stop_reason": _anthropic_stop_reason_from_openai(choice.get("finish_reason"), bool(tool_calls)),
    "stop_sequence": None,
    "usage": _anthropic_usage_from_openai(payload.get("usage")),
  }


def _build_openai_completion_payload_from_stream(public_model: str, chunks: list[str]) -> tuple[dict, dict]:
  content_parts = []
  usage = {}
  response_id = f"chatcmpl-{uuid.uuid4().hex}"
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

  payload = {
    "id": response_id,
    "object": "chat.completion",
    "created": created,
    "model": public_model,
    "choices": [{
      "index": 0,
      "message": {"role": "assistant", "content": "".join(content_parts)},
      "finish_reason": finish_reason,
    }],
    "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
  }
  return payload, usage or {}


def _prepare_upstream_headers(request: Request, key_info: dict | None = None, upstream: str = "kiro") -> dict:
  headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}

  upstream_api_key = KIRO_UPSTREAM_API_KEY if upstream == "kiro" else OPENAI_UPSTREAM_API_KEY
  if upstream_api_key:
    headers["x-api-key"] = upstream_api_key
    headers["Authorization"] = f"Bearer {upstream_api_key}"
  elif key_info:
    auth_header = request.headers.get("Authorization", "")
    x_api_key = request.headers.get("x-api-key", "") or request.headers.get("X-Api-Key", "")
    if auth_header.startswith("Bearer kp-"):
      headers["Authorization"] = auth_header
    elif x_api_key.startswith("kp-"):
      headers["Authorization"] = f"Bearer {x_api_key}"

  headers["content-type"] = "application/json"
  return headers


async def _proxy_openai_chat_completions(request: Request, key_info: dict, public_model: str, backend_model: str, body: dict):
  anthropic_body = _openai_chat_to_anthropic_body(body, backend_model)
  headers = _prepare_upstream_headers(request, key_info, upstream="kiro")
  include_usage = bool(((body.get("stream_options") or {}) if isinstance(body, dict) else {}).get("include_usage"))
  created = int(time.time())
  response_id = f"chatcmpl-{uuid.uuid4().hex}"

  req = kiro_proxy_client.build_request(
    "POST",
    "/v1/messages",
    headers=headers,
    content=json.dumps(anthropic_body).encode("utf-8"),
  )
  r = await kiro_proxy_client.send(req, stream=True)

  if anthropic_body.get("stream"):
    async def event_stream():
      input_tokens = 0
      output_tokens = 0
      cache_read_tokens = 0
      cache_creation_tokens = 0
      sent_role = False
      raw_bytes = bytearray()
      finish_reason = "stop"

      async for chunk in r.aiter_raw():
        raw_bytes.extend(chunk)
        for line in chunk.split(b"\n"):
          if not line.startswith(b"data: "):
            continue
          data = line[6:]
          if data == b"[DONE]":
            continue
          try:
            event = json.loads(data)
          except Exception:
            continue

          event_type = event.get("type")
          if event_type == "message_start":
            usage = event.get("message", {}).get("usage", {})
            input_tokens = int(usage.get("input_tokens", 0) or 0)
            cache_read_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
            cache_creation_tokens = int(usage.get("cache_creation_input_tokens", 0) or 0)
            if not sent_role:
              first_chunk = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": public_model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
              }
              yield f"data: {json.dumps(first_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
              sent_role = True
          elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            text = delta.get("text", "")
            if text:
              out_chunk = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": public_model,
                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
              }
              yield f"data: {json.dumps(out_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
          elif event_type == "message_delta":
            usage = event.get("usage", {})
            output_tokens = int(usage.get("output_tokens", output_tokens) or 0)
            input_tokens = int(usage.get("input_tokens", input_tokens) or input_tokens)
            cache_read_tokens = int(usage.get("cache_read_input_tokens", cache_read_tokens) or cache_read_tokens)
            cache_creation_tokens = int(usage.get("cache_creation_input_tokens", cache_creation_tokens) or cache_creation_tokens)
            finish_reason = event.get("delta", {}).get("stop_reason") or finish_reason

        if False:
          yield b""

      end_chunk = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": public_model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason or "stop"}],
      }
      yield f"data: {json.dumps(end_chunk, ensure_ascii=False)}\n\n".encode("utf-8")

      if include_usage:
        usage_chunk = {
          "id": response_id,
          "object": "chat.completion.chunk",
          "created": created,
          "model": public_model,
          "choices": [],
          "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
          },
        }
        yield f"data: {json.dumps(usage_chunk, ensure_ascii=False)}\n\n".encode("utf-8")

      yield b"data: [DONE]\n\n"

      if (input_tokens + output_tokens) > 0:
        try:
          await portal_db.log_usage(
            key_info["user_id"],
            key_info["key_prefix"],
            public_model,
            input_tokens,
            output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
          )
        except Exception as e:
          print(f"[Usage] Record failed: {e}")

    return StreamingResponse(event_stream(), status_code=r.status_code, media_type="text/event-stream")

  payload = json.loads(await r.aread())
  usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
  input_tokens = int(usage.get("input_tokens", 0) or 0)
  output_tokens = int(usage.get("output_tokens", 0) or 0)
  cache_read_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
  cache_creation_tokens = int(usage.get("cache_creation_input_tokens", 0) or 0)

  if r.status_code >= 400:
    return JSONResponse(payload, status_code=r.status_code)

  if (input_tokens + output_tokens) > 0:
    try:
      await portal_db.log_usage(
        key_info["user_id"],
        key_info["key_prefix"],
        public_model,
        input_tokens,
        output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
      )
    except Exception as e:
      print(f"[Usage] Record failed: {e}")

  return JSONResponse(_openai_response_from_anthropic(payload, public_model), status_code=r.status_code)


async def _proxy_openai_passthrough_chat_completions(request: Request, key_info: dict, public_model: str, backend_model: str, body: dict):
  request_body = dict(body)
  request_body["model"] = backend_model
  headers = _prepare_upstream_headers(request, key_info, upstream="openai")

  req = openai_proxy_client.build_request(
    "POST",
    "/v1/chat/completions",
    headers=headers,
    content=json.dumps(request_body).encode("utf-8"),
  )
  r = await openai_proxy_client.send(req, stream=True)

  if request_body.get("stream"):
    async def event_stream():
      chunks = []
      input_tokens = 0
      output_tokens = 0

      async for chunk in r.aiter_text():
        chunks.append(chunk)
        yield chunk.encode("utf-8")
        for line in chunk.split("\n"):
          if not line.startswith("data: "):
            continue
          data = line[6:]
          if data == "[DONE]" or not data:
            continue
          try:
            payload = json.loads(data)
          except Exception:
            continue
          usage = payload.get("usage", {})
          prompt_tokens = int(usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0)
          completion_tokens = int(usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0)
          if prompt_tokens or completion_tokens:
            input_tokens = prompt_tokens
            output_tokens = completion_tokens

      if not (input_tokens or output_tokens):
        stream_payload = {"choices": []}
        for chunk in chunks:
          for line in chunk.split("\n"):
            if not line.startswith("data: "):
              continue
            data = line[6:]
            if data == "[DONE]" or not data:
              continue
            try:
              payload = json.loads(data)
            except Exception:
              continue
            if isinstance(payload.get("choices"), list):
              stream_payload["choices"].extend(payload["choices"])
        input_tokens, output_tokens = _extract_openai_usage(stream_payload, request_body)

      if (input_tokens + output_tokens) > 0:
        try:
          cost_usd = _calculate_openai_cost_usd(public_model, input_tokens, output_tokens)
          await portal_db.log_usage(
            key_info["user_id"],
            key_info["key_prefix"],
            public_model,
            input_tokens,
            output_tokens,
            cost_usd=cost_usd,
          )
        except Exception as e:
          print(f"[Usage] Record failed: {e}")

    return StreamingResponse(event_stream(), status_code=r.status_code, media_type="text/event-stream")

  payload = json.loads(await r.aread())
  if r.status_code >= 400:
    return JSONResponse(payload, status_code=r.status_code)

  input_tokens, output_tokens = _extract_openai_usage(payload, request_body)
  if (input_tokens + output_tokens) > 0:
    try:
      cost_usd = _calculate_openai_cost_usd(public_model, input_tokens, output_tokens)
      await portal_db.log_usage(
        key_info["user_id"],
        key_info["key_prefix"],
        public_model,
        input_tokens,
        output_tokens,
        cost_usd=cost_usd,
      )
    except Exception as e:
      print(f"[Usage] Record failed: {e}")

  return JSONResponse(payload, status_code=r.status_code)


async def _proxy_openai_messages(request: Request, key_info: dict, public_model: str, backend_model: str, body: dict):
  request_body = _anthropic_messages_to_openai_body(body, backend_model)
  headers = _prepare_upstream_headers(request, key_info, upstream="openai")

  req = openai_proxy_client.build_request(
    "POST",
    "/v1/chat/completions",
    headers=headers,
    content=json.dumps(request_body).encode("utf-8"),
  )
  r = await openai_proxy_client.send(req, stream=True)

  if request_body.get("stream"):
    async def event_stream():
      response_id = f"msg_{uuid.uuid4().hex}"
      sent_message_start = False
      text_block_started = False
      current_text_index = 0
      chunks = []
      usage_obj = {}
      stop_reason = "end_turn"

      async for chunk in r.aiter_text():
        chunks.append(chunk)
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

          if not sent_message_start:
            response_id = payload.get("id") or response_id
            message_start = {
              "type": "message_start",
              "message": {
                "id": response_id,
                "type": "message",
                "role": "assistant",
                "model": public_model,
                "content": [],
                "usage": {"input_tokens": 0, "output_tokens": 0},
              },
            }
            yield f"event: message_start\ndata: {json.dumps(message_start, ensure_ascii=False)}\n\n".encode("utf-8")
            sent_message_start = True

          usage = payload.get("usage") or {}
          if usage:
            usage_obj = usage

          for choice in payload.get("choices", []) or []:
            delta = choice.get("delta") or {}
            text = delta.get("content")
            if text:
              if not text_block_started:
                start_event = {
                  "type": "content_block_start",
                  "index": current_text_index,
                  "content_block": {"type": "text", "text": ""},
                }
                yield f"event: content_block_start\ndata: {json.dumps(start_event, ensure_ascii=False)}\n\n".encode("utf-8")
                text_block_started = True
              delta_event = {
                "type": "content_block_delta",
                "index": current_text_index,
                "delta": {"type": "text_delta", "text": text},
              }
              yield f"event: content_block_delta\ndata: {json.dumps(delta_event, ensure_ascii=False)}\n\n".encode("utf-8")

            if choice.get("finish_reason"):
              stop_reason = _anthropic_stop_reason_from_openai(choice.get("finish_reason"))

        if False:
          yield b""

      if text_block_started:
        stop_block = {"type": "content_block_stop", "index": current_text_index}
        yield f"event: content_block_stop\ndata: {json.dumps(stop_block, ensure_ascii=False)}\n\n".encode("utf-8")

      if not usage_obj:
        payload, usage_obj = _build_openai_completion_payload_from_stream(public_model, chunks)
      usage_event = {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": _anthropic_usage_from_openai(usage_obj),
      }
      yield f"event: message_delta\ndata: {json.dumps(usage_event, ensure_ascii=False)}\n\n".encode("utf-8")
      yield b"event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n"

      input_tokens = int(usage_obj.get("prompt_tokens", 0) or usage_obj.get("input_tokens", 0) or 0)
      output_tokens = int(usage_obj.get("completion_tokens", 0) or usage_obj.get("output_tokens", 0) or 0)
      cache_read_tokens = int(((usage_obj.get("prompt_tokens_details") or {}).get("cached_tokens", 0)) or 0)
      if input_tokens or output_tokens or cache_read_tokens:
        try:
          cost_usd = _calculate_openai_cost_usd(public_model, input_tokens, output_tokens)
          await portal_db.log_usage(
            key_info["user_id"],
            key_info["key_prefix"],
            public_model,
            input_tokens,
            output_tokens,
            cache_read_tokens=cache_read_tokens,
            cost_usd=cost_usd,
          )
        except Exception as e:
          print(f"[Usage] Record failed: {e}")

    return StreamingResponse(event_stream(), status_code=r.status_code, media_type="text/event-stream")

  payload = json.loads(await r.aread())
  if r.status_code >= 400:
    return JSONResponse(payload, status_code=r.status_code)

  input_tokens, output_tokens = _extract_openai_usage(payload, request_body)
  cache_read_tokens = int(((payload.get("usage", {}) or {}).get("prompt_tokens_details", {}) or {}).get("cached_tokens", 0) or 0)
  if input_tokens or output_tokens or cache_read_tokens:
    try:
      cost_usd = _calculate_openai_cost_usd(public_model, input_tokens, output_tokens)
      await portal_db.log_usage(
        key_info["user_id"],
        key_info["key_prefix"],
        public_model,
        input_tokens,
        output_tokens,
        cache_read_tokens=cache_read_tokens,
        cost_usd=cost_usd,
      )
    except Exception as e:
      print(f"[Usage] Record failed: {e}")

  return JSONResponse(_anthropic_response_from_openai(payload, public_model), status_code=r.status_code)


async def _proxy_mimo_anthropic_messages(request: Request, key_info: dict, public_model: str, backend_model: str, body: dict):
  request_body = dict(body)
  request_body["model"] = backend_model
  headers = {
    k: v for k, v in request.headers.items()
    if k.lower() not in ("host", "content-length", "authorization", "x-api-key")
  }
  headers["content-type"] = "application/json"
  headers.setdefault("anthropic-version", "2023-06-01")
  if MIMO_ANTHROPIC_API_KEY:
    headers["x-api-key"] = MIMO_ANTHROPIC_API_KEY
    headers["Authorization"] = f"Bearer {MIMO_ANTHROPIC_API_KEY}"

  req = mimo_anthropic_client.build_request(
    "POST",
    "/v1/messages",
    headers=headers,
    content=json.dumps(request_body).encode("utf-8"),
  )
  r = await mimo_anthropic_client.send(req, stream=True)

  if request_body.get("stream"):
    stream = _stream_and_track(r.aiter_raw(), key_info, public_model, upstream="openai")
    return StreamingResponse(
      stream,
      status_code=r.status_code,
      headers=dict(r.headers),
      media_type=r.headers.get("content-type"),
    )

  payload = json.loads(await r.aread())
  if r.status_code >= 400:
    return JSONResponse(payload, status_code=r.status_code)

  usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
  input_tokens = int(usage.get("input_tokens", 0) or 0)
  output_tokens = int(usage.get("output_tokens", 0) or 0)
  cache_read_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
  cache_creation_tokens = int(usage.get("cache_creation_input_tokens", 0) or 0)

  if input_tokens or output_tokens or cache_read_tokens or cache_creation_tokens:
    try:
      cost_usd = _calculate_openai_cost_usd(public_model, input_tokens, output_tokens)
      await portal_db.log_usage(
        key_info["user_id"],
        key_info["key_prefix"],
        public_model,
        input_tokens,
        output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cost_usd=cost_usd,
      )
    except Exception as e:
      print(f"[Usage] Record failed: {e}")

  return JSONResponse(payload, status_code=r.status_code)


async def _stream_and_track(aiter, key_info: dict, model: str, upstream: str = "kiro"):
  """Yield raw stream chunks while extracting token counts from SSE events."""
  input_tokens = 0
  output_tokens = 0
  cache_read_tokens = 0
  cache_creation_tokens = 0
  raw_bytes = bytearray()

  async for chunk in aiter:
    raw_bytes.extend(chunk)
    for line in chunk.split(b"\n"):
      if line.startswith(b"data: ") and b"[DONE]" not in line:
        try:
          ev = json.loads(line[6:])
          t = ev.get("type", "")
          if t == "message_start":
            u = ev.get("message", {}).get("usage", {})
            input_tokens = u.get("input_tokens", 0)
            cache_read_tokens = u.get("cache_read_input_tokens", 0)
            cache_creation_tokens = u.get("cache_creation_input_tokens", 0)
          elif t == "message_delta":
            delta_usage = ev.get("usage", {})
            output_tokens = delta_usage.get("output_tokens", output_tokens) or output_tokens
            # Some upstreams (e.g. fufu.iqach.top for mimo) report
            # input_tokens / cache tokens in message_delta instead of message_start.
            input_tokens = delta_usage.get("input_tokens") or input_tokens
            cache_read_tokens = delta_usage.get("cache_read_input_tokens") or cache_read_tokens
            cache_creation_tokens = delta_usage.get("cache_creation_input_tokens") or cache_creation_tokens
          elif t == "response.completed":
            usage = ev.get("response", {}).get("usage", {})
            input_tokens = usage.get("input_tokens", input_tokens)
            output_tokens = usage.get("output_tokens", output_tokens)
        except Exception:
          pass
    yield chunk

  # Non-SSE fallback: parse plain JSON response body (e.g. stream=false).
  if (input_tokens + output_tokens) == 0 and raw_bytes:
    try:
      payload = json.loads(raw_bytes.decode("utf-8"))
      usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
      input_tokens = int(usage.get("input_tokens", 0) or 0)
      output_tokens = int(usage.get("output_tokens", 0) or 0)
    except Exception:
      pass

  if (input_tokens + output_tokens) > 0:
    try:
      cost_usd = 0.0
      if upstream == "openai":
        cost_usd = _calculate_openai_cost_usd(model, input_tokens, output_tokens)
      await portal_db.log_usage(
        key_info["user_id"],
        key_info["key_prefix"],
        model,
        input_tokens,
        output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cost_usd=cost_usd,
      )
    except Exception as e:
      print(f"[Usage] Record failed: {e}")


async def _log_kiro_json_usage(payload: dict, key_info: dict, model: str):
  if not key_info or not isinstance(payload, dict):
    return

  usage = payload.get("usage", {}) or {}
  input_tokens = int(usage.get("input_tokens", 0) or 0)
  output_tokens = int(usage.get("output_tokens", 0) or 0)
  cache_read_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
  cache_creation_tokens = int(usage.get("cache_creation_input_tokens", 0) or 0)

  if (input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens) <= 0:
    return

  try:
    await portal_db.log_usage(
      key_info["user_id"],
      key_info["key_prefix"],
      model,
      input_tokens,
      output_tokens,
      cache_read_tokens=cache_read_tokens,
      cache_creation_tokens=cache_creation_tokens,
      cost_usd=0.0,
    )
  except Exception as e:
    print(f"[Usage] Record failed: {e}")


def _json_body_requests_stream(body: bytes) -> bool:
  try:
    payload = json.loads(body.decode("utf-8")) if body else {}
  except Exception:
    return False
  return isinstance(payload, dict) and bool(payload.get("stream"))


def _log_message_payload_shape(model: str, payload: dict):
  if model != "claude-sonnet-4-6" or not isinstance(payload, dict):
    return

  messages = payload.get("messages") or []
  system = payload.get("system")
  tools = payload.get("tools") or []
  metadata = payload.get("metadata")
  context_management = payload.get("context_management")
  thinking = payload.get("thinking")

  def _content_chars(content) -> int:
    if isinstance(content, str):
      return len(content)
    if isinstance(content, list):
      total = 0
      for block in content:
        if isinstance(block, dict):
          total += len(str(block.get("text") or block.get("thinking") or block.get("input") or ""))
        else:
          total += len(str(block))
      return total
    if content is None:
      return 0
    return len(str(content))

  role_counts = {}
  message_chars = 0
  for msg in messages:
    if not isinstance(msg, dict):
      continue
    role = str(msg.get("role") or "unknown")
    role_counts[role] = role_counts.get(role, 0) + 1
    message_chars += _content_chars(msg.get("content"))

  if isinstance(system, str):
    system_chars = len(system)
  elif isinstance(system, list):
    system_chars = sum(len(str(item.get("text") or "")) if isinstance(item, dict) else len(str(item)) for item in system)
  else:
    system_chars = len(str(system)) if system is not None else 0

  try:
    metadata_bytes = len(json.dumps(metadata, ensure_ascii=False).encode("utf-8")) if metadata is not None else 0
  except Exception:
    metadata_bytes = 0
  try:
    context_mgmt_bytes = len(json.dumps(context_management, ensure_ascii=False).encode("utf-8")) if context_management is not None else 0
  except Exception:
    context_mgmt_bytes = 0
  try:
    thinking_bytes = len(json.dumps(thinking, ensure_ascii=False).encode("utf-8")) if thinking is not None else 0
  except Exception:
    thinking_bytes = 0

  print(
    "[PortalDiag] model=%s stream=%s messages=%s roles=%s msg_chars=%s system_chars=%s tools=%s metadata_bytes=%s context_mgmt_bytes=%s thinking_bytes=%s max_tokens=%s"
    % (
      model,
      bool(payload.get("stream", False)),
      len(messages) if isinstance(messages, list) else 0,
      role_counts,
      message_chars,
      system_chars,
      len(tools) if isinstance(tools, list) else 0,
      metadata_bytes,
      context_mgmt_bytes,
      thinking_bytes,
      payload.get("max_tokens"),
    ),
    flush=True,
  )


def _sse_ping_bytes() -> bytes:
  return b'event: ping\ndata: {"type":"ping"}\n\n'


def _sse_error_bytes(message: str) -> bytes:
  payload = {
    "type": "error",
    "error": {
      "type": "upstream_error",
      "message": message,
    },
  }
  return f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


async def _stream_kiro_request_with_heartbeat(client, req, key_info: dict, model: str, upstream: str = "kiro"):
  """Start an SSE response before Kiro's upstream has produced headers.

  Cloudflare can return 524 when the origin accepts a request but does not send
  response bytes while Opus is waiting on capacity. Sending SSE ping events keeps
  the edge connection active until kiro-rs returns the real stream.
  """
  send_task = asyncio.create_task(client.send(req, stream=True))
  response = None
  try:
    yield _sse_ping_bytes()
    while not send_task.done():
      try:
        response = await asyncio.wait_for(asyncio.shield(send_task), timeout=15.0)
      except asyncio.TimeoutError:
        yield _sse_ping_bytes()

    if response is None:
      response = await send_task

    if response.status_code >= 400:
      body = await response.aread()
      detail = body.decode("utf-8", errors="replace") if body else response.reason_phrase
      yield _sse_error_bytes(detail)
      return

    async for chunk in _stream_and_track(response.aiter_raw(), key_info, model, upstream=upstream):
      yield chunk
  except asyncio.CancelledError:
    if response is not None:
      await response.aclose()
    if not send_task.done():
      send_task.cancel()
    raise
  except Exception as e:
    yield _sse_error_bytes(str(e))
  finally:
    if response is not None:
      await response.aclose()


async def _proxy_handler(request: Request, key_info: dict = None, model: str = None, body_override: bytes = None, upstream: str = "kiro", path_override: str = None):
  """Proxy requests to upstream backends."""
  # Exclude client auth headers. Portal authenticates kp-* locally and must
  # forward only the configured upstream credential to avoid duplicate
  # Authorization values such as "Bearer kp-..., Bearer sk-...".
  headers = {
    k: v
    for k, v in request.headers.items()
    if k.lower() not in ("host", "content-length", "authorization", "x-api-key")
  }
  request_body = body_override if body_override is not None else await request.body()
  wants_stream = _json_body_requests_stream(request_body)

  upstream_api_key = KIRO_UPSTREAM_API_KEY if upstream == "kiro" else OPENAI_UPSTREAM_API_KEY

  # Portal 先在本地验证 kp-*，再使用固定上游 API Key 调用后端。
  if upstream_api_key:
    headers["x-api-key"] = upstream_api_key
    headers["Authorization"] = f"Bearer {upstream_api_key}"

  # If we have key_info, auth was validated by portal.
  # Upstream auth is handled via configured upstream API key when present.
  if key_info:
    if not upstream_api_key:
      # Backward compatibility: if no upstream key set, retain original forwarding behavior.
      auth_header = request.headers.get("Authorization", "")
      x_api_key = request.headers.get("x-api-key", "") or request.headers.get("X-Api-Key", "")

      if auth_header.startswith("Bearer kp-"):
        headers["Authorization"] = auth_header
      elif x_api_key.startswith("kp-"):
        headers["Authorization"] = f"Bearer {x_api_key}"
      else:
        print(f"[Proxy] Warning: key_info exists but no valid key in headers")
  else:
    # No key_info means no auth required (e.g., /v1/models GET)
    # Still forward any auth headers if present
    has_auth = any(k.lower() == "authorization" for k in headers)
    if not has_auth:
      api_key = headers.get("x-api-key", "") or headers.get("X-Api-Key", "")
      if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

  url = path_override or request.url.path
  # Compatibility: some clients mistakenly send /v1/v1/* when base_url already ends with /v1.
  if url.startswith("/v1/v1/"):
    url = "/v1/" + url[len("/v1/v1/"):]
  if request.url.query:
    url += "?" + str(request.url.query)

  try:
    client = kiro_proxy_client if upstream == "kiro" else openai_proxy_client
    if (
      upstream == "openai"
      and key_info
      and model
      and str(model).startswith("mimo-")
      and url.split("?", 1)[0] == "/v1/audio/speech"
    ):
      r = await client.request(
        request.method,
        url,
        headers=headers,
        content=request_body,
        timeout=600.0,
      )
      if r.status_code < 400:
        try:
          req_json = json.loads(request_body.decode("utf-8")) if request_body else {}
        except Exception:
          req_json = {}
        input_tokens = _estimate_tokens(_extract_request_input_text(req_json))
        if input_tokens > 0:
          cost_usd = _calculate_openai_cost_usd(model, input_tokens, 0)
          await portal_db.log_usage(
            key_info["user_id"],
            key_info["key_prefix"],
            model,
            input_tokens,
            0,
            cost_usd=cost_usd,
          )
      return Response(
        content=await r.aread(),
        status_code=r.status_code,
        headers=dict(r.headers),
        media_type=r.headers.get("content-type"),
      )

    req = client.build_request(
      request.method,
      url,
      headers=headers,
      content=request_body
    )
    if upstream == "kiro" and wants_stream:
      return StreamingResponse(
        _stream_kiro_request_with_heartbeat(client, req, key_info, model, upstream=upstream),
        status_code=200,
        media_type="text/event-stream",
      )

    if upstream == "kiro" and not wants_stream:
      try:
        r = await client.request(
          request.method,
          url,
          headers=headers,
          content=request_body,
          timeout=KIRO_NON_STREAM_TIMEOUT_SECS,
        )
      except httpx.TimeoutException:
        detail = (
          "Upstream non-stream response timed out before the edge would accept it. "
          "Retry, enable stream=true, or use a lower-latency model."
        )
        return JSONResponse(
          {
            "type": "error",
            "error": {
              "type": "upstream_timeout",
              "message": detail,
            },
          },
          status_code=504,
        )

      content_type = r.headers.get("content-type")
      body = await r.aread()
      if r.status_code < 400 and content_type and "application/json" in content_type:
        try:
          await _log_kiro_json_usage(json.loads(body), key_info, model)
        except Exception:
          pass
      return Response(
        content=body,
        status_code=r.status_code,
        headers=dict(r.headers),
        media_type=content_type,
      )

    r = await client.send(req, stream=True)
    stream = _stream_and_track(r.aiter_raw(), key_info, model, upstream=upstream) if key_info else r.aiter_raw()
    return StreamingResponse(
      stream,
      status_code=r.status_code,
      headers=dict(r.headers),
      media_type=r.headers.get("content-type")
    )
  except Exception as e:
    return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/v1/models")
async def list_models(request: Request):
  """Expose portal-facing models.

  Query:
  - ?for=messages   -> anthropic/messages-facing list
  - default         -> same message list
  """
  message_models = _message_model_catalog()

  model_for = (request.query_params.get("for") or "").strip().lower()
  if model_for in {"messages", "message", "anthropic", "responses", "response", "openai"}:
    data = message_models
  else:
    data = message_models

  return JSONResponse({"object": "list", "data": data})


@app.get("/v1/models/messages")
async def list_message_models():
  return JSONResponse({
    "object": "list",
    "data": _message_model_catalog(),
  })


@app.get("/v1/models/responses")
async def list_responses_models():
  return JSONResponse({
    "object": "list",
    "data": [],
  })


@app.get("/api/model-marketplace")
async def model_marketplace():
  return JSONResponse(_model_marketplace_payload())

async def validate_proxy_auth(request: Request):
    # Support both Authorization: Bearer kp-xxx and x-api-key: kp-xxx (Anthropic SDK)
    auth_header = request.headers.get("Authorization", "")
    key = None
    if auth_header.startswith("Bearer kp-"):
        key = auth_header[7:].strip()
    else:
        api_key = request.headers.get("x-api-key", "")
        if api_key.startswith("kp-"):
            key = api_key.strip()
    
    if not key or not key.startswith("kp-"):
        print(f"[Auth] Invalid header format: auth={auth_header[:20]}... x-api-key={request.headers.get('x-api-key', '')[:20]}...")
        raise HTTPException(status_code=401, detail="Invalid API Key format (must start with kp-)")
    # Validate against portal DB
    try:
        key_info = await portal_db.validate_key(key)
    except Exception as e:
        print(f"[Auth] Exception during validation: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during auth")

    if isinstance(key_info, str):
        if key_info == "quota_exceeded":
            raise HTTPException(status_code=403, detail="已达到上限，感谢体验～")
        else:
            print(f"[Auth] Key validation failed ({key_info}) for: {key[:10]}...")
            raise HTTPException(status_code=401, detail="Invalid or expired API Key")
    
    return key_info

@app.post("/v1/messages")
async def proxy_messages(request: Request):
  key_info = await validate_proxy_auth(request)
  body_bytes = await request.body()
  model, backend_model, upstream, normalized_body = _normalize_body_model_or_raise(body_bytes)
  _ensure_key_group_allows_model(key_info, model)
  if upstream == "openai":
    try:
      body = json.loads(normalized_body)
    except Exception:
      raise HTTPException(status_code=400, detail="Invalid JSON body")
    if model in MIMO_PUBLIC_MODELS:
      return await _proxy_mimo_anthropic_messages(request, key_info, model, backend_model, body)
    return await _proxy_openai_messages(request, key_info, model, backend_model, body)
  if model not in MESSAGE_PUBLIC_MODELS:
    raise HTTPException(status_code=400, detail=f"messages endpoint only supports: {sorted(MESSAGE_PUBLIC_MODELS | OPENAI_PUBLIC_MODELS)}")
  return await _proxy_handler(
    request,
    key_info=key_info,
    model=model,
    body_override=normalized_body,
    upstream=upstream,
  )

@app.post("/v1/chat/completions")
async def proxy_chat_completions(request: Request):
  key_info = await validate_proxy_auth(request)
  body_bytes = await request.body()
  try:
    body = json.loads(body_bytes)
  except Exception:
    raise HTTPException(status_code=400, detail="Invalid JSON body")
  if not isinstance(body, dict):
    raise HTTPException(status_code=400, detail="JSON body must be an object")
  public_model, backend_model, upstream = _normalize_portal_model_or_raise(body.get("model"))
  _ensure_key_group_allows_model(key_info, public_model)
  if upstream == "openai":
    return await _proxy_openai_passthrough_chat_completions(request, key_info, public_model, backend_model, body)
  return await _proxy_openai_chat_completions(request, key_info, public_model, backend_model, body)

# Catch-all for other /v1/* endpoints (e.g., streaming variants, health checks)
@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_v1_catchall(request: Request, path: str):
  """Proxy all other /v1/* requests to backend with auth validation."""
  normalized_path = path[3:] if path.startswith("v1/") else path
  path_override = f"/v1/{normalized_path}"

  # OPTIONS and models listing do not require portal key auth.
  if request.method == "OPTIONS" or normalized_path == "models":
    return await _proxy_handler(request, upstream="kiro", path_override=path_override)

  key_info = await validate_proxy_auth(request)

  # POST/PUT/PATCH: if model exists in JSON body, normalize and route by model type.
  if request.method in ["POST", "PUT", "PATCH"]:
    body_bytes = await request.body()

    # Debug logging for astrbot
    print(f"[Portal] Catchall: path={normalized_path}, method={request.method}")
    try:
      payload = json.loads(body_bytes)
      print(f"[Portal] Request body keys: {list(payload.keys()) if isinstance(payload, dict) else 'not-dict'}")
      if isinstance(payload, dict):
        print(f"[Portal] Model in request: {payload.get('model', 'NO-MODEL')}")
        _log_message_payload_shape(str(payload.get("model") or ""), payload)
    except Exception as e:
      print(f"[Portal] Failed to parse body: {e}")

    try:
      payload = json.loads(body_bytes)
      if isinstance(payload, dict) and "model" in payload:
        model, backend_model, upstream, normalized_body = _normalize_body_model_or_raise(body_bytes)
        _ensure_key_group_allows_model(key_info, model)
        if normalized_path == "messages":
          if upstream == "openai":
            if model in MIMO_PUBLIC_MODELS:
              return await _proxy_mimo_anthropic_messages(request, key_info, model, backend_model, payload)
            return await _proxy_openai_messages(request, key_info, model, backend_model, payload)
          if model not in MESSAGE_PUBLIC_MODELS:
            raise HTTPException(status_code=400, detail=f"messages endpoint only supports: {sorted(MESSAGE_PUBLIC_MODELS | OPENAI_PUBLIC_MODELS)}")
        return await _proxy_handler(
          request,
          key_info=key_info,
          model=model,
          body_override=normalized_body,
          upstream=upstream,
          path_override=path_override,
        )
    except HTTPException as he:
      print(f"[Portal] HTTPException: {he.status_code} - {he.detail}")
      raise
    except Exception as e:
      print(f"[Portal] Exception during normalization: {e}")
      # Non-JSON or parse failure: pass through to Kiro upstream.
      return await _proxy_handler(
        request,
        key_info=key_info,
        model="unknown",
        body_override=body_bytes,
        upstream="kiro",
        path_override=path_override,
      )

    return await _proxy_handler(
      request,
      key_info=key_info,
      model="unknown",
      body_override=body_bytes,
      upstream="kiro",
      path_override=path_override,
    )

  return await _proxy_handler(request, key_info=key_info, model="unknown", upstream="kiro", path_override=path_override)

@app.post("/api/auth/register")
async def register(request: Request):
    body = await request.json()
    sid = (body.get("student_id") or "").strip()
    pwd = (body.get("password") or "").strip()
    email = _normalize_email(body.get("email") or "")
    verification_code = str(body.get("verification_code") or "").strip()
    if not sid or not pwd:
        return JSONResponse({"ok": False, "error": "学号和密码不能为空"}, 400)
    if len(sid) < 4 or len(sid) > 20:
        return JSONResponse({"ok": False, "error": "学号长度应在4-20位"}, 400)
    if len(pwd) < 6:
        return JSONResponse({"ok": False, "error": "密码至少6位"}, 400)
    if _email_verification_enabled():
        if not email or not _is_valid_email(email):
            return JSONResponse({"ok": False, "error": "请输入有效邮箱"}, 400)
        if not re.fullmatch(r"^\d{6}$", verification_code):
            return JSONResponse({"ok": False, "error": "请输入 6 位邮箱验证码"}, 400)
        result = await portal_db.register_user_with_email_verification(
            sid,
            pwd,
            email,
            _hash_email_code(email, verification_code),
        )
    else:
        result = await portal_db.create_user(sid, pwd)
    if not result.get("ok"):
        return JSONResponse(result, 400)

    user = await portal_db.login_user(sid, pwd)
    if not user:
        return JSONResponse({"ok": False, "error": "注册成功，但自动登录失败"}, 500)

    token = create_user_session(user["id"], user["student_id"])
    resp = JSONResponse({"ok": True, "student_id": user["student_id"]})
    resp.set_cookie("portal_session", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return resp


@app.post("/api/auth/send-email-code")
async def send_email_code(request: Request):
    if not _email_verification_enabled():
        return JSONResponse({"ok": False, "error": "邮箱验证码注册未启用"}, 503)

    body = await request.json()
    email = _normalize_email(body.get("email") or "")
    if not _is_valid_email(email):
        return JSONResponse({"ok": False, "error": "请输入有效邮箱"}, 400)

    code = _generate_email_code()
    code_hash = _hash_email_code(email, code)
    client_ip = request.client.host if request.client else ""
    result = await portal_db.create_email_verification(email, "register", code_hash, client_ip)
    if not result.get("ok"):
        return JSONResponse(result, 400)

    try:
        await asyncio.to_thread(_send_verification_email, email, code, "register")
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"验证码发送失败: {e}"}, 502)

    return JSONResponse({"ok": True, "expires_in_seconds": result.get("expires_in_seconds", 600)})


@app.get("/api/auth/register-config")
async def register_config():
    return JSONResponse({
        "email_verification_required": _email_verification_enabled(),
        "email_service_enabled": _email_service_enabled(),
    })


@app.post("/api/auth/reset-password/send-email-code")
async def auth_reset_password_send_email_code(request: Request):
    if not _email_service_enabled():
        return JSONResponse({"ok": False, "error": "邮箱验证码未启用"}, 503)

    body = await request.json()
    sid = (body.get("student_id") or "").strip()
    email = _normalize_email(body.get("email") or "")
    if not sid:
        return JSONResponse({"ok": False, "error": "请输入账号 ID"}, 400)
    if not _is_valid_email(email):
        return JSONResponse({"ok": False, "error": "请输入有效邮箱"}, 400)

    user = await portal_db.get_user_by_student_id(sid)
    if not user:
        return JSONResponse({"ok": False, "error": "账号不存在"}, 404)
    stored_email = _normalize_email(user.get("email") or "")
    if not stored_email:
        return JSONResponse({"ok": False, "error": "该账号未绑定邮箱，无法找回密码"}, 400)
    if stored_email != email:
        return JSONResponse({"ok": False, "error": "账号与邮箱不匹配"}, 400)

    purpose = "reset_password"
    code = _generate_email_code()
    code_hash = _hash_email_code(email, code, purpose)
    client_ip = request.client.host if request.client else ""
    result = await portal_db.create_email_verification(email, purpose, code_hash, client_ip, user.get("id"))
    if not result.get("ok"):
        return JSONResponse(result, 400)

    try:
        await asyncio.to_thread(_send_verification_email, email, code, purpose)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"验证码发送失败: {e}"}, 502)

    return JSONResponse({"ok": True, "expires_in_seconds": result.get("expires_in_seconds", 600)})


@app.post("/api/auth/reset-password")
async def auth_reset_password(request: Request):
    if not _email_service_enabled():
        return JSONResponse({"ok": False, "error": "邮箱验证码未启用"}, 503)

    body = await request.json()
    sid = (body.get("student_id") or "").strip()
    email = _normalize_email(body.get("email") or "")
    verification_code = str(body.get("verification_code") or "").strip()
    new_password = str(body.get("new_password") or "").strip()
    if not sid:
        return JSONResponse({"ok": False, "error": "请输入账号 ID"}, 400)
    if not _is_valid_email(email):
        return JSONResponse({"ok": False, "error": "请输入有效邮箱"}, 400)
    if not re.fullmatch(r"^\d{6}$", verification_code):
        return JSONResponse({"ok": False, "error": "请输入 6 位邮箱验证码"}, 400)
    if len(new_password) < 6:
        return JSONResponse({"ok": False, "error": "新密码至少 6 位"}, 400)

    purpose = "reset_password"
    result = await portal_db.reset_password_with_email_verification(
        sid,
        email,
        _hash_email_code(email, verification_code, purpose),
        new_password,
    )
    if not result.get("ok"):
        return JSONResponse(result, 400)
    return JSONResponse({"ok": True})


@app.post("/api/auth/login")
async def login(request: Request, response: Response):
    body = await request.json()
    sid = (body.get("student_id") or "").strip()
    pwd = (body.get("password") or "").strip()
    user = await portal_db.login_user(sid, pwd)
    if not user:
        return JSONResponse({"ok": False, "error": "学号或密码错误"}, 401)
    token = create_user_session(user["id"], user["student_id"])
    resp = JSONResponse({"ok": True, "student_id": user["student_id"]})
    resp.set_cookie("portal_session", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return resp


@app.post("/api/auth/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("portal_session")
    return resp


@app.get("/api/auth/me")
async def me(request: Request):
    u = get_current_user(request)
    if not u:
        return JSONResponse({"ok": False}, 401)
    user = await portal_db.get_user(u["uid"])
    if not user:
        return JSONResponse({"ok": False}, 401)
    return JSONResponse({"ok": True, **user})


@app.post("/api/account/send-email-code")
async def account_send_email_code(request: Request):
    session_user = require_user(request)
    if not _email_service_enabled():
        return JSONResponse({"ok": False, "error": "邮箱验证码未启用"}, 503)

    body = await request.json()
    email = _normalize_email(body.get("email") or "")
    if not _is_valid_email(email):
        return JSONResponse({"ok": False, "error": "请输入有效邮箱"}, 400)

    code = _generate_email_code()
    purpose = "bind_email"
    code_hash = _hash_email_code(email, code, purpose)
    client_ip = request.client.host if request.client else ""
    result = await portal_db.create_email_verification(email, purpose, code_hash, client_ip, session_user["uid"])
    if not result.get("ok"):
        return JSONResponse(result, 400)

    try:
        await asyncio.to_thread(_send_verification_email, email, code, "bind_email")
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"验证码发送失败: {e}"}, 502)

    return JSONResponse({"ok": True, "expires_in_seconds": result.get("expires_in_seconds", 600)})


@app.post("/api/account/bind-email")
async def account_bind_email(request: Request):
    session_user = require_user(request)
    if not _email_service_enabled():
        return JSONResponse({"ok": False, "error": "邮箱验证码未启用"}, 503)

    body = await request.json()
    email = _normalize_email(body.get("email") or "")
    verification_code = str(body.get("verification_code") or "").strip()
    if not _is_valid_email(email):
        return JSONResponse({"ok": False, "error": "请输入有效邮箱"}, 400)
    if not re.fullmatch(r"^\d{6}$", verification_code):
        return JSONResponse({"ok": False, "error": "请输入 6 位邮箱验证码"}, 400)

    result = await portal_db.bind_email_with_verification(
        session_user["uid"],
        email,
        _hash_email_code(email, verification_code, "bind_email"),
    )
    if not result.get("ok"):
        return JSONResponse(result, 400)
    user = await portal_db.get_user(session_user["uid"])
    return JSONResponse({"ok": True, "user": user})


@app.post("/api/account/change-password")
async def account_change_password(request: Request):
    session_user = require_user(request)
    if not _email_service_enabled():
        return JSONResponse({"ok": False, "error": "邮箱验证码未启用"}, 503)

    body = await request.json()
    current_password = str(body.get("current_password") or "").strip()
    new_password = str(body.get("new_password") or "").strip()
    verification_code = str(body.get("verification_code") or "").strip()
    if not current_password:
        return JSONResponse({"ok": False, "error": "请输入当前密码"}, 400)
    if len(new_password) < 6:
        return JSONResponse({"ok": False, "error": "新密码至少 6 位"}, 400)
    if not re.fullmatch(r"^\d{6}$", verification_code):
        return JSONResponse({"ok": False, "error": "请输入 6 位邮箱验证码"}, 400)

    user = await portal_db.get_user(session_user["uid"])
    email = _normalize_email((user or {}).get("email") or "")
    if not email:
        return JSONResponse({"ok": False, "error": "请先绑定邮箱后再修改密码"}, 400)

    result = await portal_db.change_password_with_email_verification(
        session_user["uid"],
        current_password,
        new_password,
        _hash_email_code(email, verification_code, "change_password"),
    )
    if not result.get("ok"):
        return JSONResponse(result, 400)
    return JSONResponse({"ok": True})


@app.post("/api/account/change-password/send-email-code")
async def account_send_change_password_email_code(request: Request):
    session_user = require_user(request)
    if not _email_service_enabled():
        return JSONResponse({"ok": False, "error": "邮箱验证码未启用"}, 503)

    user = await portal_db.get_user(session_user["uid"])
    if not user:
        return JSONResponse({"ok": False, "error": "用户不存在"}, 404)
    email = _normalize_email(user.get("email") or "")
    if not _is_valid_email(email):
        return JSONResponse({"ok": False, "error": "请先绑定有效邮箱"}, 400)

    purpose = "change_password"
    code = _generate_email_code()
    code_hash = _hash_email_code(email, code, purpose)
    client_ip = request.client.host if request.client else ""
    result = await portal_db.create_email_verification(email, purpose, code_hash, client_ip, session_user["uid"])
    if not result.get("ok"):
        return JSONResponse(result, 400)

    try:
        await asyncio.to_thread(_send_verification_email, email, code, purpose)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"验证码发送失败: {e}"}, 502)

    return JSONResponse({"ok": True, "expires_in_seconds": result.get("expires_in_seconds", 600)})


@app.get("/api/account/profile")
async def account_get_profile(request: Request):
    u = require_user(request)
    user = await portal_db.get_user(u["uid"])
    if not user:
        return JSONResponse({"ok": False, "error": "用户不存在"}, 404)
    return JSONResponse({"ok": True, "user": user})


@app.put("/api/account/profile")
async def account_update_profile(request: Request):
    u = require_user(request)
    body = await request.json()
    display_name = body.get("display_name")
    result = await portal_db.update_profile(u["uid"], display_name=display_name)
    if not result.get("ok"):
        return JSONResponse(result, 400)
    user = await portal_db.get_user(u["uid"])
    return JSONResponse({"ok": True, "user": user})


@app.post("/api/account/avatar")
async def account_upload_avatar(request: Request, file: UploadFile = File(...)):
    u = require_user(request)

    if file.content_type not in ALLOWED_AVATAR_TYPES:
        return JSONResponse({"ok": False, "error": "仅支持 PNG、JPEG、GIF、WebP 格式"}, 400)

    contents = await file.read()
    if len(contents) > MAX_AVATAR_SIZE:
        return JSONResponse({"ok": False, "error": "头像文件不能超过 5MB"}, 400)

    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(contents))
        img = img.convert("RGB") if img.mode in ("RGBA", "P", "LA") else img
        img.thumbnail((256, 256), Image.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        contents = buf.getvalue()
        ext = ".jpg"
    except ImportError:
        ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}
        ext = ext_map.get(file.content_type, ".jpg")

    filename = f"user_{u['uid']}_{uuid.uuid4().hex[:12]}{ext}"
    filepath = AVATAR_DIR / filename
    filepath.write_bytes(contents)

    user = await portal_db.get_user(u["uid"])
    if user and user.get("avatar"):
        old_path = AVATAR_DIR / Path(user["avatar"]).name
        if old_path.exists():
            old_path.unlink(missing_ok=True)

    avatar_path = f"avatars/{filename}"
    await portal_db.update_profile(u["uid"], avatar=avatar_path)
    user = await portal_db.get_user(u["uid"])
    return JSONResponse({"ok": True, "user": user, "avatar_url": f"/static/{avatar_path}"})


# ─── Dashboard API ────────────────────────────────────────────────────────────

@app.get("/api/dashboard")
async def dashboard(request: Request):
    u = require_user(request)
    stats = await portal_db.get_stats(u["uid"])
    return JSONResponse(stats)


# ─── API Keys ─────────────────────────────────────────────────────────────────

@app.get("/api/keys")
async def list_keys(request: Request):
    u = require_user(request)
    keys = await portal_db.list_keys(u["uid"])
    return JSONResponse({"keys": keys})


@app.post("/api/keys")
async def create_key(request: Request):
    u = require_user(request)
    body = await request.json()
    name = str(body.get("name") or "My Key").strip()[:50]
    group_name = str(body.get("group_name") or "claude").strip()[:50].lower()
    if group_name not in KEY_GROUP_MODEL_MAP:
        raise HTTPException(status_code=400, detail="group_name must be 'claude', 'kimi', or 'mimo'")
    expires_at = body.get("expires_at")
    try:
        quota_limit = float(body.get("quota_limit") or 0)
    except ValueError:
        quota_limit = 0.0
    result = await portal_db.create_key(u["uid"], name, group_name, expires_at, quota_limit)
    return JSONResponse(result)


@app.delete("/api/keys/{key_id}")
async def delete_key(key_id: int, request: Request):
    u = require_user(request)
    ok = await portal_db.delete_key(key_id, u["uid"])
    return JSONResponse({"ok": ok})


# ─── Usage Logs ───────────────────────────────────────────────────────────────

@app.get("/api/logs")
async def get_logs(request: Request, limit: int = 50, offset: int = 0):
    u = require_user(request)
    logs = await portal_db.get_logs(u["uid"], min(limit, 200), offset)
    return JSONResponse({"logs": logs})


@app.get("/api/balance-history")
async def get_balance_history(request: Request, limit: int = 200):
    u = require_user(request)
    points = await portal_db.get_balance_history(u["uid"], min(limit, 500))
    return JSONResponse(points)


@app.get("/api/image-playground/quota")
async def get_image_playground_quota(request: Request):
    u = require_user(request)
    quota = await portal_db.get_image_playground_quota(u["uid"], IMAGE_PLAYGROUND_DAILY_FREE_LIMIT)
    return JSONResponse(quota)


async def _proxy_image_playground_request(request: Request, action: str):
    u = require_user(request)
    usage_id = await portal_db.reserve_image_playground_usage(u["uid"], action, "gpt-image-2", IMAGE_PLAYGROUND_DAILY_FREE_LIMIT)
    if usage_id is None:
        raise HTTPException(status_code=429, detail="今日免费图像额度已用完，请明天再试或切换自定义模式")

    def _finalize_bg(uid: int, uid_val: int, in_tok: int, out_tok: int, cost: float, st: str):
        """Fire-and-forget DB finalization — must not block the response."""
        try:
            portal_db._sync_finalize_image_playground_usage(uid_val, in_tok, out_tok, cost, st)
        except Exception:
            pass

    try:
        body = await request.body()

        # ── Try soruxgpt for image generation/editing ──
        if action == "generations":
            result = await _try_soruxgpt_image_gen(body, _finalize_bg, u["uid"], usage_id)
            if result is not None:
                return result
        elif action == "edits":
            ct = request.headers.get("content-type", "")
            result = await _try_soruxgpt_image_edit(body, ct, _finalize_bg, u["uid"], usage_id)
            if result is not None:
                return result

        # SoruxGPT failed — no CPA fallback
        asyncio.get_running_loop().run_in_executor(
            None, _finalize_bg, u["uid"], usage_id, 0, 0, 0.0, "error"
        )
        return JSONResponse({"error": {"message": IMAGE_PLAYGROUND_GENERIC_ERROR}}, status_code=502)
    except HTTPException:
        raise
    except Exception:
        asyncio.get_running_loop().run_in_executor(
            None, _finalize_bg, u["uid"], usage_id, 0, 0, 0.0, "error"
        )
        raise


async def _run_soruxgpt_image_gen(task_id: str, prompt: str, n: int, size: str,
                                   _finalize_bg, uid: int, usage_id: int):
    """Background task: call SoruxGPT, save images, store result in DB.

    The browser only polls SQLite task state, but this background worker can
    still consume SoruxGPT's upstream SSE stream. That avoids the 60s idle
    disconnect seen on non-streaming /images/generations for complex prompts.
    """
    headers = {"Authorization": f"Bearer {SORUXGPT_API_KEY}", "Content-Type": "application/json"}
    retryable_statuses = {408, 502, 503, 504}
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def _collect_b64_values(obj, found: list[str]) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in {"b64_json", "image_b64", "partial_image_b64"} and isinstance(value, str) and value:
                    found.append(value)
                else:
                    _collect_b64_values(value, found)
        elif isinstance(obj, list):
            for item in obj:
                _collect_b64_values(item, found)

    async def _save_image_bytes(image_bytes: bytes, index: int) -> dict | None:
        try:
            fname = f"playground_{prompt_hash[:16]}_{int(time.time())}_{index}.png"
            fpath = GAME_IMAGE_DIR / fname
            await asyncio.to_thread(fpath.write_bytes, image_bytes)
            return {
                "b64_json": base64.b64encode(image_bytes).decode("utf-8"),
                "url": f"{GAME_IMAGE_URL_PREFIX}/{fname}",
            }
        except Exception:
            _image_playground_log(f"generation image_save_failed task={task_id} uid={uid}")
            return None

    async def _items_from_b64s(b64_values: list[str]) -> list[dict]:
        items = []
        seen = set()
        for b64 in b64_values:
            if not b64 or b64 in seen:
                continue
            seen.add(b64)
            try:
                image_bytes = base64.b64decode(b64)
            except Exception:
                continue
            item = await _save_image_bytes(image_bytes, len(items) + 1)
            if item:
                items.append(item)
            if len(items) >= max(1, int(n or 1)):
                break
        return items

    async def _call_soruxgpt_stream() -> tuple[list[dict] | None, str]:
        """Use Responses SSE upstream, but keep the browser-facing API polling."""
        stream_payload = {
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
                    "size": size,
                    "quality": "auto",
                    "output_format": "png",
                    "moderation": "auto",
                }
            ],
            "tool_choice": "auto",
            "store": False,
            "stream": True,
        }
        last_err = IMAGE_PLAYGROUND_GENERIC_ERROR
        for attempt in range(2):
            latest_by_output: dict[str, str] = {}
            completed_b64s: list[str] = []
            _image_playground_log(f"generation stream_start task={task_id} uid={uid} attempt={attempt + 1}")
            try:
                async with soruxgpt_image_client.stream(
                    "POST", "/responses", headers=headers, json=stream_payload, timeout=None
                ) as resp:
                    _image_playground_log(
                        f"generation stream_response task={task_id} uid={uid} attempt={attempt + 1} status={resp.status_code}"
                    )
                    if resp.status_code in retryable_statuses:
                        last_err = f"SoruxGPT stream HTTP {resp.status_code}"
                        if attempt < 1:
                            await asyncio.sleep(2.0)
                            continue
                    if resp.status_code >= 400:
                        try:
                            err_data = json.loads((await resp.aread()).decode("utf-8", errors="replace"))
                            last_err = _extract_error_message(err_data) or f"SoruxGPT stream HTTP {resp.status_code}"
                        except Exception:
                            snippet = (await resp.aread())[:300]
                            last_err = snippet.decode("utf-8", errors="replace") or f"SoruxGPT stream HTTP {resp.status_code}"
                        return None, last_err

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
                                output_key = str(event.get("output_index", 0))
                                latest_by_output[output_key] = b64
                        elif event_type == "response.completed":
                            _collect_b64_values(event.get("response", {}), completed_b64s)
                        elif event_type in {"response.failed", "response.incomplete"}:
                            last_err = _extract_error_message(event) or event_type

                    b64_values = completed_b64s or list(latest_by_output.values())
                    if b64_values:
                        items = await _items_from_b64s(b64_values)
                        if items:
                            return items, ""
                    last_err = last_err or "SoruxGPT stream returned no image"
            except Exception as exc:
                _image_playground_log(
                    f"generation stream_exception task={task_id} uid={uid} attempt={attempt + 1}: {exc!r}"
                )
                last_err = f"SoruxGPT stream failed: {type(exc).__name__}"
            if attempt < 1:
                await asyncio.sleep(2.0)
        return None, last_err

    async def _call_soruxgpt(response_format: str) -> tuple[list[dict] | None, str]:
        """Returns (image_items, error_message). image_items is a list of
        {b64_json, url} dicts on success, or None on failure."""
        body = json.dumps({
            "model": "gpt-image-2",
            "prompt": prompt,
            "n": n,
            "size": size,
            "response_format": response_format,
        })
        last_err = IMAGE_PLAYGROUND_GENERIC_ERROR
        max_attempts = 2 if response_format == "url" else 1
        for attempt in range(max_attempts):
            _image_playground_log(
                f"generation start task={task_id} uid={uid} fmt={response_format} attempt={attempt + 1}"
            )
            try:
                resp = await soruxgpt_image_client.post(
                    "/images/generations", headers=headers, content=body,
                )
                _image_playground_log(
                    f"generation response task={task_id} uid={uid} fmt={response_format} attempt={attempt + 1} status={resp.status_code}"
                )
                if resp.status_code in retryable_statuses:
                    last_err = f"SoruxGPT HTTP {resp.status_code}"
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(2.0)
                        continue
                    continue
                if resp.status_code >= 400:
                    try:
                        err_data = resp.json()
                        last_err = _extract_error_message(err_data) or resp.text[:300]
                    except Exception:
                        last_err = resp.text[:300] or f"SoruxGPT HTTP {resp.status_code}"
                    _image_playground_log(
                        f"generation failed task={task_id} uid={uid} fmt={response_format} status={resp.status_code}"
                    )
                    return None, last_err

                resp_data = resp.json()
                images = resp_data.get("data", [])
                if not images:
                    return None, _extract_error_message(resp_data) or "SoruxGPT returned no image data"

                items = []
                for img in images:
                    item = {}
                    b64 = img.get("b64_json", "")
                    url = img.get("url", "")

                    if b64:
                        item["b64_json"] = b64
                    if url:
                        item["url"] = url
                    if not b64 and not url:
                        continue

                    # Save image to disk
                    try:
                        if b64:
                            image_bytes = base64.b64decode(b64)
                        elif url:
                            dl_resp = await soruxgpt_image_client.get(url)
                            if dl_resp.status_code >= 400:
                                _image_playground_log(
                                    f"generation url_download_failed task={task_id} uid={uid} status={dl_resp.status_code}"
                                )
                                continue
                            image_bytes = dl_resp.content
                            # Convert downloaded image to b64 for frontend compatibility
                            item["b64_json"] = base64.b64encode(image_bytes).decode("utf-8")
                        else:
                            continue

                        fname = f"playground_{prompt_hash[:16]}_{int(time.time())}_{len(items) + 1}.png"
                        fpath = GAME_IMAGE_DIR / fname
                        await asyncio.to_thread(fpath.write_bytes, image_bytes)
                        item["url"] = f"{GAME_IMAGE_URL_PREFIX}/{fname}"
                    except Exception:
                        _image_playground_log(
                            f"generation image_save_failed task={task_id} uid={uid}"
                        )
                        continue
                    items.append(item)

                if items:
                    return items, ""
                return None, "No valid images in response"
            except Exception as exc:
                _image_playground_log(
                    f"generation exception task={task_id} uid={uid} fmt={response_format} attempt={attempt + 1}: {exc!r}"
                )
                last_err = f"SoruxGPT request failed: {type(exc).__name__}"
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2.0)
                continue
        return None, last_err

    # Phase 1: upstream SSE in the background. Browser still uses DB polling.
    items, err_msg = await _call_soruxgpt_stream()
    if items is None:
        _image_playground_log(f"generation stream_failed, trying url format task={task_id} uid={uid}: {err_msg}")
        items, err_msg = await _call_soruxgpt("url")
    if items is None:
        _image_playground_log(f"generation url_failed, trying b64_json task={task_id} uid={uid}: {err_msg}")
        items, err_msg = await _call_soruxgpt("b64_json")

    if items:
        result_json = json.dumps({"created": int(time.time()), "data": items})
        cost_usd = portal_db._calculate_cost_usd("gpt-image-2", 0, 0)
        asyncio.get_running_loop().run_in_executor(
            None, _finalize_bg, uid, usage_id, 0, 0, cost_usd, "success"
        )
        await portal_db.update_playground_task(task_id, "done", result_json=result_json)
        _image_playground_log(f"generation done task={task_id} uid={uid}")
        return

    asyncio.get_running_loop().run_in_executor(
        None, _finalize_bg, uid, usage_id, 0, 0, 0.0, "error"
    )
    if "RemoteProtocolError" in err_msg:
        err_msg = "SoruxGPT 在 60 秒内未返回图片，已尝试流式、URL 与 b64 模式仍失败。请简化提示词或稍后重试。"
    await portal_db.update_playground_task(task_id, "error", error_message=err_msg)
    _image_playground_log(f"generation error task={task_id} uid={uid}: {err_msg}")


async def _run_soruxgpt_image_edit(task_id: str, prompt: str, image_b64s: list[str],
                                    mask_b64: str | None, size: str, model: str,
                                    _finalize_bg, uid: int, usage_id: int):
    """Background task: call SoruxGPT Responses API with reference images."""
    headers = {"Authorization": f"Bearer {SORUXGPT_API_KEY}", "Content-Type": "application/json"}
    retryable_statuses = {408, 502, 503, 504}
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def _collect_b64_values(obj, found: list[str]) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in {"b64_json", "image_b64", "partial_image_b64"} and isinstance(value, str) and value:
                    found.append(value)
                else:
                    _collect_b64_values(value, found)
        elif isinstance(obj, list):
            for item in obj:
                _collect_b64_values(item, found)

    async def _save_image_bytes(image_bytes: bytes, index: int) -> dict | None:
        try:
            fname = f"playground_{prompt_hash[:16]}_{int(time.time())}_{index}.png"
            fpath = GAME_IMAGE_DIR / fname
            await asyncio.to_thread(fpath.write_bytes, image_bytes)
            return {
                "b64_json": base64.b64encode(image_bytes).decode("utf-8"),
                "url": f"{GAME_IMAGE_URL_PREFIX}/{fname}",
            }
        except Exception:
            _image_playground_log(f"edit image_save_failed task={task_id} uid={uid}")
            return None

    async def _items_from_b64s(b64_values: list[str]) -> list[dict]:
        items = []
        seen = set()
        for b64 in b64_values:
            if not b64 or b64 in seen:
                continue
            seen.add(b64)
            try:
                image_bytes = base64.b64decode(b64)
            except Exception:
                continue
            item = await _save_image_bytes(image_bytes, len(items) + 1)
            if item:
                items.append(item)
        return items

    # Build Responses API payload with input_image
    input_content = [{"type": "input_text", "text": prompt}]
    for img_b64 in image_b64s:
        input_content.append({
            "type": "input_image",
            "image_url": f"data:image/png;base64,{img_b64}",
        })

    tool: dict = {
        "type": "image_generation",
        "model": model,
        "size": size,
        "quality": "auto",
        "output_format": "png",
        "moderation": "auto",
    }

    if mask_b64:
        tool["input_image_mask"] = {"image_url": f"data:image/png;base64,{mask_b64}"}

    stream_payload = {
        "model": "gpt-5.4-mini",
        "input": [{"type": "message", "role": "user", "content": input_content}],
        "tools": [tool],
        "tool_choice": "auto",
        "store": False,
        "stream": True,
    }

    last_err = IMAGE_PLAYGROUND_GENERIC_ERROR
    for attempt in range(2):
        latest_by_output: dict[str, str] = {}
        completed_b64s: list[str] = []
        _image_playground_log(f"edit stream_start task={task_id} uid={uid} attempt={attempt + 1}")
        try:
            async with soruxgpt_image_client.stream(
                "POST", "/responses", headers=headers, json=stream_payload, timeout=None
            ) as resp:
                _image_playground_log(
                    f"edit stream_response task={task_id} uid={uid} attempt={attempt + 1} status={resp.status_code}"
                )
                if resp.status_code in retryable_statuses:
                    last_err = f"SoruxGPT edit stream HTTP {resp.status_code}"
                    if attempt < 1:
                        await asyncio.sleep(2.0)
                        continue
                if resp.status_code >= 400:
                    try:
                        err_data = json.loads((await resp.aread()).decode("utf-8", errors="replace"))
                        last_err = _extract_error_message(err_data) or f"SoruxGPT edit stream HTTP {resp.status_code}"
                    except Exception:
                        snippet = (await resp.aread())[:300]
                        last_err = snippet.decode("utf-8", errors="replace") or f"SoruxGPT edit stream HTTP {resp.status_code}"
                    _image_playground_log(f"edit stream_http_error task={task_id} uid={uid}: {last_err}")
                    break

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
                            output_key = str(event.get("output_index", 0))
                            latest_by_output[output_key] = b64
                    elif event_type == "response.completed":
                        _collect_b64_values(event.get("response", {}), completed_b64s)
                    elif event_type in {"response.failed", "response.incomplete"}:
                        last_err = _extract_error_message(event) or event_type

                b64_values = completed_b64s or list(latest_by_output.values())
                if b64_values:
                    items = await _items_from_b64s(b64_values)
                    if items:
                        result_json = json.dumps({"created": int(time.time()), "data": items})
                        cost_usd = portal_db._calculate_cost_usd(model, 0, 0)
                        asyncio.get_running_loop().run_in_executor(
                            None, _finalize_bg, uid, usage_id, 0, 0, cost_usd, "success"
                        )
                        await portal_db.update_playground_task(task_id, "done", result_json=result_json)
                        _image_playground_log(f"edit done task={task_id} uid={uid}")
                        return
                last_err = last_err or "SoruxGPT edit stream returned no image"
        except Exception as exc:
            _image_playground_log(
                f"edit stream_exception task={task_id} uid={uid} attempt={attempt + 1}: {exc!r}"
            )
            last_err = f"SoruxGPT edit stream failed: {type(exc).__name__}"
        if attempt < 1:
            await asyncio.sleep(2.0)

    asyncio.get_running_loop().run_in_executor(
        None, _finalize_bg, uid, usage_id, 0, 0, 0.0, "error"
    )
    await portal_db.update_playground_task(task_id, "error", error_message=last_err)
    _image_playground_log(f"edit error task={task_id} uid={uid}: {last_err}")


async def _try_soruxgpt_image_gen(body: bytes, _finalize_bg, uid: int, usage_id: int):
    """Start image generation as a background task, return task_id for polling.

    The frontend polls /api/image-playground/images/task/{task_id} until done.
    Task state is stored in SQLite so it works across multiple uvicorn workers.
    No long-lived HTTP connection — avoids Cloudflare 524 entirely.
    """
    try:
        req_data = json.loads(body)
    except Exception:
        return None

    prompt = req_data.get("prompt", "")
    if not prompt:
        return None

    n = req_data.get("n", 1)
    size = _normalize_soruxgpt_image_size(req_data.get("size", "1024x1024"))

    task_id = str(uuid.uuid4())[:12]
    await portal_db.create_playground_task(task_id)

    # Periodically clean up old tasks (keep last 10 minutes)
    await portal_db.cleanup_playground_tasks(ttl=600.0)

    asyncio.create_task(
        _run_soruxgpt_image_gen(task_id, prompt, n, size, _finalize_bg, uid, usage_id)
    )

    return JSONResponse({"task_id": task_id, "status": "processing"}, status_code=202)


async def _try_soruxgpt_image_edit(body: bytes, content_type: str, _finalize_bg, uid: int, usage_id: int):
    """Parse multipart form data, extract reference images, generate via SoruxGPT Responses API."""
    import email as _email
    from email.message import Message

    # Parse multipart form data
    if "boundary=" not in (content_type or ""):
        return JSONResponse(
            {"error": {"message": "NEXUS image editing requires multipart form data with reference images."}},
            status_code=400,
        )

    # Prepend Content-Type header so email parser can handle multipart body
    mime_body = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8") + body
    msg: Message = _email.message_from_bytes(mime_body)

    prompt = ""
    size = "1024x1024"
    model = "gpt-image-2"
    image_parts: list[bytes] = []
    mask_bytes: bytes | None = None

    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue

        name = part.get_param("name", header="content-disposition")
        if not name:
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            continue

        if name in ("prompt", "text"):
            prompt = payload.decode("utf-8", errors="replace")
        elif name == "size":
            size = payload.decode("utf-8", errors="replace")
        elif name == "model":
            model = payload.decode("utf-8", errors="replace")
        elif name == "image[]" or name == "image":
            image_parts.append(payload)
        elif name == "mask":
            mask_bytes = payload

    if not prompt:
        return JSONResponse(
            {"error": {"message": "Prompt is required for image editing."}},
            status_code=400,
        )

    if not image_parts:
        return JSONResponse(
            {"error": {"message": "At least one reference image is required for editing."}},
            status_code=400,
        )

    image_b64s: list[str] = []
    for img_bytes in image_parts:
        image_b64s.append(base64.b64encode(img_bytes).decode("utf-8"))

    mask_b64 = base64.b64encode(mask_bytes).decode("utf-8") if mask_bytes else None

    size = _normalize_soruxgpt_image_size(size)

    task_id = str(uuid.uuid4())[:12]
    await portal_db.create_playground_task(task_id)
    await portal_db.cleanup_playground_tasks(ttl=600.0)

    asyncio.create_task(
        _run_soruxgpt_image_edit(task_id, prompt, image_b64s, mask_b64, size, model, _finalize_bg, uid, usage_id)
    )

    return JSONResponse({"task_id": task_id, "status": "processing"}, status_code=202)


@app.post("/api/image-playground/images/generations")
async def image_playground_generations(request: Request):
    return await _proxy_image_playground_request(request, "generations")


@app.post("/api/image-playground/images/edits")
async def image_playground_edits(request: Request):
    return await _proxy_image_playground_request(request, "edits")


@app.get("/api/image-playground/images/task/{task_id}")
async def image_playground_task(task_id: str):
    """Poll for image generation result.

    Always returns 200 — the caller checks the JSON "status" field.
    Task state lives in SQLite so it works across multiple uvicorn workers.
    """
    task = await portal_db.get_playground_task(task_id)
    if task is None:
        return JSONResponse({"status": "error", "error": {"message": "任务已过期，请重新生成"}})
    if task["status"] == "processing":
        return JSONResponse({"status": "processing"})
    if task["status"] == "error":
        return JSONResponse({"status": "error", "error": {"message": task.get("error_message", IMAGE_PLAYGROUND_GENERIC_ERROR)}})
    # status == "done"
    result = json.loads(task["result_json"])
    return JSONResponse({"status": "done", "created": result["created"], "data": result["data"]})

# ─── Background Management ────────────────────────────────────────────────────

DEFAULT_BG_URL = "https://images.unsplash.com/photo-1620641788421-7a1c342ea42e?q=80&w=2874&auto=format&fit=crop"  # Anime/Cyberpunk style

@app.get("/api/bg/active")
async def get_active_bg():
    opacity = 1.0
    if ACTIVE_BG_OPACITY_FILE.exists():
        try:
            opacity = float(ACTIVE_BG_OPACITY_FILE.read_text().strip())
        except Exception:
            opacity = 1.0
    if ACTIVE_BG_FILE.exists():
        bg = ACTIVE_BG_FILE.read_text().strip()
        if bg and (BG_DIR / bg).is_file():
            return JSONResponse({"url": f"/static/backgrounds/{bg}", "opacity": opacity})
        elif bg and bg.startswith("http"):
            return JSONResponse({"url": bg, "opacity": opacity})
    return JSONResponse({"url": DEFAULT_BG_URL, "opacity": opacity})

@app.post("/api/admin/backgrounds/opacity")
async def set_bg_opacity(request: Request):
    require_user(request)
    body = await request.json()
    try:
        opacity = max(0.0, min(1.0, float(body.get("opacity", 1.0))))
    except Exception:
        opacity = 1.0
    ACTIVE_BG_OPACITY_FILE.write_text(str(opacity))
    return JSONResponse({"ok": True, "opacity": opacity})

@app.get("/api/admin/backgrounds")
async def list_backgrounds(request: Request):
    # Simple check
    u = require_user(request)
    files = [f.name for f in BG_DIR.glob("*") if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif', '.webp')]
    return JSONResponse({"files": files})

@app.post("/api/admin/backgrounds/upload")
async def upload_background(request: Request, file: UploadFile = File(...)):
    u = require_user(request)
    file_path = BG_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return JSONResponse({"ok": True, "filename": file.filename})

@app.post("/api/admin/backgrounds/active")
async def set_active_background(request: Request):
    u = require_user(request)
    body = await request.json()
    filename = body.get("filename")
    if filename:
        ACTIVE_BG_FILE.write_text(filename)
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False}, 400)


# ─── Super Admin Auth ──────────────────────────────────────────────────────────

@app.post("/api/admin/auth/login")
async def portal_admin_login(request: Request, response: Response):
    body = await request.json()
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    if username == _PORTAL_ADMIN_USER and password == _PORTAL_ADMIN_PASS:
        token = create_admin_session(username)
        resp = JSONResponse({"ok": True})
        resp.set_cookie("admin_session", token, httponly=True, samesite="lax", max_age=86400)
        return resp
    return JSONResponse({"ok": False, "error": "用户名或密码错误"}, status_code=401)


@app.post("/api/admin/auth/logout")
async def portal_admin_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("admin_session")
    return resp


@app.get("/api/admin/auth/me")
async def portal_admin_me(request: Request):
    admin = get_current_admin(request)
    if not admin:
        return JSONResponse({"ok": False}, 401)
    return JSONResponse({"ok": True, "username": admin.get("username", "admin")})


# ─── Super Admin: Users ────────────────────────────────────────────────────────

@app.get("/api/admin/users")
async def admin_list_users(request: Request):
    require_admin(request)
    users = await portal_db.get_all_users()
    return JSONResponse({"users": users})


@app.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, request: Request):
    require_admin(request)
    body = await request.json()
    allowed = {"total_tokens", "balance_usd", "is_active", "notes", "display_name"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if "total_tokens" in updates:
        updates["total_tokens"] = int(updates["total_tokens"])
    if "balance_usd" in updates:
        updates["balance_usd"] = float(updates["balance_usd"])
    if "is_active" in updates:
        updates["is_active"] = int(bool(updates["is_active"]))
    ok = await portal_db.update_user(user_id, **updates)
    return JSONResponse({"ok": ok})


@app.post("/api/admin/users/{user_id}/quota")
async def admin_add_user_quota(user_id: int, request: Request):
    require_admin(request)
    body = await request.json()
    amount = float(body.get("amount", 0) or 0)
    if amount == 0:
        return JSONResponse({"ok": False, "error": "amount must be non-zero"}, 400)
    ok = await portal_db.admin_add_quota(user_id, amount)
    return JSONResponse({"ok": ok})


@app.post("/api/admin/users/quota/batch")
async def admin_add_all_users_quota(request: Request):
    """批量给用户增加余额。传 user_ids 时仅作用于选中用户。"""
    require_admin(request)
    body = await request.json()
    amount = float(body.get("amount", 0) or 0)
    if amount == 0:
        return JSONResponse({"ok": False, "error": "amount must be non-zero"}, 400)
    selected_ids = body.get("user_ids") or []
    selected_ids = {int(uid) for uid in selected_ids if str(uid).isdigit()}

    users = await portal_db.get_all_users()
    success_count = 0
    for user in users:
        if selected_ids and user["id"] not in selected_ids:
            continue
        if user.get("is_active") == 1:
            ok = await portal_db.admin_add_quota(user["id"], amount)
            if ok:
                success_count += 1

    return JSONResponse({"ok": True, "count": success_count, "amount": amount})


@app.delete("/api/admin/users/{user_id}")
async def admin_deactivate_user(user_id: int, request: Request):
    require_admin(request)
    ok = await portal_db.update_user(user_id, is_active=0)
    return JSONResponse({"ok": ok})


# ─── Super Admin: Keys ─────────────────────────────────────────────────────────

@app.get("/api/admin/keys")
async def admin_list_all_keys(request: Request):
    require_admin(request)
    keys = await portal_db.admin_get_all_keys()
    return JSONResponse({"keys": keys})


@app.post("/api/admin/keys/{key_id}/toggle")
async def admin_toggle_key_endpoint(key_id: int, request: Request):
    require_admin(request)
    body = await request.json()
    is_active = int(bool(body.get("is_active", True)))
    ok = await portal_db.admin_toggle_key(key_id, is_active)
    return JSONResponse({"ok": ok})


@app.delete("/api/admin/keys/{key_id}")
async def admin_delete_key_endpoint(key_id: int, request: Request):
    require_admin(request)
    ok = await portal_db.admin_delete_any_key(key_id)
    return JSONResponse({"ok": ok})


# ─── Super Admin: Stats & Logs ─────────────────────────────────────────────────

@app.get("/api/admin/full-stats")
async def admin_full_stats(request: Request):
    require_admin(request)
    stats = await portal_db.admin_get_full_stats()
    return JSONResponse(stats)


@app.get("/api/admin/all-logs")
async def admin_all_logs(request: Request, limit: int = 50, offset: int = 0):
    require_admin(request)
    logs = await portal_db.admin_get_all_logs(min(limit, 200), offset)
    return JSONResponse({"logs": logs})


# ─── Super Admin: Announcements ────────────────────────────────────────────────

@app.post("/api/admin/announcements")
async def admin_send_announcement(request: Request):
    require_admin(request)
    body = await request.json()
    content = (body.get("content") or "").strip()[:100]
    persistent = body.get("persistent", False)  # 是否长时间驻留
    if not content:
        return JSONResponse({"ok": False, "error": "公告内容不能为空"}, 400)
    ann_id = await portal_db.admin_save_announcement(content)
    await manager.broadcast({
        "text": f"[公告] {content}",
        "style": "admin",
        "user": "系统公告",
        "type": "announcement",
        "persistent": persistent  # 标记为驻留公告
    })
    return JSONResponse({"ok": True, "id": ann_id})


@app.get("/api/admin/announcements")
async def admin_list_announcements(request: Request):
    require_admin(request)
    anns = await portal_db.admin_get_announcements()
    return JSONResponse({"announcements": anns})


@app.delete("/api/admin/announcements/{ann_id}")
async def admin_delete_announcement_endpoint(ann_id: int, request: Request):
    require_admin(request)
    ok = await portal_db.admin_delete_announcement(ann_id)
    return JSONResponse({"ok": ok})


# ─── Checkin API (user) ────────────────────────────────────────────────────────

@app.post("/api/user/checkin")
async def user_checkin(request: Request):
    user = require_user(request)
    result = await portal_db.checkin_user(user["uid"])
    return JSONResponse(result)


@app.get("/api/user/checkin/status")
async def user_checkin_status(request: Request):
    from datetime import date
    user = require_user(request)
    today = date.today().isoformat()
    result = await portal_db.get_checkin_status(user["uid"], today)
    return JSONResponse(result)


@app.get("/api/user/checkin/history")
async def user_checkin_history(request: Request, limit: int = 30):
    user = require_user(request)
    result = await portal_db.get_checkin_history(user["uid"], min(limit, 100))
    return JSONResponse(result)


@app.get("/api/user/checkin/leaderboard")
async def user_checkin_leaderboard(request: Request, limit: int = 50):
    user = require_user(request)
    result = await portal_db.get_today_checkin_leaderboard(min(limit, 100))
    return JSONResponse(result)


# ─── Checkin Admin API ────────────────────────────────────────────────────────

@app.get("/api/admin/checkin/config")
async def admin_get_checkin_config(request: Request):
    require_admin(request)
    result = await portal_db.get_checkin_config()
    if isinstance(result, dict):
        result["min_usd"] = round((result.get("min_tokens", 0) or 0) * portal_db.LEGACY_BALANCE_USD_PER_1M / 1e6, 6)
        result["max_usd"] = round((result.get("max_tokens", 0) or 0) * portal_db.LEGACY_BALANCE_USD_PER_1M / 1e6, 6)
    return JSONResponse(result)


@app.post("/api/admin/checkin/config")
async def admin_set_checkin_config(request: Request):
    admin = require_admin(request)
    body = await request.json()
    if "min_usd" in body or "max_usd" in body:
        min_t = int(round(float(body.get("min_usd", 0) or 0) * 1e6 / portal_db.LEGACY_BALANCE_USD_PER_1M))
        max_t = int(round(float(body.get("max_usd", 0) or 0) * 1e6 / portal_db.LEGACY_BALANCE_USD_PER_1M))
    else:
        min_t = int(body.get("min_tokens", 100))
        max_t = int(body.get("max_tokens", 500))
    result = await portal_db.update_checkin_config(min_t, max_t, admin.get("username", "admin"))
    return JSONResponse(result)


@app.get("/api/admin/checkin/stats")
async def admin_checkin_stats(request: Request, days: int = 7):
    require_admin(request)
    result = await portal_db.get_checkin_stats(days)
    return JSONResponse(result)


# ─── HTML Page (embedded) ─────────────────────────────────────────────────────

_HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kiro Proxy 统一模型网关 & 密钥管理平台</title>
<link rel="icon" type="image/png" href="/favicon.png">
<script src="https://lf26-cdn-tos.bytecdntp.com/cdn/expire-1-M/tailwindcss/3.0.23/tailwind.min.js"></script>
<script src="https://unpkg.com/lucide@latest"></script>
<script src="https://lf6-cdn-tos.bytecdntp.com/cdn/expire-1-M/Chart.js/3.7.1/chart.min.js"></script>
<script>
  tailwind.config = {
    darkMode: 'class',
    theme: {
      extend: {
        colors: { zinc: {950: '#09090b', 900: '#18181b', 800: '#27272a'}, brand: '#3b82f6', brandDark: '#2563eb' },
          brand: '#f472b6', // Pink
          brandDark: '#db2777',
        }
      }
    }
  }
</script>
<link href="https://fonts.font.im/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; }
  /* Transparent glass background */
  body { 
    background-color: #09090b; 
    background-size: cover; 
    background-position: center; 
    background-attachment: fixed;
    color:#f4f4f5; 
    font-family: 'RunTo', 'Noto Sans JP', 'Inter', ui-sans-serif, system-ui, sans-serif; 
    min-height: 100vh;
  }
  
  /* Glassmorphism for containers */
  .card, #loginScreen .card, .glass-panel { 
    background: rgba(9, 9, 11, 0.5); /* More transparent */
    backdrop-filter: blur(10px); 
    -webkit-backdrop-filter: blur(10px); 
    border: 1px solid rgba(255, 255, 255, 0.15); 
    border-radius: 16px; 
    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
  }

  /* Navbar glass */
  nav {
    background: rgba(9, 9, 11, 0.6) !important;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
  }


  .btn-primary { 
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); 
    color:#fff; 
    border-radius:12px; 
    padding:8px 20px; 
    font-size:14px; 
    font-weight:600; 
    cursor:pointer; 
    transition:transform .1s, box-shadow .2s; 
    border:none; 
    box-shadow: 0 4px 14px 0 rgba(37, 99, 235, 0.39);
  }
  .btn-primary:active { transform: scale(0.97); }
  .btn-primary:hover { box-shadow: 0 6px 20px rgba(219, 39, 119, 0.23); }
  
  .btn-ghost { background:transparent; color:#e4e4e7; border:1px solid rgba(255,255,255,0.1); border-radius:10px; padding:7px 14px; font-size:13px; cursor:pointer; transition:all .15s; }
  .btn-ghost:hover { background:rgba(255,255,255,0.15); color:#fff; border-color:#3b82f6; }
  
  .input { background:rgba(0, 0, 0, 0.4); border:1px solid rgba(255,255,255,0.15); border-radius:10px; padding:12px 16px; font-size:14px; color:#f4f4f5; width:100%; outline:none; transition:border .2s; }
  .input:focus { border-color:#3b82f6; background:rgba(0,0,0,0.6); }
  .input::placeholder { color:#a1a1aa; }
  
  /* ... (rest of styles similar, customized for blue/anime) ... */
  .badge { display:inline-flex; align-items:center; gap:4px; font-size:11px; font-weight:500; padding:2px 8px; border-radius:999px; }
  .badge-green { background:rgba(5, 46, 22, 0.8); color:#4ade80; border:1px solid #166534; }
  .badge-red { background:rgba(69, 10, 10, 0.8); color:#f87171; border:1px solid #991b1b; }
  
  .tab { padding:8px 16px; font-size:14px; font-weight:600; border-radius:10px; cursor:pointer; color:#a1a1aa; transition:all .2s; }
  .tab.active { background:rgba(59, 130, 246, 0.2); color:#bfdbfe; border:1px solid rgba(59, 130, 246, 0.3); }
  .tab:hover:not(.active) { color:#bfdbfe; }
  
  .progress-bar { height:8px; border-radius:999px; background:rgba(255, 255, 255, 0.1); overflow:hidden; }
  .progress-fill { height:100%; border-radius:999px; background:linear-gradient(90deg, #3b82f6, #2563eb); transition:width .8s cubic-bezier(0.4, 0, 0.2, 1); }
  
  /* ... (toast, keys, scrollbar) ... */
  .toast { position:fixed; bottom:24px; right:24px; padding:12px 20px; border-radius:12px; font-size:14px; z-index:9999; opacity:0; transform:translateY(8px); transition:all .25s; pointer-events:none; }
  .toast.show { opacity:1; transform:none; }
  .toast-success { background:rgba(20, 83, 45, 0.9); color:#4ade80; border:1px solid #22c55e; backdrop-filter:blur(8px); }
  .toast-error { background:rgba(127, 29, 29, 0.9); color:#fca5a5; border:1px solid #ef4444; backdrop-filter:blur(8px); }
  
  .mono { font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size:13px; }
  .secret-key { background:rgba(0, 0, 0, 0.6); border:1px dashed #3b82f6; border-radius:10px; padding:12px; font-size:13px; color:#bfdbfe; word-break:break-all; }

  /* Danmaku Style */
  #danmaku-layer {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 9999; overflow: hidden;
  }
  .danmaku-item {
    position: absolute; white-space: nowrap; font-size: 24px; font-weight: 700;
    text-shadow: 2px 2px 0px rgba(0,0,0,0.5), -1px -1px 0 #3b82f6;
    color: #fff; opacity: 0.95; will-change: transform; pointer-events: none; font-family: 'Noto Sans JP', sans-serif;
  }
  .danmaku-admin {
    color: #ffd700; font-weight: 900; font-size: 32px;
    text-shadow: 0 0 10px rgba(255, 215, 0, 0.8), 3px 3px 0px #000;
    z-index: 10000;
  }
  
  .danmaku-form {
    position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%); z-index: 9990;
    display: flex; gap: 8px; background: rgba(9, 9, 11, 0.7); padding: 6px 10px; border-radius: 999px;
    backdrop-filter: blur(10px); border: 1px solid rgba(59, 130, 246, 0.3);
    transition: all 0.3s; opacity: 0.5;
  }
  .danmaku-form:hover, .danmaku-form:focus-within { opacity: 1; transform: translateX(-50%) scale(1.05); }
  .danmaku-input { background: transparent; border: none; color: #fff; outline: none; width: 220px; padding: 0 8px; font-size:14px; }

  /* ── Super Admin Styles ── */
  .admin-badge { display:inline-flex;align-items:center;gap:3px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700;letter-spacing:.3px; }
  .admin-card { background:rgba(15,10,30,0.55);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(99,102,241,0.2);border-radius:16px;box-shadow:0 8px 32px 0 rgba(99,102,241,0.15); }
  .admin-tab { padding:7px 14px;font-size:13px;font-weight:600;border-radius:9px;cursor:pointer;color:#a1a1aa;transition:all .2s;white-space:nowrap; }
  .admin-tab.active { background:rgba(99,102,241,0.2);color:#c4b5fd;border:1px solid rgba(99,102,241,0.35); }
  .admin-tab:hover:not(.active) { color:#c4b5fd; }
  .btn-danger { background:transparent;color:#f87171;border:1px solid rgba(248,113,113,0.3);border-radius:8px;padding:4px 10px;font-size:12px;cursor:pointer;transition:all .15s; }
  .btn-danger:hover { background:rgba(239,68,68,0.15);border-color:#ef4444; }
  .btn-indigo { background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;border:none;border-radius:10px;padding:8px 18px;font-size:13px;font-weight:600;cursor:pointer;transition:transform .1s,box-shadow .2s;box-shadow:0 4px 14px rgba(99,102,241,0.35); }
  .btn-indigo:hover { box-shadow:0 6px 20px rgba(99,102,241,0.5); }
  .btn-indigo:active { transform:scale(0.97); }
  .ann-banner { position:fixed;top:62px;left:50%;transform:translateX(-50%);z-index:9800;max-width:680px;width:calc(100% - 32px);pointer-events:auto; }

  /* Login redesign */
  .login-shell { width:100%; max-width:980px; display:grid; grid-template-columns:1.2fr 1fr; gap:20px; align-items:stretch; }
  .login-intro { padding:30px; display:flex; flex-direction:column; justify-content:space-between; }
  .login-marks { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-top:20px; }
  .login-mark { background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.12); border-radius:12px; padding:10px 12px; }
  .login-mark .k { color:#bfdbfe; font-size:12px; }
  .login-mark .v { color:#fff; font-weight:700; font-size:14px; margin-top:4px; }
  .auth-card { padding:28px; display:flex; flex-direction:column; justify-content:center; }
  @media (max-width: 900px) {
    .login-shell { grid-template-columns:1fr; max-width:520px; }
    .login-intro { padding:22px; }
    .auth-card { padding:22px; }
  }

  /* Leaderboard animations */
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  @keyframes fadeOut {
    from { opacity: 1; }
    to { opacity: 0; }
  }
  @keyframes danmaku {
    0% { transform: translateX(0); }
    100% { transform: translateX(10px); }
  }
</style>
</head>
<body>

<!-- Background Layer -->
<div id="bg-layer" style="position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;background-size:cover;background-position:center;transition:background-image 1s ease-in-out"></div>

<!-- Danmaku Layer -->
<div id="danmaku-layer"></div>

<!-- Admin Login Modal -->
<div id="adminLoginModal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.75);backdrop-filter:blur(6px);z-index:9500;align-items:center;justify-content:center">
  <div class="admin-card" style="width:90%;max-width:360px;padding:30px;position:relative">
    <div style="text-align:center;margin-bottom:22px">
      <div style="font-size:32px;margin-bottom:8px;filter:drop-shadow(0 0 12px rgba(139,92,246,0.7))">🔐</div>
      <div style="font-size:16px;font-weight:800;color:#fff;letter-spacing:-.3px">超级管理员登录</div>
      <div style="font-size:12px;color:#a1a1aa;margin-top:4px">Super Admin Access</div>
    </div>
    <div style="display:flex;flex-direction:column;gap:12px">
      <input id="adminLoginUser" class="input" type="text" placeholder="管理员用户名" style="border-color:rgba(99,102,241,0.3)">
      <input id="adminLoginPass" class="input" type="password" placeholder="管理员密码" style="border-color:rgba(99,102,241,0.3)" onkeydown="if(event.key==='Enter')doAdminLogin()">
      <button class="btn-indigo" onclick="doAdminLogin()" style="width:100%;padding:11px;margin-top:4px">登录管理后台</button>
      <button class="btn-ghost" onclick="closeAdminLogin()" style="width:100%;padding:8px;font-size:13px">取消</button>
    </div>
  </div>
</div>

<!-- Announcement Banner -->
<div class="ann-banner" id="announcementBanner" style="display:none">
  <div style="background:linear-gradient(135deg,rgba(99,102,241,0.92),rgba(139,92,246,0.92));backdrop-filter:blur(12px);border-radius:12px;padding:11px 18px;display:flex;align-items:center;justify-content:space-between;border:1px solid rgba(165,180,252,0.4);box-shadow:0 4px 24px rgba(99,102,241,0.4)">
    <div style="display:flex;align-items:center;gap:10px">
      <span style="font-size:18px">📢</span>
      <span id="announcementBannerText" style="font-size:13px;font-weight:600;color:#fff;line-height:1.4"></span>
    </div>
    <button onclick="document.getElementById('announcementBanner').style.display='none'" style="background:none;border:none;cursor:pointer;color:rgba(255,255,255,0.7);font-size:20px;padding:0;margin-left:14px;line-height:1;flex-shrink:0">×</button>
  </div>
</div>

<div class="danmaku-form" id="danmakuForm">
  <input type="text" id="danmakuInput" class="danmaku-input" placeholder="WBU AI Club へようこそ (弹幕)..." onkeydown="if(event.key==='Enter')sendDanmaku()">
  <button class="btn-primary" style="padding:4px 14px;border-radius:99px;font-size:12px;background:#db2777" onclick="sendDanmaku()">发送</button>
</div>

<!-- Toast -->
<div id="toast" class="toast"></div>

<!-- Welcome Modal -->
<div id="welcomeOverlay" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);backdrop-filter:blur(4px);z-index:9000;align-items:center;justify-content:center">
  <div class="card" style="width:90%;max-width:500px;padding:32px;text-align:center;position:relative;background:rgba(20,20,20,0.9)">
    <i data-lucide="sparkles" style="width:48px;height:48px;margin: 0 auto 12px;color:#3b82f6"></i>
    <div style="font-size:20px;font-weight:800;color:#fff;margin-bottom:16px;letter-spacing:-0.5px">
      欢迎来到 Kiro Proxy
    </div>
    <div style="font-size:14px;color:#cbd5e1;line-height:1.6;margin-bottom:24px;text-align:left;background:rgba(0,0,0,0.3);padding:16px;border-radius:12px;border:1px solid #334155 border-left:4px solid #3b82f6">
      <p style="margin-bottom:8px"><b>您好，欢迎加入本平台！</b></p>
      <p style="margin-bottom:8px">此工作台为您提供了统一的 AI 模型调用网关、Token 消费统计及 Key 管理功能。</p>
      <p style="margin-bottom:0">请阅读平台公告并享受您的 AI 之旅。</p>
    </div>
    <button class="btn-primary" onclick="closeWelcome()" style="width:100%;font-size:15px;padding:12px">进入控制台</button>
  </div>
</div>

<!-- Login Screen -->
<div id="loginScreen" class="min-h-screen flex items-center justify-center p-4" style="display:none!important">
  <div style="width:100%; max-width:420px;">
    <div class="card auth-card" style="padding:32px;">
      <div style="text-align:center;margin-bottom:24px;">
        <i data-lucide="layers" style="width:42px;height:42px;color:#3b82f6;margin:0 auto 12px;"></i>
        <div style="font-size:22px;font-weight:800;color:#fff;">Kiro Proxy</div>
        <div style="color:#94a3b8;font-size:13px;margin-top:4px;">统一模型认证网关与控制台</div>
      </div>
      <div id="authTabs" style="display:flex;gap:4px;background:rgba(0,0,0,0.4);border-radius:12px;padding:4px;margin-bottom:22px;border:1px solid rgba(255,255,255,0.1)">
        <button onclick="switchAuthTab('login')" id="tabLogin" class="tab active" style="flex:1;text-align:center">用户登录</button>
        <button onclick="switchAuthTab('register')" id="tabRegister" class="tab" style="flex:1;text-align:center">账户注册</button>
      </div>

      <div id="formLogin">
        <label style="display:block;margin-bottom:6px;font-size:13px;color:#cbd5e1;font-weight:500;">账号 / 学号 / 邮箱</label>
        <input type="text" id="l_user" class="input" placeholder="输入您的用户名或学号" style="margin-bottom:16px;">
        <label style="display:block;margin-bottom:6px;font-size:13px;color:#cbd5e1;font-weight:500;">密码</label>
        <input type="password" id="l_pass" class="input" placeholder="输入密码" style="margin-bottom:24px;" onkeydown="if(event.key==='Enter')doLogin()">
        <button class="btn-primary" onclick="doLogin()" style="width:100%;padding:12px;font-size:15px;display:flex;justify-content:center;align-items:center;gap:8px;"><i data-lucide="log-in" style="width:18px;height:18px;"></i> 登录</button>
      </div>

      <div id="formRegister" style="display:none;">
        <label style="display:block;margin-bottom:6px;font-size:13px;color:#cbd5e1;font-weight:500;">学号 (必填)</label>
        <input type="text" id="r_user" class="input" placeholder="如: sxxxxxx" style="margin-bottom:14px;">
        <label style="display:block;margin-bottom:6px;font-size:13px;color:#cbd5e1;font-weight:500;">邮箱 (选填)</label>
        <input type="email" id="r_email" class="input" placeholder="可用于密码找回" style="margin-bottom:14px;">
        <label style="display:block;margin-bottom:6px;font-size:13px;color:#cbd5e1;font-weight:500;">设置密码</label>
        <input type="password" id="r_pass" class="input" placeholder="不少于6位" style="margin-bottom:14px;">
        <label style="display:block;margin-bottom:6px;font-size:13px;color:#cbd5e1;font-weight:500;">确认密码</label>
        <input type="password" id="r_pass2" class="input" placeholder="再次输入密码" style="margin-bottom:24px;" onkeydown="if(event.key==='Enter')doRegister()">
        <button class="btn-primary" onclick="doRegister()" style="width:100%;padding:12px;font-size:15px;display:flex;justify-content:center;align-items:center;gap:8px;"><i data-lucide="user-plus" style="width:18px;height:18px;"></i> 立即注册</button>
      </div>
    </div>
    
  </div>
</div>
        <p style="color:#d4d4d8;font-size:14px;line-height:1.7">
          统一登录、密钥发放与用量追踪。当前 Claude 模型已接入独立 Anthropic 网关，调用链路更直接稳定。
        </p>
      </div>
      <div class="login-marks">
        <div class="login-mark"><div class="k">默认额度</div><div class="v">5,000,000 Tokens</div></div>
        <div class="login-mark"><div class="k">协议兼容</div><div class="v">Anthropic / OpenAI</div></div>
        <div class="login-mark"><div class="k">主力模型</div><div class="v">Claude 4.6 系列</div></div>
        <div class="login-mark"><div class="k">网关内核</div><div class="v">Anthropic Relay · Direct</div></div>
      </div>
    </div>

    <div class="card auth-card">
      <div id="authTabs" style="display:flex;gap:4px;background:rgba(0,0,0,0.3);border-radius:12px;padding:4px;margin-bottom:22px">
        <button onclick="switchAuthTab('login')" id="tabLogin" class="tab active" style="flex:1;text-align:center">登录</button>
        <button onclick="switchAuthTab('register')" id="tabRegister" class="tab" style="flex:1;text-align:center">注册</button>
      </div>

      <div id="formLogin">
        <div style="display:flex;flex-direction:column;gap:14px">
          <div>
            <label style="font-size:12px;color:#bfdbfe;display:block;margin-bottom:8px;font-weight:600">User ID / 学号</label>
            <input id="loginSid" class="input" type="text" placeholder="Your Student ID">
          </div>
          <div>
            <label style="font-size:12px;color:#bfdbfe;display:block;margin-bottom:8px;font-weight:600">Password / 密码</label>
            <input id="loginPwd" class="input" type="password" placeholder="••••••••" onkeydown="if(event.key==='Enter')doLogin()">
          </div>
          <button class="btn-primary w-full" onclick="doLogin()" style="margin-top:8px;width:100%;padding:12px">登录进入工作台</button>
        </div>
      </div>

      <div id="formRegister" style="display:none">
        <div style="display:flex;flex-direction:column;gap:12px">
          <div>
            <label style="font-size:12px;color:#a1a1aa;display:block;margin-bottom:6px">学号</label>
            <input id="regSid" class="input" type="text" placeholder="请输入学号（4-20位）">
          </div>
          <div>
            <label style="font-size:12px;color:#a1a1aa;display:block;margin-bottom:6px">密码</label>
            <input id="regPwd" class="input" type="password" placeholder="至少6位">
          </div>
          <div>
            <label style="font-size:12px;color:#a1a1aa;display:block;margin-bottom:6px">确认密码</label>
            <input id="regPwd2" class="input" type="password" placeholder="再次输入密码" onkeydown="if(event.key==='Enter')doRegister()">
          </div>
          <button class="btn-primary" onclick="doRegister()" style="margin-top:4px;width:100%;padding:10px">创建账号</button>
        </div>
      </div>
      <p style="text-align:center;margin-top:14px;font-size:12px;color:#a1a1aa">注册即送 500万 tokens</p>
    </div>
  </div>
</div>

<!-- Dashboard Screen -->
<div id="dashScreen" style="display:none!important">
  <!-- Top Nav -->
  <nav style="padding:0 24px;height:56px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;">
    <div style="display:flex;align-items:center;gap:20px">
      <div style="display:flex;align-items:center;gap:8px; cursor: pointer" ondblclick="toggleAdminPanel()">
        <span style="font-size:20px"><i data-lucide="flower" style="width:18px;height:18px;"></i></span>
        <span style="font-weight:700;font-size:15px;letter-spacing:-.3px">WBU AI Club</span>
      </div>
      <div style="display:flex;gap:2px">
        <button class="tab active" id="navDash" onclick="showPage('dashboard')">概览</button>
        <button class="tab" id="navKeys" onclick="showPage('keys')">API Keys</button>
        <button class="tab" id="navLogs" onclick="showPage('logs')">使用日志</button>
        <button class="tab" id="navAdmin" onclick="showPage('admin')" style="display:none;background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.3);color:#a5b4fc">超管</button>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:12px">
      <span id="navUser" style="font-size:13px;color:#e4e4e7"></span>
      <button id="adminEntryBtn" onclick="openAdminLogin()" style="background:none;border:none;cursor:pointer;font-size:18px;opacity:0.35;padding:4px;transition:opacity .2s;display:none" title="管理员登录">🔐</button>
      <button class="btn-ghost" onclick="doLogout()" style="padding:6px 12px;font-size:13px">退出</button>
    </div>
  </nav>

  <!-- Admin Panel (Toggleable) -->
  <div id="adminPanel" class="glass-panel" style="display:none; position:fixed; top:70px; right:20px; width:300px; z-index:9000; padding:16px; border:1px solid #6366f1;">
    <div style="font-weight:bold; margin-bottom:12px; color:#c4b5fd">管理面板 (快捷)</div>
    <div style="font-size:12px; margin-bottom:8px">背景管理</div>
    <div id="bgList" style="max-height:150px; overflow-y:auto; margin-bottom:8px; display:flex; flex-direction:column; gap:4px"></div>
    <div style="display:flex; gap:4px; margin-bottom:8px">
       <input type="file" id="bgUpload" style="font-size:11px; width:180px">
       <button class="btn-primary" style="font-size:11px; padding:4px 8px" onclick="uploadBg()">上传</button>
    </div>
    <div style="margin-bottom:12px">
      <div style="font-size:12px; margin-bottom:6px; display:flex; justify-content:space-between">背景透明度 <span id="bgOpacityVal">100%</span></div>
      <input type="range" id="bgOpacitySlider" min="0" max="100" value="100" style="width:100%;accent-color:#c4b5fd"
        oninput="document.getElementById('bgOpacityVal').textContent=this.value+'%'; document.getElementById('bg-layer').style.opacity=this.value/100"
        onchange="saveBgOpacity(this.value)">
    </div>
    <button class="btn-ghost" style="width:100%; font-size:12px" onclick="toggleAdminPanel()">关闭面板</button>
  </div>

  <!-- Main Content -->
  <main style="max-width:1100px;margin:0 auto;padding:28px 24px">

    <!-- Dashboard Page -->
    <div id="pageDashboard">
      <h1 style="font-size:22px;font-weight:700;margin-bottom:24px;text-shadow:0 1px 2px rgba(0,0,0,0.5)">概览</h1>

      <!-- Stats Grid -->
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:28px">
        <div class="card" style="padding:20px">
          <div style="font-size:12px;color:#a1a1aa;margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px">剩余 Tokens</div>
          <div id="statRemaining" style="font-size:28px;font-weight:700;letter-spacing:-1px">—</div>
          <div id="statProgressBar" class="progress-bar" style="margin-top:12px"><div id="statFill" class="progress-fill" style="width:0%"></div></div>
          <div id="statUsedPct" style="font-size:12px;color:#d4d4d8;margin-top:6px"></div>
        </div>
        <div class="card" style="padding:20px">
          <div style="font-size:12px;color:#a1a1aa;margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px">累计消耗</div>
          <div id="statUsed" style="font-size:28px;font-weight:700;letter-spacing:-1px">—</div>
          <div style="font-size:12px;color:#d4d4d8;margin-top:6px">总计 <span id="statTotal">—</span></div>
        </div>
        <div class="card" style="padding:20px">
          <div style="font-size:12px;color:#a1a1aa;margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px">今日消耗</div>
          <div id="statToday" style="font-size:28px;font-weight:700;letter-spacing:-1px">—</div>
          <div style="font-size:12px;color:#d4d4d8;margin-top:6px">API 调用 <span id="statReqs">—</span> 次</div>
        </div>
        <div class="card" style="padding:20px;border-color:rgba(74,222,128,0.2)">
          <div style="font-size:12px;color:#a1a1aa;margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px">缓存节省 🧊</div>
          <div id="statCacheSaved" style="font-size:28px;font-weight:700;letter-spacing:-1px;color:#4ade80">—</div>
          <div style="font-size:12px;color:#d4d4d8;margin-top:6px">命中 <span id="statCacheRead" style="color:#86efac">—</span> · 写入 <span id="statCacheWrite">—</span></div>
        </div>
      </div>

      <div class="card" style="padding:18px;margin-bottom:20px">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
          <div>
            <div style="font-size:14px;font-weight:700;color:#fff">引擎能力状态</div>
            <div style="font-size:12px;color:#a1a1aa;margin-top:4px">当前工作台已接入独立 Anthropic 网关，凭据调度已启用，核心导航保持稳定。</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <span class="badge" style="background:rgba(16,185,129,0.15);color:#6ee7b7;border:1px solid rgba(16,185,129,0.35)">Cache: Enabled</span>
            <span class="badge" style="background:rgba(59,130,246,0.15);color:#93c5fd;border:1px solid rgba(59,130,246,0.35)">Admin UI: /admin</span>
            <span class="badge" style="background:rgba(245,158,11,0.15);color:#fcd34d;border:1px solid rgba(245,158,11,0.35)">Portal Relay: Active</span>
          </div>
        </div>
      </div>

      <!-- Check-in Section -->
      <div class="card" style="padding:24px;margin-bottom:28px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
          <div style="display:flex;align-items:center;gap:12px">
            <span style="font-size:24px"><i data-lucide="gift" style="width:28px;height:28px;color:#3b82f6;"></i></span>
            <div>
              <div style="font-size:16px;font-weight:700;color:#fff">每日签到</div>
              <div style="font-size:12px;color:#a1a1aa;margin-top:2px">Daily Check-in Rewards</div>
            </div>
          </div>
          <div id="checkinStatus" style="text-align:right">
            <div style="font-size:12px;color:#a1a1aa;margin-bottom:4px">今日状态</div>
            <div id="checkinStatusBadge" style="display:inline-flex;align-items:center;gap:4px;background:rgba(239,68,68,0.2);color:#fca5a5;border:1px solid rgba(239,68,68,0.3);border-radius:6px;padding:4px 10px;font-size:12px;font-weight:600">
              <span style="width:6px;height:6px;border-radius:50%;background:#fca5a5;display:inline-block"></span>
              未签到
            </div>
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
          <!-- Check-in Button -->
          <div style="display:flex;flex-direction:column;gap:12px">
            <button id="checkinBtn" onclick="performCheckin()" style="width:100%;padding:14px;font-size:15px;font-weight:600;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);border-radius:12px;color:#fff;cursor:pointer;transition:all .2s">
              ✨ 立即签到
            </button>
            <div id="checkinReward" style="text-align:center;padding:12px;background:rgba(20,10,25,0.5);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.15);border-radius:12px;display:none">
              <div style="font-size:12px;color:#a1a1aa;margin-bottom:4px">本次获得</div>
              <div id="rewardAmount" style="font-size:28px;font-weight:700;color:#4ade80;letter-spacing:-1px">—</div>
              <div style="font-size:11px;color:#a1a1aa;margin-top:2px">Tokens</div>
            </div>
          </div>

          <!-- Stats -->
          <div style="display:flex;flex-direction:column;gap:12px">
            <div style="padding:12px;background:rgba(20,10,25,0.5);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.15);border-radius:12px">
              <div style="font-size:12px;color:#a1a1aa;margin-bottom:4px">连续签到</div>
              <div id="consecutiveDays" style="font-size:24px;font-weight:700;color:#fff">0</div>
              <div style="font-size:11px;color:#a1a1aa">天</div>
            </div>
            <div style="padding:12px;background:rgba(20,10,25,0.5);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.15);border-radius:12px">
              <div style="font-size:12px;color:#a1a1aa;margin-bottom:4px">本月累计</div>
              <div id="monthlyTotal" style="font-size:24px;font-weight:700;color:#4ade80">0</div>
              <div style="font-size:11px;color:#a1a1aa">Tokens</div>
            </div>
          </div>
        </div>

        <!-- Check-in History Calendar -->
        <div style="margin-top:20px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.1)">
          <div style="font-size:12px;font-weight:600;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px">最近7天签到记录</div>
          <div id="checkinCalendar" style="display:grid;grid-template-columns:repeat(7,1fr);gap:8px">
            <!-- Calendar items will be inserted here -->
          </div>
        </div>

        <!-- Leaderboard Button -->
        <div style="margin-top:16px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.1)">
          <button onclick="showLeaderboard()" style="width:100%;padding:12px;font-size:14px;font-weight:500;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:10px;color:#d4d4d8;cursor:pointer;transition:all .2s;display:flex;align-items:center;justify-content:center;gap:8px">
            <svg style="width:16px;height:16px" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
            <span>看看大家今日签到情况～</span>
          </button>
        </div>
      </div>

      <!-- Model Breakdown -->
      <div class="card" style="padding:20px">
        <div style="font-size:12px;font-weight:600;margin-bottom:16px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px">模型用量</div>
        <div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap">
          <div style="position:relative;width:160px;height:160px;flex-shrink:0">
            <canvas id="modelChart"></canvas>
            <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none">
              <div style="font-size:11px;color:#a1a1aa">总消耗</div>
              <div id="modelChartTotal" style="font-size:15px;font-weight:700;color:#fff">—</div>
            </div>
          </div>
          <div id="modelBreakdown" style="flex:1;min-width:180px;display:flex;flex-direction:column;gap:10px">
            <div style="color:#e4e4e8;font-size:13px">暂无数据</div>
          </div>
        </div>
      </div>

      <!-- Allowed Models -->
      <div class="card" style="padding:20px;margin-top:16px">
        <div style="font-size:12px;font-weight:600;margin-bottom:14px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px">可用模型</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px">
          <div style="background:rgba(24,24,27,0.5);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:8px 14px">
            <div style="font-size:13px;font-weight:500">claude-haiku-4.5</div>
            <div style="font-size:11px;color:#a1a1aa;margin-top:2px">快速 · 轻量</div>
          </div>
          <div style="background:rgba(24,24,27,0.5);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:8px 14px">
            <div style="font-size:13px;font-weight:500">claude-sonnet-4.5</div>
            <div style="font-size:11px;color:#a1a1aa;margin-top:2px">均衡 · 推荐</div>
          </div>
          <div style="background:rgba(24,24,27,0.5);border:1px solid #6366f1;border-radius:8px;padding:8px 14px">
            <div style="font-size:13px;font-weight:500">claude-sonnet-4.6</div>
            <div style="font-size:11px;color:#6366f1;margin-top:2px">最新 · 带思考模式</div>
          </div>
          <div style="background:rgba(24,24,27,0.5);border:1px solid rgba(20,184,166,0.45);border-radius:8px;padding:8px 14px">
            <div style="font-size:13px;font-weight:500">kimi-k2.6</div>
            <div style="font-size:11px;color:#5eead4;margin-top:2px">长上下文 · 中文强</div>
          </div>
          <div style="background:rgba(24,24,27,0.5);border:1px solid rgba(59,130,246,0.45);border-radius:8px;padding:8px 14px">
            <div style="font-size:13px;font-weight:500">mimo-v2.5</div>
            <div style="font-size:11px;color:#93c5fd;margin-top:2px">通用主力 · 长上下文</div>
          </div>
          <div style="background:rgba(24,24,27,0.5);border:1px solid rgba(124,58,237,0.55);border-radius:8px;padding:8px 14px">
            <div style="font-size:13px;font-weight:500">mimo-v2.5-pro</div>
            <div style="font-size:11px;color:#c4b5fd;margin-top:2px">高配推理 · 稳定转发</div>
          </div>
        </div>
        <div style="margin-top:12px;font-size:12px;color:#d4d4d8">Claude 走 Anthropic 风格接口；Kimi 与 MIMO 走 OpenAI 兼容接口。</div>
      </div>
    </div>

    <!-- API Keys Page -->
    <div id="pageKeys" style="display:none">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
        <h1 style="font-size:22px;font-weight:700;text-shadow:0 1px 2px rgba(0,0,0,0.5)">API Keys</h1>
        <button class="btn-primary" onclick="openCreateKey()">+ 创建 Key</button>
      </div>

      <!-- Create Key Modal Inline -->
      <div id="createKeyForm" class="card" style="padding:20px;margin-bottom:20px;display:none">
        <div style="font-size:14px;font-weight:600;margin-bottom:14px">创建新 Key</div>
        <div style="display:flex;gap:12px;align-items:flex-end">
          <div style="flex:1">
            <label style="font-size:12px;color:#a1a1aa;display:block;margin-bottom:6px">Key 名称</label>
            <input id="newKeyName" class="input" placeholder="如：My Claude Key">
          </div>
          <div style="width:170px">
            <label style="font-size:12px;color:#a1a1aa;display:block;margin-bottom:6px">模型分组</label>
            <select id="newKeyGroup" class="input">
              <option value="claude">Claude</option>
              <option value="kimi">Kimi</option>
              <option value="mimo">MIMO</option>
            </select>
          </div>
          <button class="btn-primary" onclick="doCreateKey()" style="white-space:nowrap">创建</button>
          <button class="btn-ghost" onclick="closeCreateKey()">取消</button>
        </div>
      </div>

      <!-- New Key Display (shown once) -->
      <div id="newKeyDisplay" class="card" style="padding:20px;margin-bottom:20px;border-color:#166534;display:none">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
          <svg width="16" height="16" fill="none"><circle cx="8" cy="8" r="8" fill="#052e16"/><path d="M5 8l2 2 4-4" stroke="#4ade80" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span style="font-size:14px;font-weight:600;color:#4ade80">Key 创建成功 — 请立即保存，此后不再显示</span>
        </div>
        <div id="newKeyValue" class="secret-key"></div>
        <button class="btn-ghost" onclick="copyNewKey()" style="margin-top:10px;font-size:12px">复制</button>
      </div>

      <!-- Keys Table -->
      <div class="card" style="overflow:hidden">
        <table style="width:100%;border-collapse:collapse">
          <thead>
            <tr style="border-bottom:1px solid rgba(255,255,255,0.05)">
              <th style="text-align:left;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">名称</th>
              <th style="text-align:left;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">分组</th>
              <th style="text-align:left;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">Key (前缀)</th>
              <th style="text-align:left;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">已用 Tokens</th>
              <th style="text-align:left;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">创建时间</th>
              <th style="text-align:left;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">状态</th>
              <th style="padding:12px 16px"></th>
            </tr>
          </thead>
          <tbody id="keysTable">
            <tr><td colspan="7" style="text-align:center;padding:32px;color:#a1a1aa;font-size:14px">加载中...</td></tr>
          </tbody>
        </table>
      </div>

      <!-- Endpoint Info -->
      <div class="card" style="padding:20px;margin-top:16px">
        <div style="font-size:12px;font-weight:600;margin-bottom:12px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px">接入方式</div>
        <div style="font-size:13px;color:#e4e4e8;margin-bottom:10px">Claude 组使用 Anthropic 兼容接入；Kimi 和 MIMO 组使用 OpenAI 兼容接入。</div>
        <div style="display:flex;flex-direction:column;gap:8px">
          <div style="font-size:12px;color:#c4b5fd;margin-top:2px">Anthropic 客户端（Claude Code、Cherry Studio）</div>
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:12px;color:#a1a1aa;width:80px">Endpoint</span>
            <code id="endpointUrl" style="background:rgba(24,24,27,0.5);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:5px 10px;font-size:12px;color:#a3e635">https://portal.wbuai.me/v1</code>
          </div>
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:12px;color:#a1a1aa;width:80px">API Key</span>
            <code style="background:rgba(24,24,27,0.5);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:5px 10px;font-size:12px;color:#f4f4f5">kp-xxxxxxxx... (你的 Key)</code>
          </div>
          <div style="font-size:12px;color:#c4b5fd;margin-top:10px">OpenAI 兼容客户端（Kimi / MIMO / Codex 自定义端点）</div>
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:12px;color:#a1a1aa;width:80px">Base URL</span>
            <code style="background:rgba(24,24,27,0.5);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:5px 10px;font-size:12px;color:#a3e635">https://portal.wbuai.me/v1</code>
          </div>
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:12px;color:#a1a1aa;width:80px">Model</span>
            <code style="background:rgba(24,24,27,0.5);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:5px 10px;font-size:12px;color:#f4f4f5">kimi-k2.6 / mimo-v2.5 / mimo-v2.5-pro ...</code>
          </div>
        </div>
      </div>
    </div>

    <!-- Logs Page -->
    <div id="pageLogs" style="display:none">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
        <h1 style="font-size:22px;font-weight:700;text-shadow:0 1px 2px rgba(0,0,0,0.5)">使用日志</h1>
        <button class="btn-ghost" onclick="loadLogs()">↻ 刷新</button>
      </div>
      <div class="card" style="overflow:hidden">
        <table style="width:100%;border-collapse:collapse">
          <thead>
            <tr style="border-bottom:1px solid rgba(255,255,255,0.05)">
              <th style="text-align:left;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">时间</th>
              <th style="text-align:left;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">模型</th>
              <th style="text-align:right;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">输入</th>
              <th style="text-align:right;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">输出</th>
              <th style="text-align:right;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">合计</th>
              <th style="text-align:left;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">Key</th>
              <th style="text-align:left;padding:12px 16px;font-size:12px;color:#a1a1aa;font-weight:500;text-transform:uppercase;letter-spacing:.5px">状态</th>
            </tr>
          </thead>
          <tbody id="logsTable">
            <tr><td colspan="7" style="text-align:center;padding:32px;color:#a1a1aa;font-size:14px">加载中...</td></tr>
          </tbody>
        </table>
      </div>
      <div style="display:flex;justify-content:center;margin-top:16px;gap:8px" id="logsPagination"></div>
    </div>

    <!-- ── Super Admin Page ── -->
    <div id="pageAdmin" style="display:none">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
        <div style="display:flex;align-items:center;gap:12px">
          <h1 style="font-size:22px;font-weight:700;text-shadow:0 1px 2px rgba(0,0,0,0.5)">超管面板</h1>
          <span class="admin-badge">🔐 Admin</span>
        </div>
        <button onclick="doAdminLogout()" style="background:none;border:1px solid rgba(248,113,113,0.3);color:#f87171;border-radius:8px;padding:5px 12px;font-size:12px;cursor:pointer">退出管理员</button>
      </div>

      <!-- Admin Sub-tabs -->
      <div style="display:flex;gap:4px;background:rgba(0,0,0,0.35);border-radius:12px;padding:4px;margin-bottom:20px;overflow-x:auto;border:1px solid rgba(99,102,241,0.15)">
        <button onclick="showAdminTab('overview')" id="adminTabBtnOverview" class="admin-tab active" style="flex:1;text-align:center">概览</button>
        <button onclick="showAdminTab('users')" id="adminTabBtnUsers" class="admin-tab" style="flex:1;text-align:center">用户管理</button>
        <button onclick="showAdminTab('allkeys')" id="adminTabBtnAllkeys" class="admin-tab" style="flex:1;text-align:center">Key管理</button>
        <button onclick="showAdminTab('alllogs')" id="adminTabBtnAlllogs" class="admin-tab" style="flex:1;text-align:center">全部日志</button>
        <button onclick="showAdminTab('announcements')" id="adminTabBtnAnnouncements" class="admin-tab" style="flex:1;text-align:center">公告管理</button>
        <button onclick="showAdminTab('checkin')" id="adminTabBtnCheckin" class="admin-tab" style="flex:1;text-align:center">签到配置</button>
      </div>

      <!-- Overview Tab -->
      <div id="adminTabOverview">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:14px;margin-bottom:20px">
          <div class="admin-card" style="padding:18px">
            <div style="font-size:11px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">注册用户</div>
            <div id="adminStatUsers" style="font-size:26px;font-weight:700">—</div>
            <div style="font-size:11px;color:#71717a;margin-top:4px">活跃 <span id="adminStatActive">—</span></div>
          </div>
          <div class="admin-card" style="padding:18px">
            <div style="font-size:11px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">总消耗 Tokens</div>
            <div id="adminStatTokensUsed" style="font-size:26px;font-weight:700;letter-spacing:-1px">—</div>
            <div style="font-size:11px;color:#71717a;margin-top:4px">今日 <span id="adminStatTodayTokens">—</span></div>
          </div>
          <div class="admin-card" style="padding:18px">
            <div style="font-size:11px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">总请求数</div>
            <div id="adminStatRequests" style="font-size:26px;font-weight:700">—</div>
            <div style="font-size:11px;color:#71717a;margin-top:4px">今日 <span id="adminStatToday">—</span></div>
          </div>
          <div class="admin-card" style="padding:18px">
            <div style="font-size:11px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">活跃 Keys</div>
            <div id="adminStatActiveKeys" style="font-size:26px;font-weight:700">—</div>
            <div style="font-size:11px;color:#71717a;margin-top:4px">全局</div>
          </div>
        </div>
        <div class="admin-card" style="padding:20px">
          <div style="font-size:12px;font-weight:600;margin-bottom:14px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px">全局模型用量</div>
          <div id="adminModelBreakdown" style="display:flex;flex-direction:column;gap:10px">
            <div style="color:#71717a;font-size:13px">加载中...</div>
          </div>
        </div>
      </div>

      <!-- Users Tab -->
      <div id="adminTabUsers" style="display:none">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
          <div style="font-size:14px;font-weight:600">所有用户</div>
          <div style="display:flex;gap:8px">
            <button class="btn-indigo" onclick="openBatchAddTokenModal()" style="font-size:12px">💰 批量加 Token</button>
            <button class="btn-ghost" onclick="loadAdminUsers()" style="font-size:12px">↻ 刷新</button>
          </div>
        </div>
        <div class="admin-card" style="overflow:hidden">
          <div style="overflow-x:auto">
            <table style="width:100%;border-collapse:collapse;min-width:680px">
              <thead>
                <tr style="border-bottom:1px solid rgba(99,102,241,0.15)">
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">学号</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">注册时间</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase;min-width:160px">配额用量</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">已用</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">状态</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">操作</th>
                </tr>
              </thead>
              <tbody id="adminUsersTable">
                <tr><td colspan="6" style="text-align:center;padding:32px;color:#a1a1aa">加载中...</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- All Keys Tab -->
      <div id="adminTabAllkeys" style="display:none">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
          <div style="font-size:14px;font-weight:600">所有 API Keys</div>
          <button class="btn-ghost" onclick="loadAdminKeys()" style="font-size:12px">↻ 刷新</button>
        </div>
        <div class="admin-card" style="overflow:hidden">
          <div style="overflow-x:auto">
            <table style="width:100%;border-collapse:collapse;min-width:600px">
              <thead>
                <tr style="border-bottom:1px solid rgba(99,102,241,0.15)">
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">用户</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">名称</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">Key 前缀</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">已用</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">创建时间</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">状态</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">操作</th>
                </tr>
              </thead>
              <tbody id="adminKeysTable">
                <tr><td colspan="7" style="text-align:center;padding:32px;color:#a1a1aa">加载中...</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- All Logs Tab -->
      <div id="adminTabAlllogs" style="display:none">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
          <div style="font-size:14px;font-weight:600">全部使用日志</div>
          <button class="btn-ghost" onclick="loadAdminAllLogs()" style="font-size:12px">↻ 刷新</button>
        </div>
        <div class="admin-card" style="overflow:hidden">
          <div style="overflow-x:auto">
            <table style="width:100%;border-collapse:collapse;min-width:640px">
              <thead>
                <tr style="border-bottom:1px solid rgba(99,102,241,0.15)">
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">时间</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">用户</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">模型</th>
                  <th style="text-align:right;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">输入</th>
                  <th style="text-align:right;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">输出</th>
                  <th style="text-align:right;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">合计</th>
                  <th style="text-align:left;padding:10px 12px;font-size:11px;color:#a1a1aa;font-weight:500;text-transform:uppercase">Key</th>
                </tr>
              </thead>
              <tbody id="adminAllLogsTable">
                <tr><td colspan="7" style="text-align:center;padding:32px;color:#a1a1aa">加载中...</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div style="display:flex;justify-content:center;margin-top:16px;gap:8px" id="adminAllLogsPagination"></div>
      </div>

      <!-- Announcements Tab -->
      <div id="adminTabAnnouncements" style="display:none">
        <div class="admin-card" style="padding:20px;margin-bottom:16px">
          <div style="font-size:14px;font-weight:600;margin-bottom:4px;color:#fff">发送公告</div>
          <div style="font-size:12px;color:#a1a1aa;margin-bottom:14px">将以管理员弹幕形式广播给所有在线用户，并保存至公告历史</div>
          <div style="display:flex;gap:10px;margin-bottom:10px">
            <input id="adminAnnouncementContent" class="input" placeholder="输入公告内容（最多100字）..." maxlength="100" style="flex:1;border-color:rgba(99,102,241,0.3)" onkeydown="if(event.key==='Enter')adminSendAnnouncement()">
            <button class="btn-indigo" onclick="adminSendAnnouncement()" style="white-space:nowrap">📢 发送</button>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <input type="checkbox" id="adminAnnouncementPersistent" style="width:16px;height:16px;cursor:pointer">
            <label for="adminAnnouncementPersistent" style="font-size:12px;color:#a1a1aa;cursor:pointer">🔄 长时间驻留（反复播放，持续显示）</label>
          </div>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <div style="font-size:14px;font-weight:600">历史公告</div>
          <button class="btn-ghost" onclick="loadAdminAnnouncements()" style="font-size:12px">↻ 刷新</button>
        </div>
        <div id="adminAnnouncementsList" style="display:flex;flex-direction:column;gap:8px">
          <div style="text-align:center;padding:24px;color:#a1a1aa;font-size:13px">加载中...</div>
        </div>
      </div>

      <!-- Check-in Configuration Tab -->
      <div id="adminTabCheckin" style="display:none">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">
          <!-- Configuration Form -->
          <div class="card" style="padding:20px">
            <div style="font-size:14px;font-weight:600;margin-bottom:16px;color:#fff">签到奖励配置</div>
            <div style="display:flex;flex-direction:column;gap:14px">
              <div>
                <label style="font-size:12px;color:#a1a1aa;display:block;margin-bottom:6px;font-weight:500">最小奖励 (Tokens)</label>
                <input id="adminCheckinMin" type="number" class="input" placeholder="1000" min="1">
              </div>
              <div>
                <label style="font-size:12px;color:#a1a1aa;display:block;margin-bottom:6px;font-weight:500">最大奖励 (Tokens)</label>
                <input id="adminCheckinMax" type="number" class="input" placeholder="5000" min="1">
              </div>
              <button class="btn-primary" onclick="saveCheckinConfig()" style="width:100%;padding:10px;margin-top:8px">💾 保存配置</button>
            </div>
          </div>

          <!-- Preview -->
          <div class="card" style="padding:20px">
            <div style="font-size:14px;font-weight:600;margin-bottom:16px;color:#fff">奖励范围预览</div>
            <div style="display:flex;flex-direction:column;gap:12px">
              <div style="padding:12px;background:rgba(20,10,25,0.5);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.15);border-radius:12px">
                <div style="font-size:12px;color:#a1a1aa;margin-bottom:4px">最小奖励</div>
                <div id="previewMin" style="font-size:24px;font-weight:700;color:#bfdbfe">—</div>
              </div>
              <div style="padding:12px;background:rgba(20,10,25,0.5);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.15);border-radius:12px">
                <div style="font-size:12px;color:#a1a1aa;margin-bottom:4px">最大奖励</div>
                <div id="previewMax" style="font-size:24px;font-weight:700;color:#bfdbfe">—</div>
              </div>
              <div style="padding:12px;background:rgba(20,10,25,0.5);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.15);border-radius:12px">
                <div style="font-size:12px;color:#a1a1aa;margin-bottom:4px">平均奖励</div>
                <div id="previewAvg" style="font-size:24px;font-weight:700;color:#bfdbfe">—</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Statistics -->
        <div class="card" style="padding:20px">
          <div style="font-size:14px;font-weight:600;margin-bottom:16px;color:#fff">签到统计</div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px">
            <div style="padding:12px;background:rgba(20,10,25,0.5);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.15);border-radius:12px">
              <div style="font-size:11px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">今日签到</div>
              <div id="statCheckinToday" style="font-size:22px;font-weight:700;color:#bfdbfe">—</div>
            </div>
            <div style="padding:12px;background:rgba(20,10,25,0.5);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.15);border-radius:12px">
              <div style="font-size:11px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">今日奖励</div>
              <div id="statTokensToday" style="font-size:22px;font-weight:700;color:#bfdbfe">—</div>
            </div>
            <div style="padding:12px;background:rgba(20,10,25,0.5);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.15);border-radius:12px">
              <div style="font-size:11px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">总签到数</div>
              <div id="statCheckinTotal" style="font-size:22px;font-weight:700;color:#bfdbfe">—</div>
            </div>
            <div style="padding:12px;background:rgba(20,10,25,0.5);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.15);border-radius:12px">
              <div style="font-size:11px;color:#a1a1aa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">总奖励</div>
              <div id="statTokensTotal" style="font-size:22px;font-weight:700;color:#bfdbfe">—</div>
            </div>
          </div>
          <button class="btn-primary" onclick="loadCheckinStats()" style="width:100%;font-size:12px;padding:8px">↻ 刷新统计</button>
        </div>
      </div>
    </div>

  </main>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let currentUser = null;
let logsOffset = 0;
let _newKeyValue = '';
let ws = null;
const FIXED_IP = '43.136.72.125';

// ── Init ───────────────────────────────────────────────────────────────────
async function init() { lucide.createIcons();
  // Load background
  loadBackground();
  
  try {
    const r = await api('GET', '/api/auth/me');
    if (r.ok) {
      currentUser = r;
      showDashboard();
      connectWs();
      return;
    }
  } catch(e) {}
  showLogin();
}

async function loadBackground() {
  try {
    const r = await api('GET', '/api/bg/active');
    const layer = document.getElementById('bg-layer');
    if (r.url) {
      layer.style.backgroundImage = `url('${r.url}')`;
      layer.style.opacity = r.opacity !== undefined ? r.opacity : 1.0;
      // Sync slider if admin panel is open
      const slider = document.getElementById('bgOpacitySlider');
      if (slider) {
        slider.value = Math.round((r.opacity !== undefined ? r.opacity : 1.0) * 100);
        document.getElementById('bgOpacityVal').textContent = slider.value + '%';
      }
    }
  } catch(e) {}
}

function showLogin() {
  document.getElementById('loginScreen').style.removeProperty('display');
  document.getElementById('dashScreen').style.setProperty('display','none','important');
  const danmakuForm = document.getElementById('danmakuForm');
  if (danmakuForm) danmakuForm.style.display = 'none';
}
function showDashboard() {
  document.getElementById('loginScreen').style.setProperty('display','none','important');
  document.getElementById('dashScreen').style.removeProperty('display');
  const danmakuForm = document.getElementById('danmakuForm');
  if (danmakuForm) danmakuForm.style.display = 'flex';
  document.getElementById('navUser').textContent = currentUser.student_id;
  document.getElementById('endpointUrl').textContent = 'https://portal.wbuai.me/v1';
  // Show admin entry button for all users (admin login is separate)
  document.getElementById('adminEntryBtn').style.display = '';
  // Check if already logged in as admin
  checkAdminSession();
  showPage('dashboard');
  loadDashboard();
  
  // Auto refresh stats every 10 seconds
  if (!window.dashInterval) {
      window.dashInterval = setInterval(() => {
          if (document.getElementById('pageDashboard').style.display !== 'none') {
              loadDashboard();
          }
      }, 10000);
  }
  
  // Show welcome modal if not seen this session/ever? Let's show it on login for now.
  const seen = localStorage.getItem('seenWelcome_' + currentUser.student_id);
  // Optional: remove 'if (!seen)' to show every time
  if (!seen) {
    showWelcome();
  }
}

function showWelcome() {
  const overlay = document.getElementById('welcomeOverlay');
  overlay.style.display = 'flex';
}
function closeWelcome() {
  document.getElementById('welcomeOverlay').style.display = 'none';
  if (currentUser) {
    localStorage.setItem('seenWelcome_' + currentUser.student_id, '1');
  }
}

// ── WebSocket & Danmaku ────────────────────────────────────────────────────
function connectWs() {
    if (ws) return;
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws/danmaku`);
    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === 'announcement') {
            const banner = document.getElementById('announcementBanner');
            document.getElementById('announcementBannerText').textContent = data.text;
            banner.style.display = '';
            setTimeout(() => { banner.style.display = 'none'; }, 15000);
        }
        renderDanmaku(data);
    };
    ws.onclose = function() {
        ws = null;
        setTimeout(connectWs, 3000); // Reconnect
    }
}

function sendDanmaku() {
    const input = document.getElementById('danmakuInput');
    const msg = input.value.trim();
    if (!msg) return;
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(msg);
        input.value = '';
    } else {
        toast('连接已断开', 'error');
    }
}

const MAX_DANMAKU = 20;
const activeDanmaku = [];
let persistentDanmaku = null; // 驻留弹幕

function renderDanmaku(data) {
    const container = document.getElementById('danmaku-layer');

    // 如果是驻留公告，先清除旧的驻留弹幕
    if (data.persistent) {
        if (persistentDanmaku) {
            persistentDanmaku.remove();
        }
        // 创建驻留弹幕（反复播放）
        createPersistentDanmaku(container, data);
        return;
    }

    // Check limit on screen (simple heuristic)
    if (container.childElementCount >= MAX_DANMAKU) {
       // Ideally remove oldest, but CSS transition handles removal.
       // We can force remove the first one if too many
       container.firstElementChild.remove();
    }

    const div = document.createElement('div');
    div.className = 'danmaku-item';
    if (data.style === 'admin') {
        div.classList.add('danmaku-admin');
        div.style.zIndex = 10001;
    }
    div.textContent = data.text;

    // Position
    const top = 10 + Math.random() * 60; // Top 10% to 70% to avoid form
    div.style.top = top + '%';
    div.style.left = '100%';

    container.appendChild(div);

    // Animate
    // Randomize duration between 10s and 20s for slower, more readable scrolling
    // If it's history (reloaded), maybe we want to stagger them?
    const duration = 15000 + Math.random() * 5000;
    div.style.transition = `transform ${duration}ms linear`;

    // Force reflow
    div.getBoundingClientRect();

    div.style.transform = 'translateX(-120vw)'; // Move across screen

    // Remove after animation completes
    setTimeout(() => {
        div.remove();
    }, duration + 100);
}

function createPersistentDanmaku(container, data) {
    const div = document.createElement('div');
    div.className = 'danmaku-item danmaku-admin';
    div.style.zIndex = 10002;
    div.textContent = data.text;
    div.style.top = '30%'; // 固定在中上位置
    div.style.left = '100%';

    container.appendChild(div);
    persistentDanmaku = div;

    // 反复播放动画
    function animatePersistent() {
        div.style.transition = 'none';
        div.style.transform = 'translateX(0)';
        div.style.left = '100%';

        // Force reflow
        div.getBoundingClientRect();

        const duration = 20000; // 20秒横穿
        div.style.transition = `transform ${duration}ms linear`;
        div.style.transform = 'translateX(-120vw)';

        // 动画结束后重新开始
        setTimeout(() => {
            if (persistentDanmaku === div) {
                animatePersistent();
            }
        }, duration);
    }

    animatePersistent();
}

// ── Admin Panel ────────────────────────────────────────────────────────────
function toggleAdminPanel() {
    const p = document.getElementById('adminPanel');
    if (p.style.display === 'none') {
        p.style.display = 'block';
        loadAdminBackgrounds();
    } else {
        p.style.display = 'none';
    }
}

async function loadAdminBackgrounds() {
    const list = document.getElementById('bgList');
    list.innerHTML = 'Loading...';
    try {
        const r = await api('GET', '/api/admin/backgrounds');
        if (r.files) {
            list.innerHTML = r.files.map(f => `
                <div style="display:flex;justify-content:space-between;align-items:center;background:rgba(0,0,0,0.3);padding:4px;border-radius:4px;font-size:11px">
                    <span>${f}</span>
                    <button class="btn-ghost" style="padding:2px 6px;font-size:10px" onclick="setBg('${f}')">Activate</button>
                </div>
            `).join('');
        } else {
            list.innerHTML = 'No files';
        }
    } catch(e) {
        list.innerHTML = 'Error loading list';
    }
}

async function uploadBg() {
    const input = document.getElementById('bgUpload');
    if (!input.files[0]) return;
    const formData = new FormData();
    formData.append('file', input.files[0]);
    
    try {
        const r = await fetch('/api/admin/backgrounds/upload', {
            method: 'POST',
            body: formData
        });
        const res = await r.json();
        if (res.ok) {
            toast('上传成功', 'success');
            loadAdminBackgrounds();
        } else {
            toast('上传失败', 'error');
        }
    } catch(e) {
        toast('Error', 'error');
    }
}

async function setBg(filename) {
    const r = await api('POST', '/api/admin/backgrounds/active', {filename});
    if (r.ok) {
        toast('Background updated', 'success');
        loadBackground();
    } else {
        toast('Failed to set', 'error');
    }
}

async function saveBgOpacity(val) {
    const opacity = val / 100;
    await api('POST', '/api/admin/backgrounds/opacity', {opacity});
}

// ── Auth tab ───────────────────────────────────────────────────────────────
function switchAuthTab(tab) {
  document.getElementById('formLogin').style.display = tab==='login'?'':'none';
  document.getElementById('formRegister').style.display = tab==='register'?'':'none';
  document.getElementById('tabLogin').className = 'tab' + (tab==='login'?' active':'');
  document.getElementById('tabRegister').className = 'tab' + (tab==='register'?' active':'');
}

async function doLogin() {
  const sid = document.getElementById('loginSid').value.trim();
  const pwd = document.getElementById('loginPwd').value;
  if (!sid || !pwd) { toast('请填写学号和密码','error'); return; }
  const r = await api('POST', '/api/auth/login', {student_id:sid, password:pwd});
  if (r.ok) { currentUser = {student_id: r.student_id}; const me = await api('GET','/api/auth/me'); currentUser = me; showDashboard(); connectWs(); }
  else toast(r.error || '登录失败','error');
}

async function doRegister() {
  const sid = document.getElementById('regSid').value.trim();
  const pwd = document.getElementById('regPwd').value;
  const pwd2 = document.getElementById('regPwd2').value;
  if (pwd !== pwd2) { toast('两次密码不一致','error'); return; }
  const r = await api('POST', '/api/auth/register', {student_id:sid, password:pwd});
  if (r.ok) { toast('注册成功！请登录','success'); switchAuthTab('login'); document.getElementById('loginSid').value=sid; }
  else toast(r.error || '注册失败','error');
}

async function doLogout() {
  await api('POST', '/api/auth/logout');
  currentUser = null;
  if (ws) ws.close();
  showLogin();
}

// ── Navigation ─────────────────────────────────────────────────────────────
function showPage(page) {
  ['dashboard','keys','logs','admin'].forEach(p => {
    const pageEl = document.getElementById('page'+p.charAt(0).toUpperCase()+p.slice(1));
    if (pageEl) pageEl.style.display = p===page?'':'none';
    const navId = p==='dashboard'?'navDash':(p==='keys'?'navKeys':(p==='logs'?'navLogs':'navAdmin'));
    const nav = document.getElementById(navId);
    if (nav) nav.className = 'tab' + (p===page?' active':'') + (p==='admin'?' ':' ');
    if (p==='admin' && nav) {
      nav.className = p===page
        ? 'tab active'
        : 'tab';
      nav.style.background = p===page ? 'rgba(99,102,241,0.3)' : 'rgba(99,102,241,0.15)';
      nav.style.border = '1px solid rgba(99,102,241,0.3)';
      nav.style.color = '#a5b4fc';
    }
  });
  if (page==='keys') loadKeys();
  if (page==='logs') { logsOffset=0; loadLogs(); }
  if (page==='admin') { showAdminTab('overview'); loadAdminStats(); }
}

// ── Dashboard ──────────────────────────────────────────────────────────────
async function loadDashboard() {
  const s = await api('GET', '/api/dashboard');
  document.getElementById('statRemaining').textContent = fmtNum(s.remaining_tokens);
  document.getElementById('statUsed').textContent = fmtNum(s.used_tokens);
  document.getElementById('statTotal').textContent = fmtNum(s.total_tokens);
  document.getElementById('statToday').textContent = fmtNum(s.today_tokens);
  document.getElementById('statReqs').textContent = s.request_count.toLocaleString();
  const pct = s.total_tokens > 0 ? ((s.used_tokens / s.total_tokens)*100).toFixed(1) : 0;
  document.getElementById('statFill').style.width = pct+'%';
  document.getElementById('statUsedPct').textContent = `已用 ${pct}%`;

  // Cache stats
  const cacheRead = s.cache_read_tokens || 0;
  const cacheWrite = s.cache_creation_tokens || 0;
  const cacheSaved = s.cache_saved_tokens || 0;
  document.getElementById('statCacheSaved').textContent = cacheSaved > 0 ? fmtNum(cacheSaved) : '0';
  document.getElementById('statCacheRead').textContent = fmtNum(cacheRead);
  document.getElementById('statCacheWrite').textContent = fmtNum(cacheWrite);

  const mb = document.getElementById('modelBreakdown');
  const CHART_COLORS = ['#6366f1','#a78bfa','#34d399','#f472b6','#fb923c','#38bdf8'];
  if (s.model_breakdown && s.model_breakdown.length > 0) {
    mb.innerHTML = s.model_breakdown.map((m, i) => {
      const color = CHART_COLORS[i % CHART_COLORS.length];
      return `<div style="display:flex;align-items:center;gap:10px">
        <span style="width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0"></span>
        <span style="font-size:12px;font-family:monospace;color:#a1a1aa;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${m.model}</span>
        <span style="font-size:12px;color:#d4d4d8;flex-shrink:0">${fmtNum(m.tokens)}</span>
        <span style="font-size:11px;color:#71717a;flex-shrink:0">${m.reqs}次</span>
      </div>`;
    }).join('');
    const canvas = document.getElementById('modelChart');
    if (canvas) {
      if (window._modelChartInst) { window._modelChartInst.destroy(); }
      window._modelChartInst = new Chart(canvas, {
        type: 'doughnut',
        data: {
          labels: s.model_breakdown.map(m => m.model.replace('claude-','')),
          datasets: [{ data: s.model_breakdown.map(m => m.tokens),
            backgroundColor: CHART_COLORS.slice(0, s.model_breakdown.length),
            borderWidth: 2, borderColor: 'rgba(0,0,0,0.3)', hoverOffset: 6 }]
        },
        options: {
          cutout: '70%', responsive: true, maintainAspectRatio: true,
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ` ${fmtNum(ctx.raw)} tokens` } } },
          animation: { animateRotate: true, duration: 800 }
        }
      });
      document.getElementById('modelChartTotal').textContent = fmtNum(s.used_tokens);
    }
  } else {
    mb.innerHTML = '<div style="color:#e4e4e8;font-size:13px">暂无数据</div>';
    const canvas = document.getElementById('modelChart');
    if (canvas && window._modelChartInst) { window._modelChartInst.destroy(); window._modelChartInst = null; }
  }

  // Load check-in status and history
  loadCheckinStatus();
  loadCheckinHistory();
}

// ── API Keys ───────────────────────────────────────────────────────────────
async function loadKeys() {
  const r = await api('GET', '/api/keys');
  const tbody = document.getElementById('keysTable');
  if (!r.keys || r.keys.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:#a1a1aa;font-size:14px">还没有 Key，点击右上角创建</td></tr>';
    return;
  }
  tbody.innerHTML = r.keys.map(k => `
    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);transition:background .1s" onmouseover="this.style.background='rgba(255,255,255,0.05)'" onmouseout="this.style.background=''">
      <td style="padding:12px 16px;font-size:14px">${esc(k.name)}</td>
      <td style="padding:12px 16px"><span class="badge" style="background:${keyGroupColor(k.group_name)};color:#fff;border:none">${esc(keyGroupLabel(k.group_name))}</span></td>
      <td style="padding:12px 16px"><code class="mono" style="color:#a3e635">${esc(k.key_prefix)}</code></td>
      <td style="padding:12px 16px;font-size:13px;color:#a1a1aa">${fmtNum(k.used_tokens)}</td>
      <td style="padding:12px 16px;font-size:13px;color:#e4e4e7">${k.created_at||''}</td>
      <td style="padding:12px 16px"><span class="badge ${k.is_active?'badge-green':'badge-red'}">${k.is_active?'● 启用':'○ 停用'}</span></td>
      <td style="padding:12px 16px;text-align:right"><button class="btn-danger" onclick="doDeleteKey(${k.id})">删除</button></td>
    </tr>`).join('');
}

function openCreateKey() {
  document.getElementById('createKeyForm').style.display = '';
  document.getElementById('newKeyDisplay').style.display = 'none';
  document.getElementById('newKeyName').focus();
}
function closeCreateKey() { document.getElementById('createKeyForm').style.display = 'none'; }

async function doCreateKey() {
  const name = document.getElementById('newKeyName').value.trim() || 'My Key';
  const group_name = document.getElementById('newKeyGroup').value || 'claude';
  const r = await api('POST', '/api/keys', {name, group_name});
  if (r.ok) {
    _newKeyValue = r.key;
    document.getElementById('newKeyValue').textContent = r.key;
    document.getElementById('newKeyDisplay').style.display = '';
    closeCreateKey();
    loadKeys();
    toast('Key 创建成功','success');
  } else toast(r.error || '创建失败','error');
}

function copyNewKey() {
  navigator.clipboard.writeText(_newKeyValue).then(()=>toast('已复制到剪贴板','success'));
}

function keyGroupLabel(group) {
  if (group === 'kimi') return 'Kimi';
  if (group === 'mimo') return 'MIMO';
  return 'Claude';
}

function keyGroupColor(group) {
  if (group === 'kimi') return 'linear-gradient(135deg,#0f766e,#14b8a6)';
  if (group === 'mimo') return 'linear-gradient(135deg,#7c3aed,#2563eb)';
  return 'linear-gradient(135deg,#475569,#0f172a)';
}

async function doDeleteKey(id) {
  if (!confirm('确定要删除这个 Key 吗？')) return;
  const r = await api('DELETE', `/api/keys/${id}`);
  if (r.ok) { toast('已删除','success'); loadKeys(); }
  else toast('删除失败','error');
}

// ── Logs ───────────────────────────────────────────────────────────────────
async function loadLogs() {
  const r = await api('GET', `/api/logs?limit=50&offset=${logsOffset}`);
  const tbody = document.getElementById('logsTable');
  if (!r.logs || r.logs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:#a1a1aa;font-size:14px">暂无日志</td></tr>';
    return;
  }
  tbody.innerHTML = r.logs.map(l => `
    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);font-size:13px">
      <td style="padding:10px 16px;color:#a1a1aa;white-space:nowrap">${l.timestamp||''}</td>
      <td style="padding:10px 16px"><code class="mono">${esc(l.model||'')}</code></td>
      <td style="padding:10px 16px;text-align:right;color:#a1a1aa">${(l.input_tokens||0).toLocaleString()}</td>
      <td style="padding:10px 16px;text-align:right;color:#a1a1aa">${(l.output_tokens||0).toLocaleString()}</td>
      <td style="padding:10px 16px;text-align:right;font-weight:600">${(l.total_tokens||0).toLocaleString()}</td>
      <td style="padding:10px 16px"><code style="font-size:11px;color:#d4d4d8">${esc(l.key_prefix||'')}</code></td>
      <td style="padding:10px 16px"><span class="badge ${l.status==='success'?'badge-green':'badge-red'}">${l.status}</span></td>
    </tr>`).join('');
  // pagination
  const pg = document.getElementById('logsPagination');
  pg.innerHTML = '';
  if (logsOffset > 0) { const b=document.createElement('button'); b.className='btn-ghost'; b.textContent='← 上一页'; b.onclick=()=>{logsOffset=Math.max(0,logsOffset-50);loadLogs();}; pg.appendChild(b); }
  if (r.logs.length >= 50) { const b=document.createElement('button'); b.className='btn-ghost'; b.textContent='下一页 →'; b.onclick=()=>{logsOffset+=50;loadLogs();}; pg.appendChild(b); }
}

// ── Helpers ────────────────────────────────────────────────────────────────
async function api(method, url, body) {
  const opts = {method, headers:{'Content-Type':'application/json'}};
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  return r.json();
}
function fmtNum(n) {
  if (n >= 1e6) return (n/1e6).toFixed(2) + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(1) + 'K';
  return (n||0).toLocaleString();
}
function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function toast(msg, type='success') {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = `toast toast-${type} show`;
  setTimeout(()=>{t.className='toast';},3000);
}

// ── Super Admin ────────────────────────────────────────────────────────────
let adminLogsOffset = 0;

async function checkAdminSession() {
  try {
    const r = await api('GET', '/api/admin/auth/me');
    if (r.ok) {
      document.getElementById('navAdmin').style.display = '';
    }
  } catch(e) {}
}

function openAdminLogin() {
  document.getElementById('adminLoginModal').style.display = 'flex';
  document.getElementById('adminLoginUser').focus();
}
function closeAdminLogin() {
  document.getElementById('adminLoginModal').style.display = 'none';
  document.getElementById('adminLoginUser').value = '';
  document.getElementById('adminLoginPass').value = '';
}

async function doAdminLogin() {
  const username = document.getElementById('adminLoginUser').value.trim();
  const password = document.getElementById('adminLoginPass').value;
  if (!username || !password) { toast('请输入用户名和密码', 'error'); return; }
  const r = await api('POST', '/api/admin/auth/login', {username, password});
  if (r.ok) {
    closeAdminLogin();
    toast('管理员登录成功', 'success');
    document.getElementById('navAdmin').style.display = '';
    showPage('admin');
  } else {
    toast(r.error || '登录失败', 'error');
  }
}

async function doAdminLogout() {
  await api('POST', '/api/admin/auth/logout');
  document.getElementById('navAdmin').style.display = 'none';
  showPage('dashboard');
  toast('已退出管理员', 'success');
}

function showAdminTab(tab) {
  ['overview','users','allkeys','alllogs','announcements','checkin'].forEach(t => {
    const el = document.getElementById('adminTab'+t.charAt(0).toUpperCase()+t.slice(1));
    if (el) el.style.display = t===tab?'':'none';
    const btn = document.getElementById('adminTabBtn'+t.charAt(0).toUpperCase()+t.slice(1));
    if (btn) btn.className = 'admin-tab' + (t===tab?' active':'');
  });
  if (tab==='users') loadAdminUsers();
  if (tab==='allkeys') loadAdminKeys();
  if (tab==='alllogs') { adminLogsOffset=0; loadAdminAllLogs(); }
  if (tab==='announcements') loadAdminAnnouncements();
  if (tab==='checkin') { loadCheckinConfig(); loadCheckinStats(); }
}

async function loadAdminStats() {
  try {
    const s = await api('GET', '/api/admin/full-stats');
    document.getElementById('adminStatUsers').textContent = s.total_users ?? '—';
    document.getElementById('adminStatActive').textContent = s.active_users ?? '—';
    document.getElementById('adminStatTokensUsed').textContent = fmtNum(s.total_tokens_used || 0);
    document.getElementById('adminStatTodayTokens').textContent = fmtNum(s.today_tokens || 0);
    document.getElementById('adminStatRequests').textContent = (s.total_requests || 0).toLocaleString();
    document.getElementById('adminStatToday').textContent = (s.today_requests || 0).toLocaleString();
    document.getElementById('adminStatActiveKeys').textContent = s.active_keys ?? '—';
    const mb = document.getElementById('adminModelBreakdown');
    if (s.model_breakdown && s.model_breakdown.length > 0) {
      const totalTok = s.total_tokens_used || 1;
      mb.innerHTML = s.model_breakdown.map(m => {
        const pct = ((m.tokens / totalTok)*100).toFixed(0);
        return `<div style="display:flex;align-items:center;gap:12px">
          <span style="font-size:12px;font-family:monospace;color:#a1a1aa;min-width:220px">${esc(m.model)}</span>
          <div class="progress-bar" style="flex:1"><div class="progress-fill" style="width:${pct}%;background:linear-gradient(90deg,#6366f1,#a78bfa)"></div></div>
          <span style="font-size:12px;color:#71717a;min-width:70px;text-align:right">${fmtNum(m.tokens)}</span>
          <span style="font-size:11px;color:#d4d4d8;min-width:30px">${m.reqs}次</span>
        </div>`;
      }).join('');
    } else {
      mb.innerHTML = '<div style="color:#71717a;font-size:13px">暂无数据</div>';
    }
  } catch(e) { toast('加载统计失败，请确认管理员已登录', 'error'); }
}

async function loadAdminUsers() {
  const tbody = document.getElementById('adminUsersTable');
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;color:#a1a1aa">加载中...</td></tr>';
  try {
    const r = await api('GET', '/api/admin/users');
    if (!r.users || r.users.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:32px;color:#a1a1aa">暂无用户</td></tr>';
      return;
    }
    tbody.innerHTML = r.users.map(u => {
      const pct = u.total_tokens > 0 ? ((u.used_tokens / u.total_tokens)*100).toFixed(1) : 0;
      const remaining = u.total_tokens - u.used_tokens;
      return `<tr style="border-bottom:1px solid rgba(99,102,241,0.08);transition:background .1s" onmouseover="this.style.background='rgba(99,102,241,0.05)'" onmouseout="this.style.background=''">
        <td style="padding:10px 12px;font-size:13px;font-weight:600">${esc(u.student_id)}</td>
        <td style="padding:10px 12px;font-size:12px;color:#71717a">${u.created_at||''}</td>
        <td style="padding:10px 12px;min-width:160px">
          <div style="display:flex;align-items:center;gap:8px">
            <div class="progress-bar" style="flex:1;height:6px"><div class="progress-fill" style="width:${pct}%;background:linear-gradient(90deg,#6366f1,#a78bfa)"></div></div>
            <span style="font-size:11px;color:#71717a;white-space:nowrap">${pct}%</span>
          </div>
          <div style="font-size:10px;color:#52525b;margin-top:2px">${fmtNum(remaining)} 剩余 / ${fmtNum(u.total_tokens)} 总量</div>
        </td>
        <td style="padding:10px 12px;font-size:12px;color:#a1a1aa">${fmtNum(u.used_tokens)}</td>
        <td style="padding:10px 12px"><span class="badge ${u.is_active?'badge-green':'badge-red'}">${u.is_active?'● 正常':'○ 封禁'}</span></td>
        <td style="padding:10px 12px">
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <button class="btn-ghost" style="font-size:11px;padding:3px 8px" onclick="adminAddQuota(${u.id},'${esc(u.student_id)}')">+ 配额</button>
            <button class="btn-ghost" style="font-size:11px;padding:3px 8px" onclick="adminSetQuota(${u.id},'${esc(u.student_id)}',${u.total_tokens})">=配额</button>
            <button class="btn-ghost" style="font-size:11px;padding:3px 8px;${u.is_active?'color:#f87171;border-color:rgba(248,113,113,0.3)':'color:#4ade80;border-color:rgba(74,222,128,0.3)'}" onclick="adminToggleUser(${u.id},${u.is_active?0:1})">${u.is_active?'封禁':'解封'}</button>
          </div>
        </td>
      </tr>`;
    }).join('');
  } catch(e) { tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;color:#f87171">加载失败，请确认管理员已登录</td></tr>'; }
}

async function adminAddQuota(userId, studentId) {
  const input = prompt(`给用户 ${studentId} 增加配额 (tokens):\n例如：1000000 = 100万`);
  if (!input) return;
  const amount = parseInt(input.replace(/,/g,'').trim());
  if (isNaN(amount) || amount <= 0) { toast('请输入有效的正整数', 'error'); return; }
  const r = await api('POST', `/api/admin/users/${userId}/quota`, {amount});
  if (r.ok) { toast(`已为 ${studentId} 增加 ${fmtNum(amount)} tokens`, 'success'); loadAdminUsers(); }
  else toast(r.error || '操作失败', 'error');
}

async function adminSetQuota(userId, studentId, current) {
  const input = prompt(`设置用户 ${studentId} 的总配额 (tokens):\n当前: ${current.toLocaleString()}`);
  if (!input) return;
  const amount = parseInt(input.replace(/,/g,'').trim());
  if (isNaN(amount) || amount < 0) { toast('请输入有效数值', 'error'); return; }
  const r = await api('PUT', `/api/admin/users/${userId}`, {total_tokens: amount});
  if (r.ok) { toast(`已设置 ${studentId} 配额为 ${fmtNum(amount)} tokens`, 'success'); loadAdminUsers(); }
  else toast(r.error || '操作失败', 'error');
}

async function adminToggleUser(userId, newActive) {
  const action = newActive ? '解封' : '封禁';
  if (!confirm(`确定要${action}该用户吗？`)) return;
  const r = await api('PUT', `/api/admin/users/${userId}`, {is_active: newActive});
  if (r.ok) { toast(`操作成功`, 'success'); loadAdminUsers(); }
  else toast('操作失败', 'error');
}

async function loadAdminKeys() {
  const tbody = document.getElementById('adminKeysTable');
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;color:#a1a1aa">加载中...</td></tr>';
  try {
    const r = await api('GET', '/api/admin/keys');
    if (!r.keys || r.keys.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:#a1a1aa">暂无 Key</td></tr>';
      return;
    }
    tbody.innerHTML = r.keys.map(k => `
      <tr style="border-bottom:1px solid rgba(99,102,241,0.08);transition:background .1s" onmouseover="this.style.background='rgba(99,102,241,0.05)'" onmouseout="this.style.background=''">
        <td style="padding:10px 12px;font-size:13px;font-weight:600">${esc(k.student_id)}</td>
        <td style="padding:10px 12px;font-size:13px">${esc(k.name)}</td>
        <td style="padding:10px 12px"><code style="font-size:11px;color:#a3e635">${esc(k.key_prefix)}</code></td>
        <td style="padding:10px 12px;font-size:12px;color:#a1a1aa">${fmtNum(k.used_tokens)}</td>
        <td style="padding:10px 12px;font-size:12px;color:#71717a">${k.created_at||''}</td>
        <td style="padding:10px 12px"><span class="badge ${k.is_active?'badge-green':'badge-red'}">${k.is_active?'● 启用':'○ 停用'}</span></td>
        <td style="padding:10px 12px">
          <div style="display:flex;gap:6px">
            <button class="btn-ghost" style="font-size:11px;padding:3px 8px" onclick="adminToggleKey(${k.id},${k.is_active?0:1})">${k.is_active?'停用':'启用'}</button>
            <button class="btn-danger" style="font-size:11px;padding:3px 8px" onclick="adminDeleteKey(${k.id})">删除</button>
          </div>
        </td>
      </tr>`).join('');
  } catch(e) { tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;color:#f87171">加载失败</td></tr>'; }
}

async function adminToggleKey(keyId, newActive) {
  const r = await api('POST', `/api/admin/keys/${keyId}/toggle`, {is_active: newActive});
  if (r.ok) { toast(newActive ? 'Key 已启用' : 'Key 已停用', 'success'); loadAdminKeys(); }
  else toast('操作失败', 'error');
}

async function adminDeleteKey(keyId) {
  if (!confirm('确定要删除这个 Key 吗？此操作不可撤销。')) return;
  const r = await api('DELETE', `/api/admin/keys/${keyId}`);
  if (r.ok) { toast('Key 已删除', 'success'); loadAdminKeys(); }
  else toast('删除失败', 'error');
}

async function loadAdminAllLogs() {
  const tbody = document.getElementById('adminAllLogsTable');
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;color:#a1a1aa">加载中...</td></tr>';
  try {
    const r = await api('GET', `/api/admin/all-logs?limit=50&offset=${adminLogsOffset}`);
    if (!r.logs || r.logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:#a1a1aa">暂无日志</td></tr>';
      return;
    }
    tbody.innerHTML = r.logs.map(l => `
      <tr style="border-bottom:1px solid rgba(99,102,241,0.08);font-size:12px">
        <td style="padding:9px 12px;color:#71717a;white-space:nowrap">${l.timestamp||''}</td>
        <td style="padding:9px 12px;font-weight:600">${esc(l.student_id||String(l.user_id||''))}</td>
        <td style="padding:9px 12px"><code class="mono" style="font-size:11px">${esc(l.model||'')}</code></td>
        <td style="padding:9px 12px;text-align:right;color:#a1a1aa">${(l.input_tokens||0).toLocaleString()}</td>
        <td style="padding:9px 12px;text-align:right;color:#a1a1aa">${(l.output_tokens||0).toLocaleString()}</td>
        <td style="padding:9px 12px;text-align:right;font-weight:600">${(l.total_tokens||0).toLocaleString()}</td>
        <td style="padding:9px 12px"><code style="font-size:10px;color:#d4d4d8">${esc(l.key_prefix||'')}</code></td>
      </tr>`).join('');
    const pg = document.getElementById('adminAllLogsPagination');
    pg.innerHTML = '';
    if (adminLogsOffset > 0) { const b=document.createElement('button'); b.className='btn-ghost'; b.textContent='← 上一页'; b.onclick=()=>{adminLogsOffset=Math.max(0,adminLogsOffset-50);loadAdminAllLogs();}; pg.appendChild(b); }
    if (r.logs.length >= 50) { const b=document.createElement('button'); b.className='btn-ghost'; b.textContent='下一页 →'; b.onclick=()=>{adminLogsOffset+=50;loadAdminAllLogs();}; pg.appendChild(b); }
  } catch(e) { tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;color:#f87171">加载失败</td></tr>'; }
}

async function loadAdminAnnouncements() {
  const list = document.getElementById('adminAnnouncementsList');
  list.innerHTML = '<div style="text-align:center;padding:24px;color:#a1a1aa;font-size:13px">加载中...</div>';
  try {
    const r = await api('GET', '/api/admin/announcements');
    if (!r.announcements || r.announcements.length === 0) {
      list.innerHTML = '<div style="text-align:center;padding:32px;color:#71717a;font-size:13px">暂无公告记录</div>';
      return;
    }
    list.innerHTML = r.announcements.map(a => `
      <div class="admin-card" style="padding:14px 16px;display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;color:#e4e4e7;line-height:1.5;word-break:break-word">${esc(a.content)}</div>
          <div style="font-size:11px;color:#71717a;margin-top:6px">由 ${esc(a.created_by)} 于 ${a.created_at||''} 发布</div>
        </div>
        <button class="btn-danger" style="flex-shrink:0;font-size:11px;padding:3px 8px" onclick="adminDeleteAnnouncement(${a.id})">删除</button>
      </div>`).join('');
  } catch(e) { list.innerHTML = '<div style="text-align:center;padding:24px;color:#f87171;font-size:13px">加载失败</div>'; }
}

async function adminSendAnnouncement() {
  const content = document.getElementById('adminAnnouncementContent').value.trim();
  const persistent = document.getElementById('adminAnnouncementPersistent').checked;
  if (!content) { toast('公告内容不能为空', 'error'); return; }
  const r = await api('POST', '/api/admin/announcements', {content, persistent});
  if (r.ok) {
    toast(persistent ? '驻留公告已发送并广播' : '公告已发送并广播', 'success');
    document.getElementById('adminAnnouncementContent').value = '';
    document.getElementById('adminAnnouncementPersistent').checked = false;
    loadAdminAnnouncements();
  } else toast(r.error || '发送失败', 'error');
}

async function adminDeleteAnnouncement(annId) {
  if (!confirm('确定删除这条公告记录吗？')) return;
  const r = await api('DELETE', `/api/admin/announcements/${annId}`);
  if (r.ok) { toast('已删除', 'success'); loadAdminAnnouncements(); }
  else toast('删除失败', 'error');
}

function openBatchAddTokenModal() {
  const amount = prompt('请输入要给所有活跃用户增加的 Token 数量：\\n\\n例如：1000000 (100万)', '1000000');
  if (!amount) return;
  const tokens = parseInt(amount);
  if (isNaN(tokens) || tokens <= 0) {
    toast('请输入有效的正整数', 'error');
    return;
  }
  if (!confirm(`确定给所有活跃用户增加 ${tokens.toLocaleString()} Tokens 吗？\\n\\n此操作不可撤销！`)) return;
  batchAddTokens(tokens);
}

async function batchAddTokens(amount) {
  toast('正在批量添加 Token...', 'info');
  try {
    const r = await api('POST', '/api/admin/users/quota/batch', {amount});
    if (r.ok) {
      toast(`成功给 ${r.count} 个用户增加了 ${amount.toLocaleString()} Tokens`, 'success');
      loadAdminUsers();
    } else {
      toast(r.error || '批量添加失败', 'error');
    }
  } catch(e) {
    toast('批量添加失败', 'error');
  }
}

// ─── Check-in Functions ───────────────────────────────────────────────────────

async function loadCheckinStatus() {
  try {
    const r = await api('GET', '/api/user/checkin/status');
    const statusEl = document.getElementById('checkinStatusBadge');
    const btnEl = document.getElementById('checkinBtn');
    const rewardEl = document.getElementById('checkinReward');

    if (r.checked_in) {
      statusEl.innerHTML = '<span style="width:6px;height:6px;border-radius:50%;background:#4ade80;display:inline-block"></span>已签到';
      statusEl.style.background = 'rgba(5,46,22,0.2)';
      statusEl.style.color = '#4ade80';
      statusEl.style.borderColor = 'rgba(74,222,128,0.3)';
      btnEl.disabled = true;
      btnEl.style.opacity = '0.5';
      btnEl.style.cursor = 'not-allowed';
      btnEl.textContent = '✓ 已签到';

      if (r.tokens_awarded) {
        rewardEl.style.display = 'block';
        document.getElementById('rewardAmount').textContent = fmtNum(r.tokens_awarded);
      }
    } else {
      statusEl.innerHTML = '<span style="width:6px;height:6px;border-radius:50%;background:#fca5a5;display:inline-block"></span>未签到';
      statusEl.style.background = 'rgba(239,68,68,0.2)';
      statusEl.style.color = '#fca5a5';
      statusEl.style.borderColor = 'rgba(239,68,68,0.3)';
      btnEl.disabled = false;
      btnEl.style.opacity = '1';
      btnEl.style.cursor = 'pointer';
      btnEl.textContent = '✨ 立即签到';
      rewardEl.style.display = 'none';
    }
  } catch (e) {
    console.error('Failed to load checkin status:', e);
  }
}

async function loadCheckinHistory() {
  try {
    const r = await api('GET', '/api/user/checkin/history?limit=7');
    if (!r.history) return;

    const today = new Date().toISOString().split('T')[0];
    const dates = new Set(r.history.map(h => h.checkin_date));

    // Generate last 7 days
    const calendar = document.getElementById('checkinCalendar');
    calendar.innerHTML = '';

    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const dateStr = d.toISOString().split('T')[0];
      const dayName = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
      const isCheckedIn = dates.has(dateStr);
      const isToday = dateStr === today;

      const item = document.createElement('div');
      item.style.cssText = `
        padding:12px;
        border-radius:12px;
        text-align:center;
        background:rgba(20,10,25,0.5);
        backdrop-filter:blur(10px);
        -webkit-backdrop-filter:blur(10px);
        border:1px solid rgba(255,255,255,0.15);
        cursor:default;
        transition:all .2s;
      `;

      const dateDisplay = `${d.getMonth()+1}/${d.getDate()}`;
      item.innerHTML = `
        <div style="font-size:11px;color:#a1a1aa;margin-bottom:4px">周${dayName}</div>
        <div style="font-size:13px;font-weight:600;color:#fff;margin-bottom:4px">${dateDisplay}</div>
        <div style="font-size:12px;color:${isCheckedIn ? '#bfdbfe' : '#a1a1aa'};font-weight:600">${isCheckedIn ? '✓' : '—'}</div>
      `;

      calendar.appendChild(item);
    }

    // Update consecutive days and monthly total
    if (r.history && r.history.length > 0) {
      document.getElementById('consecutiveDays').textContent = r.history.length;
      document.getElementById('monthlyTotal').textContent = fmtNum(r.total_tokens_earned || 0);
    }
  } catch (e) {
    console.error('Failed to load checkin history:', e);
  }
}

async function performCheckin() {
  const btn = document.getElementById('checkinBtn');
  btn.disabled = true;
  btn.style.opacity = '0.6';

  try {
    const r = await api('POST', '/api/user/checkin');

    if (r.ok) {
      // Success animation
      const rewardEl = document.getElementById('checkinReward');
      rewardEl.style.display = 'block';
      document.getElementById('rewardAmount').textContent = fmtNum(r.tokens_awarded);

      // Animate reward
      rewardEl.style.animation = 'none';
      setTimeout(() => {
        rewardEl.style.animation = 'pulse 0.6s ease-out';
      }, 10);

      toast(`签到成功！获得 ${fmtNum(r.tokens_awarded)} Tokens`, 'success');

      // Update status
      setTimeout(() => {
        loadCheckinStatus();
        loadCheckinHistory();
        loadDashboard();
      }, 500);
    } else if (r.already_checked_in) {
      toast('今日已签到', 'error');
      loadCheckinStatus();
    } else {
      toast(r.error || '签到失败', 'error');
    }
  } catch (e) {
    toast('签到出错', 'error');
    console.error('Checkin error:', e);
  } finally {
    btn.disabled = false;
    btn.style.opacity = '1';
  }
}

// Add pulse animation
const style = document.createElement('style');
style.textContent = `
  @keyframes pulse {
    0% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); opacity: 1; }
  }
`;
document.head.appendChild(style);

// ─── Admin Check-in Configuration ─────────────────────────────────────────────

async function loadCheckinConfig() {
  try {
    const r = await api('GET', '/api/admin/checkin/config');
    if (r.min_tokens !== undefined && r.max_tokens !== undefined) {
      document.getElementById('adminCheckinMin').value = r.min_tokens;
      document.getElementById('adminCheckinMax').value = r.max_tokens;
      updateCheckinPreview();
    }
  } catch (e) {
    console.error('Failed to load checkin config:', e);
  }
}

function updateCheckinPreview() {
  const min = parseInt(document.getElementById('adminCheckinMin').value) || 0;
  const max = parseInt(document.getElementById('adminCheckinMax').value) || 0;
  const avg = min > 0 && max > 0 ? Math.round((min + max) / 2) : 0;

  document.getElementById('previewMin').textContent = min > 0 ? fmtNum(min) : '—';
  document.getElementById('previewMax').textContent = max > 0 ? fmtNum(max) : '—';
  document.getElementById('previewAvg').textContent = avg > 0 ? fmtNum(avg) : '—';
}

async function saveCheckinConfig() {
  const min = parseInt(document.getElementById('adminCheckinMin').value);
  const max = parseInt(document.getElementById('adminCheckinMax').value);

  if (!min || !max || min <= 0 || max < min) {
    toast('请输入有效的奖励范围（最小值 > 0 且 最小值 ≤ 最大值）', 'error');
    return;
  }

  try {
    const r = await api('POST', '/api/admin/checkin/config', {min_tokens: min, max_tokens: max});
    if (r.ok) {
      toast('签到配置已保存', 'success');
      updateCheckinPreview();
    } else {
      toast(r.error || '保存失败', 'error');
    }
  } catch (e) {
    toast('保存出错', 'error');
    console.error('Save config error:', e);
  }
}

async function loadCheckinStats() {
  try {
    const r = await api('GET', '/api/admin/checkin/stats?days=1');
    if (r.stats && r.stats.length > 0) {
      const today = r.stats[0];
      document.getElementById('statCheckinToday').textContent = today.checkin_count || 0;
      document.getElementById('statTokensToday').textContent = fmtNum(today.total_tokens_awarded || 0);
    } else {
      document.getElementById('statCheckinToday').textContent = '0';
      document.getElementById('statTokensToday').textContent = '0';
    }

    if (r.summary) {
      document.getElementById('statCheckinTotal').textContent = r.summary.total_checkins || 0;
      document.getElementById('statTokensTotal').textContent = fmtNum(r.summary.total_tokens_awarded || 0);
    }
  } catch (e) {
    console.error('Failed to load checkin stats:', e);
  }
}

// Add event listeners for preview updates
document.addEventListener('DOMContentLoaded', () => {
  const minInput = document.getElementById('adminCheckinMin');
  const maxInput = document.getElementById('adminCheckinMax');
  if (minInput) minInput.addEventListener('input', updateCheckinPreview);
  if (maxInput) maxInput.addEventListener('input', updateCheckinPreview);

  // Check if should show leaderboard on first login today
  checkAndShowLeaderboardOnFirstLogin();
});

// Leaderboard functions
let leaderboardShownToday = false;

async function checkAndShowLeaderboardOnFirstLogin() {
  const today = new Date().toISOString().split('T')[0];
  const lastShown = localStorage.getItem('leaderboard_last_shown');

  if (lastShown !== today) {
    // Wait a bit for page to load
    setTimeout(() => {
      showLeaderboard();
      localStorage.setItem('leaderboard_last_shown', today);
    }, 1500);
  }
}

async function showLeaderboard() {
  try {
    const r = await api('GET', '/api/user/checkin/leaderboard?limit=50');
    if (!r.ok) {
      toast('无法加载排行榜', 'error');
      return;
    }

    const leaderboard = r.leaderboard || [];
    if (leaderboard.length === 0) {
      toast('今日还没有人签到', 'info');
      return;
    }

    // Create modal
    const modal = document.createElement('div');
    modal.id = 'leaderboardModal';
    modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;animation:fadeIn 0.2s';

    const content = document.createElement('div');
    content.style.cssText = 'background:rgba(24,24,27,0.95);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.15);border-radius:16px;padding:28px;max-width:600px;width:100%;max-height:80vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.5)';

    // Header
    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:24px';
    header.innerHTML = `
      <div>
        <div style="font-size:20px;font-weight:700;color:#fff;margin-bottom:4px">今日签到排行榜</div>
        <div style="font-size:13px;color:#a1a1aa">${r.date} · 共 ${r.total_count} 人签到</div>
      </div>
      <button onclick="closeLeaderboard()" style="width:32px;height:32px;border-radius:8px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:#a1a1aa;cursor:pointer;transition:all .2s;display:flex;align-items:center;justify-content:center">
        <svg style="width:18px;height:18px" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
      </button>
    `;

    // Leaderboard list
    const list = document.createElement('div');
    list.style.cssText = 'display:flex;flex-direction:column;gap:10px';

    leaderboard.forEach((item, idx) => {
      const isFirst = idx === 0;
      const itemEl = document.createElement('div');

      if (isFirst) {
        // First place - special gold style
        itemEl.style.cssText = 'padding:20px;background:linear-gradient(135deg,rgba(202,138,4,0.2),rgba(234,179,8,0.1));border:2px solid rgba(202,138,4,0.5);border-radius:12px;display:flex;align-items:center;gap:16px;animation:danmaku 20s linear infinite';
        itemEl.innerHTML = `
          <div style="font-size:32px;font-weight:900;color:#ca8a04;text-shadow:0 0 20px rgba(202,138,4,0.6);min-width:40px;text-align:center">1</div>
          <div style="flex:1">
            <div style="font-size:18px;font-weight:700;color:#fbbf24;text-shadow:0 0 10px rgba(251,191,36,0.5)">${item.display_name || item.student_id}</div>
            <div style="font-size:13px;color:#fde047;margin-top:2px">${item.student_id}</div>
          </div>
          <div style="text-align:right">
            <div style="font-size:24px;font-weight:700;color:#fbbf24;text-shadow:0 0 10px rgba(251,191,36,0.5)">${fmtNum(item.tokens_awarded)}</div>
            <div style="font-size:11px;color:#fde047;margin-top:2px">Tokens</div>
          </div>
        `;
      } else {
        // Other places
        const rankColor = idx === 1 ? '#d4d4d8' : idx === 2 ? '#cd7f32' : '#71717a';
        itemEl.style.cssText = 'padding:14px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:10px;display:flex;align-items:center;gap:12px;transition:all .2s';
        itemEl.innerHTML = `
          <div style="font-size:16px;font-weight:700;color:${rankColor};min-width:32px;text-align:center">${item.rank}</div>
          <div style="flex:1">
            <div style="font-size:14px;font-weight:600;color:#e4e4e8">${item.display_name || item.student_id}</div>
            <div style="font-size:12px;color:#a1a1aa;margin-top:2px">${item.student_id}</div>
          </div>
          <div style="text-align:right">
            <div style="font-size:16px;font-weight:600;color:#4ade80">${fmtNum(item.tokens_awarded)}</div>
            <div style="font-size:10px;color:#a1a1aa;margin-top:2px">Tokens</div>
          </div>
        `;
      }

      list.appendChild(itemEl);
    });

    content.appendChild(header);
    content.appendChild(list);
    modal.appendChild(content);
    document.body.appendChild(modal);

    // Close on backdrop click
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeLeaderboard();
    });

  } catch (e) {
    console.error('Failed to load leaderboard:', e);
    toast('加载排行榜失败', 'error');
  }
}

function closeLeaderboard() {
  const modal = document.getElementById('leaderboardModal');
  if (modal) {
    modal.style.animation = 'fadeOut 0.2s';
    setTimeout(() => modal.remove(), 200);
  }
}

init();
</script>
<script>lucide.createIcons();</script>
</body>
</html>"""
