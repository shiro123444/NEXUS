"""Kiro API Proxy - 主应用"""
import json
import os
import uuid
import httpx
import sys
import re
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Portal: admin auth credentials (override via env)
_ADMIN_USER = os.environ.get("KIRO_ADMIN_USER", "shiro")
_ADMIN_PASS = os.environ.get("KIRO_ADMIN_PASS", "fyz040913")

from .config import (
    MODELS_URL, THINKING_MODEL_VARIANTS, BUILTIN_KIRO_MODELS, AGENTIC_MODEL_VARIANTS,
    get_custom_models, add_custom_model, remove_custom_model, _load_custom_models
)
from .core import state, scheduler, stats_manager
from .core.log_broadcaster import log_broadcaster
from .core.http_pool import http_pool
from .handlers import anthropic, openai, gemini, admin
from .handlers import responses as responses_handler

# 模型上下文窗口和输出限制配置
MODEL_CONTEXT_WINDOWS = {
    # model_id: context_window_tokens
    "auto":                200000,
    "claude-sonnet-4.6":   200000,
    "claude-sonnet-4.5":   200000,
    "claude-sonnet-4":     200000,
    "claude-haiku-4.5":    200000,
    "claude-opus-4.5":     200000,
    "claude-opus-4.6":     200000,
}
MODEL_MAX_OUTPUT_TOKENS = 32000  # Kiro 统一输出限制
from .web import get_html_page
from .credential import generate_machine_id, get_kiro_version
from .portal import db as portal_db
from .portal.auth import create_admin_session, verify_admin_session
from .portal.admin_portal import router as portal_admin_router


def get_resource_path(relative_path: str) -> Path:
    """获取资源文件路径，支持从打包资源读取"""
    base_path = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(__file__).parent.parent
    return base_path / relative_path


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    log_broadcaster.install()  # 安装日志广播
    _load_custom_models()  # 加载自定义模型
    await http_pool.warmup()  # 预热 HTTP 连接池
    await scheduler.start()
    await portal_db.init_db()  # 初始化用户门户数据库
    yield
    # 关闭时
    from .core import stats_manager
    stats_manager.force_save()  # 持久化统计
    await scheduler.stop()
    await http_pool.close_all()  # 关闭连接池


app = FastAPI(title="Kiro API Proxy", docs_url="/docs", redoc_url=None, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Portal API key middleware ────────────────────────────────────────────────
from fastapi import Request as _Request
from starlette.middleware.base import BaseHTTPMiddleware

class PortalKeyMiddleware(BaseHTTPMiddleware):
    """Validate kp-xxx API keys and attach user info to request.state."""
    async def dispatch(self, request, call_next):
        auth = request.headers.get("Authorization", "")
        xkey = request.headers.get("x-api-key", "")
        # Also support x-api-key header (used by Anthropic SDK / Cherry Studio)
        if not auth.startswith("Bearer kp-"):
            if xkey.startswith("kp-"):
                auth = f"Bearer {xkey}"
        if auth.startswith("Bearer kp-"):
            key = auth[7:]
            try:
                from .portal.db import validate_key_sync
                info = validate_key_sync(key)
                from starlette.responses import JSONResponse
                if isinstance(info, dict):
                    request.state.portal_key_info = info
                    print(f"[Portal] Key validated: user={info.get('student_id')} key={info.get('key_prefix')}")
                elif info == "quota_exceeded":
                    return JSONResponse({"error": {"type": "permission_error", "message": "已达到上限，感谢体验～"}}, status_code=403)
                else:
                    return JSONResponse({"error": {"type": "authentication_error", "message": "Invalid or expired portal API key"}}, status_code=401)
            except Exception as e:
                print(f"[Portal] Key validation error: {e}")
        else:
            if request.url.path.startswith("/v1/"):
                print(f"[Portal] No kp- key for {request.url.path}: auth={auth[:20]!r} xkey={xkey[:10]!r}")
        return await call_next(request)

app.add_middleware(PortalKeyMiddleware)

# ─── Portal admin router ─────────────────────────────────────────────────────
app.include_router(portal_admin_router)


# ==================== Web UI ====================

_ADMIN_LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kiro-Kroxy — Admin</title>
<script src="https://lf26-cdn-tos.bytecdntp.com/cdn/expire-1-M/tailwindcss/3.0.23/tailwind.min.js"></script>
<style>
* { box-sizing: border-box; }
body {
  background: #09090b;
  color: #f4f4f5;
  font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  margin: 0;
}
.card {
  background: rgba(20, 10, 25, 0.5);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 16px;
  padding: 40px;
  width: 100%;
  max-width: 380px;
  box-shadow: 0 8px 32px 0 rgba(99, 102, 241, 0.15);
}
.header {
  text-align: center;
  margin-bottom: 32px;
}
.header-icon {
  font-size: 48px;
  margin-bottom: 12px;
  filter: drop-shadow(0 0 12px rgba(99, 102, 241, 0.6));
}
.header-title {
  font-size: 24px;
  font-weight: 800;
  color: #fff;
  letter-spacing: -0.5px;
  margin-bottom: 4px;
}
.header-subtitle {
  font-size: 13px;
  color: #a1a1aa;
  font-weight: 500;
}
.form-group {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 20px;
}
.input {
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 10px;
  padding: 12px 16px;
  font-size: 14px;
  color: #f4f4f5;
  width: 100%;
  outline: none;
  transition: all 0.2s;
}
.input:focus {
  border-color: #6366f1;
  background: rgba(0, 0, 0, 0.6);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}
.input::placeholder {
  color: #71717a;
}
.btn {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: #fff;
  border: none;
  border-radius: 10px;
  padding: 12px 20px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35);
  width: 100%;
}
.btn:hover {
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
  transform: translateY(-1px);
}
.btn:active {
  transform: scale(0.98);
}
.err {
  color: #fca5a5;
  font-size: 13px;
  margin-top: 12px;
  display: none;
  padding: 10px 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
}
.footer {
  text-align: center;
  margin-top: 20px;
  font-size: 12px;
  color: #71717a;
}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <div class="header-icon">🔐</div>
    <div class="header-title">Kiro-Kroxy</div>
    <div class="header-subtitle">管理员登录 / Admin Login</div>
  </div>
  <div class="form-group">
    <input id="u" class="input" placeholder="用户名 / Username" onkeydown="if(event.key==='Enter')login()">
    <input id="p" class="input" type="password" placeholder="密码 / Password" onkeydown="if(event.key==='Enter')login()">
  </div>
  <button class="btn" onclick="login()">登录 / Login</button>
  <div id="err" class="err"></div>
  <div class="footer">Kiro API Proxy v1.7.16</div>
</div>
<script>
async function login(){
  const u=document.getElementById('u').value,p=document.getElementById('p').value;
  if(!u||!p){const e=document.getElementById('err');e.textContent='请输入用户名和密码';e.style.display='block';return;}
  const btn=document.querySelector('.btn');btn.disabled=true;btn.style.opacity='0.6';
  try{
    const r=await fetch('/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    const d=await r.json();
    if(d.ok)location.reload();
    else{const e=document.getElementById('err');e.textContent=d.error||'登录失败';e.style.display='block';}
  }catch(err){
    const e=document.getElementById('err');e.textContent='网络错误';e.style.display='block';
  }finally{btn.disabled=false;btn.style.opacity='1';}
}
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    token = request.cookies.get("admin_session")
    if not token or not verify_admin_session(token):
        return HTMLResponse(_ADMIN_LOGIN_HTML)
    return get_html_page()


@app.post("/admin/login")
async def admin_login(request: Request):
    body = await request.json()
    if body.get("username") == _ADMIN_USER and body.get("password") == _ADMIN_PASS:
        token = create_admin_session(_ADMIN_USER)
        resp = JSONResponse({"ok": True})
        resp.set_cookie("admin_session", token, httponly=True, samesite="lax", max_age=86400)
        return resp
    return JSONResponse({"ok": False, "error": "用户名或密码错误"}, status_code=401)


@app.post("/admin/logout")
async def admin_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("admin_session")
    return resp


@app.get("/assets/{path:path}")
async def serve_assets(path: str):
    """提供静态资源"""
    file_path = get_resource_path("assets") / path
    if file_path.exists():
        content_type = "image/svg+xml" if path.endswith(".svg") else "application/octet-stream"
        return StreamingResponse(open(file_path, "rb"), media_type=content_type)
    raise HTTPException(status_code=404)


# ==================== API 端点 ====================

@app.get("/v1/models")
@app.get("/models")  # 兼容不带 /v1 前缀的调用
async def models():
    """获取可用模型列表（遍历所有账号合并）"""
    def _dash_version_alias(model_id: str) -> str:
        # Keep legacy IDs visible: claude-sonnet-4.6 -> claude-sonnet-4-6
        return re.sub(r'-(\d+)\.(\d+)', r'-\1-\2', model_id)

    def _append_dash_aliases(items: list) -> list:
        existing = {m.get("id") for m in items}
        aliases = []
        for m in items:
            mid = m.get("id", "")
            alias = _dash_version_alias(mid)
            if alias != mid and alias not in existing:
                am = m.copy()
                am["id"] = alias
                aliases.append(am)
                existing.add(alias)
        items.extend(aliases)
        return items

    all_models = {}  # id -> model dict，自动去重
    kiro_version = get_kiro_version()
    
    # 遍历所有账号，合并模型列表
    for idx, account in enumerate(state.accounts):
        try:
            token = account.get_token()
            if not token:
                print(f"[Models] Account {idx} ({account.id}): no token, skipping")
                continue
            machine_id = account.get_machine_id()
            headers = {
                "content-type": "application/json",
                "x-amz-user-agent": f"aws-sdk-js/1.0.0 KiroIDE-{kiro_version}-{machine_id}",
                "amz-sdk-invocation-id": str(uuid.uuid4()),
                "Authorization": f"Bearer {token}",
            }
            resp = await http_pool.model_client.get(MODELS_URL, headers=headers, params={"origin": "AI_EDITOR"})
            if resp.status_code == 200:
                data = resp.json()
                account_models = [m["modelId"] for m in data.get("models", [])]
                print(f"[Models] Account {idx} ({account.id}): {account_models}")
                for m in data.get("models", []):
                    mid = m["modelId"]
                    if mid not in all_models:
                        all_models[mid] = {
                            "id": mid,
                            "object": "model",
                            "owned_by": "kiro",
                            "name": m["modelName"],
                            "context_window": MODEL_CONTEXT_WINDOWS.get(mid, 200000),
                            "max_tokens": MODEL_MAX_OUTPUT_TOKENS,
                        }
            else:
                print(f"[Models] Account {idx} ({account.id}): HTTP {resp.status_code} - {resp.text[:200]}")
        except Exception as e:
            print(f"[Models] Account {idx} failed: {e}")
            continue
    
    if all_models:
        model_list = list(all_models.values())
        
        # 补充已知的内置模型（Enterprise 账号 ListModels 可能 403，但实际可用）
        for mid, mname in [("claude-opus-4.5", "Claude Opus 4.5"), ("claude-opus-4.6", "Claude Opus 4.6"), ("claude-sonnet-4.6", "Claude Sonnet 4.6")]:
            if mid not in all_models:
                ctx = MODEL_CONTEXT_WINDOWS.get(mid, 200000)
                model_list.append({
                    "id": mid, "object": "model", "owned_by": "kiro", "name": mname,
                    "context_window": ctx, "context_length": ctx,
                    "max_tokens": MODEL_MAX_OUTPUT_TOKENS,
                })
        
        # 为支持的模型自动添加 -thinking 版本
        thinking_models = []
        for m in model_list:
            thinking_id = f"{m['id']}-thinking"
            if thinking_id in THINKING_MODEL_VARIANTS:
                thinking_model = m.copy()
                thinking_model["id"] = thinking_id
                thinking_model["name"] = f"{m['name']} (Thinking)"
                thinking_model["thinking"] = True
                thinking_models.append(thinking_model)
        model_list.extend(thinking_models)
        
        # 添加 agentic 变体
        agentic_models = []
        for m in model_list:
            if not m.get("thinking"):
                agentic_id = f"{m['id']}-agentic"
                if agentic_id in AGENTIC_MODEL_VARIANTS:
                    ag = m.copy()
                    ag["id"] = agentic_id
                    ag["name"] = f"{m['name']} (Agentic)"
                    ag["thinking"] = False
                    agentic_models.append(ag)
        model_list.extend(agentic_models)
        
        # 添加自定义模型
        existing_ids = {m["id"] for m in model_list}
        for model_id, model_info in get_custom_models().items():
            if model_id not in existing_ids:
                ctx = MODEL_CONTEXT_WINDOWS.get(model_id, 200000)
                model_list.append({
                    "id": model_id, "object": "model", "owned_by": "kiro", "name": model_info.get("name", model_id),
                    "context_window": ctx, "context_length": ctx,
                    "max_tokens": MODEL_MAX_OUTPUT_TOKENS,
                })
        model_list = _append_dash_aliases(model_list)
        return {
            "object": "list",
            "data": model_list
        }
    
    # 降级返回静态列表（包含自定义模型）
    def _make_model(mid, mname, thinking=False):
        ctx = MODEL_CONTEXT_WINDOWS.get(mid, 200000)
        return {
            "id": mid, "object": "model", "owned_by": "kiro", "name": mname,
            "context_window": ctx, "context_length": ctx,
            "max_tokens": MODEL_MAX_OUTPUT_TOKENS, "thinking": thinking,
        }
    
    builtin = [
        _make_model("auto",              "Auto"),
        _make_model("claude-sonnet-4.5", "Claude Sonnet 4.5"),
        _make_model("claude-sonnet-4",   "Claude Sonnet 4"),
        _make_model("claude-haiku-4.5",  "Claude Haiku 4.5"),
        _make_model("claude-opus-4.5",   "Claude Opus 4.5"),
        _make_model("claude-opus-4.6",   "Claude Opus 4.6"),
        _make_model("claude-sonnet-4.6", "Claude Sonnet 4.6"),
    ]
    # 为静态列表也添加 thinking 变体
    thinking_fallback = []
    for m in builtin:
        thinking_id = f"{m['id']}-thinking"
        if thinking_id in THINKING_MODEL_VARIANTS:
            tm = m.copy()
            tm["id"] = thinking_id
            tm["name"] = f"{m['name']} (Thinking)"
            tm["thinking"] = True
            thinking_fallback.append(tm)
    builtin.extend(thinking_fallback)
    
    # 为静态列表添加 agentic 变体
    agentic_fallback = []
    for m in builtin:
        if not m.get("thinking"):
            agentic_id = f"{m['id']}-agentic"
            if agentic_id in AGENTIC_MODEL_VARIANTS:
                ag = m.copy()
                ag["id"] = agentic_id
                ag["name"] = f"{m['name']} (Agentic)"
                ag["thinking"] = False
                agentic_fallback.append(ag)
    builtin.extend(agentic_fallback)
    
    # 追加用户自定义模型
    custom = get_custom_models()
    for mid, info in custom.items():
        ctx = MODEL_CONTEXT_WINDOWS.get(mid, 200000)
        builtin.append({
            "id": mid, "object": "model", "owned_by": "kiro", "name": info.get("name", mid),
            "context_window": ctx, "context_length": ctx,
            "max_tokens": MODEL_MAX_OUTPUT_TOKENS,
        })
    builtin = _append_dash_aliases(builtin)
    return {"object": "list", "data": builtin}


# Anthropic 协议
@app.post("/v1/messages")
@app.post("/messages")  # 兼容不带 /v1 前缀的调用
async def anthropic_messages(request: Request):
    return await anthropic.handle_messages(request)

@app.post("/v1/messages/count_tokens")
@app.post("/messages/count_tokens")  # 兼容不带 /v1 前缀的调用
async def anthropic_count_tokens(request: Request):
    return await anthropic.handle_count_tokens(request)



# OpenAI 协议
@app.post("/v1/chat/completions")
@app.post("/chat/completions")  # 兼容不带 /v1 前缀的调用
async def openai_chat(request: Request):
    return await openai.handle_chat_completions(request)


# OpenAI Responses API (Codex CLI 新版本)
@app.post("/v1/responses")
@app.post("/responses")  # 兼容不带 /v1 前缀的调用
async def openai_responses(request: Request):
    return await responses_handler.handle_responses(request)


# Gemini 协议
@app.post("/v1beta/models/{model_name}:generateContent")
@app.post("/v1/models/{model_name}:generateContent")
async def gemini_generate(model_name: str, request: Request):
    return await gemini.handle_generate_content(model_name, request)


# ==================== 管理 API ====================

@app.get("/api/status")
async def api_status():
    return await admin.get_status()

@app.post("/api/event_logging/batch")
async def api_event_logging_batch(request: Request):
    return await admin.event_logging_batch(request)


@app.get("/api/stats")
async def api_stats():
    return await admin.get_stats()


@app.get("/api/logs")
async def api_logs(limit: int = 100):
    return await admin.get_logs(limit)


@app.get("/api/logs/stream")
async def api_logs_stream():
    """SSE 实时日志流"""
    return StreamingResponse(
        log_broadcaster.subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ==================== 账号导入导出 API ====================

@app.get("/api/accounts/export")
async def api_export_accounts():
    """导出所有账号配置"""
    return await admin.export_accounts()


@app.post("/api/accounts/import")
async def api_import_accounts(request: Request):
    """导入账号配置"""
    return await admin.import_accounts(request)


@app.post("/api/accounts/manual")
async def api_add_manual_token(request: Request):
    """手动添加 Token"""
    return await admin.add_manual_token(request)


@app.post("/api/accounts/refresh-all")
async def api_refresh_all():
    """刷新所有即将过期的 token"""
    return await admin.refresh_all_tokens()


@app.get("/api/accounts")
async def api_accounts():
    return await admin.get_accounts()


@app.post("/api/accounts")
async def api_add_account(request: Request):
    return await admin.add_account(request)


@app.delete("/api/accounts/{account_id}")
async def api_delete_account(account_id: str):
    return await admin.delete_account(account_id)


@app.post("/api/accounts/{account_id}/toggle")
async def api_toggle_account(account_id: str):
    return await admin.toggle_account(account_id)


@app.post("/api/speedtest")
async def api_speedtest():
    return await admin.speedtest()


@app.get("/api/token/scan")
async def api_scan_tokens():
    return await admin.scan_tokens()


@app.post("/api/token/add-from-scan")
async def api_add_from_scan(request: Request):
    return await admin.add_from_scan(request)


@app.get("/api/config/export")
async def api_export_config():
    return await admin.export_config()


@app.post("/api/config/import")
async def api_import_config(request: Request):
    return await admin.import_config(request)


@app.post("/api/token/refresh-check")
async def api_refresh_check():
    return await admin.refresh_token_check()


@app.post("/api/accounts/{account_id}/refresh")
async def api_refresh_account(account_id: str):
    """刷新指定账号的 token"""
    return await admin.refresh_account_token(account_id)


@app.post("/api/accounts/{account_id}/restore")
async def api_restore_account(account_id: str):
    """恢复账号（从冷却状态）"""
    return await admin.restore_account(account_id)


@app.get("/api/accounts/{account_id}/usage")
async def api_account_usage(account_id: str):
    """获取账号用量信息"""
    return await admin.get_account_usage_info(account_id)


@app.get("/api/accounts/{account_id}")
async def api_account_detail(account_id: str):
    """获取账号详细信息"""
    return await admin.get_account_detail(account_id)


@app.get("/api/quota")
async def api_quota_status():
    """获取配额状态"""
    return await admin.get_quota_status()


@app.get("/api/kiro/login-url")
async def api_login_url():
    return await admin.get_kiro_login_url()


@app.get("/api/stats/detailed")
async def api_detailed_stats():
    """获取详细统计信息"""
    return await admin.get_detailed_stats()


@app.post("/api/health-check")
async def api_health_check():
    """手动触发健康检查"""
    return await admin.run_health_check()


@app.get("/api/browsers")
async def api_browsers():
    """获取可用浏览器列表"""
    return await admin.get_browsers()


# ==================== Kiro 登录 API ====================

@app.post("/api/kiro/login/start")
async def api_kiro_login_start(request: Request):
    """启动 Kiro 设备授权登录"""
    return await admin.start_kiro_login(request)


@app.get("/api/kiro/login/poll")
async def api_kiro_login_poll():
    """轮询登录状态"""
    return await admin.poll_kiro_login()


@app.post("/api/kiro/login/cancel")
async def api_kiro_login_cancel():
    """取消登录"""
    return await admin.cancel_kiro_login()


@app.get("/api/kiro/login/status")
async def api_kiro_login_status():
    """获取登录状态"""
    return await admin.get_kiro_login_status()


# ==================== Social Auth API (Google/GitHub) ====================

@app.post("/api/kiro/social/start")
async def api_social_login_start(request: Request):
    """启动 Social Auth 登录"""
    return await admin.start_social_login(request)


@app.post("/api/kiro/social/exchange")
async def api_social_token_exchange(request: Request):
    """交换 Social Auth Token"""
    return await admin.exchange_social_token(request)


@app.post("/api/kiro/social/cancel")
async def api_social_login_cancel():
    """取消 Social Auth 登录"""
    return await admin.cancel_social_login()


@app.get("/api/kiro/social/status")
async def api_social_login_status():
    """获取 Social Auth 状态"""
    return await admin.get_social_login_status()


# ==================== Flow Monitor API ====================

@app.get("/api/flows")
async def api_flows(
    protocol: str = None,
    model: str = None,
    account_id: str = None,
    state: str = None,
    has_error: bool = None,
    bookmarked: bool = None,
    search: str = None,
    limit: int = 50,
    offset: int = 0,
):
    """查询 Flows"""
    return await admin.get_flows(
        protocol=protocol,
        model=model,
        account_id=account_id,
        state_filter=state,
        has_error=has_error,
        bookmarked=bookmarked,
        search=search,
        limit=limit,
        offset=offset,
    )


@app.get("/api/flows/stats")
async def api_flow_stats():
    """获取 Flow 统计"""
    return await admin.get_flow_stats()


@app.get("/api/flows/{flow_id}")
async def api_flow_detail(flow_id: str):
    """获取 Flow 详情"""
    return await admin.get_flow_detail(flow_id)


@app.post("/api/flows/{flow_id}/bookmark")
async def api_bookmark_flow(flow_id: str, request: Request):
    """书签 Flow"""
    return await admin.bookmark_flow(flow_id, request)


@app.post("/api/flows/{flow_id}/note")
async def api_add_flow_note(flow_id: str, request: Request):
    """添加 Flow 备注"""
    return await admin.add_flow_note(flow_id, request)


@app.post("/api/flows/{flow_id}/tag")
async def api_add_flow_tag(flow_id: str, request: Request):
    """添加 Flow 标签"""
    return await admin.add_flow_tag(flow_id, request)


@app.post("/api/flows/export")
async def api_export_flows(request: Request):
    """导出 Flows"""
    return await admin.export_flows(request)


# ==================== 远程登录 API ====================

@app.post("/api/remote-login/create")
async def api_create_remote_login(request: Request):
    """创建远程登录链接"""
    return await admin.create_remote_login_link(request)


@app.get("/api/remote-login/{session_id}/status")
async def api_remote_login_status(session_id: str):
    """获取远程登录状态"""
    return await admin.get_remote_login_status(session_id)


@app.post("/api/remote-login/{session_id}/complete")
async def api_complete_remote_login(session_id: str, request: Request):
    """完成远程登录"""
    return await admin.complete_remote_login(session_id, request)


@app.get("/remote-login/{session_id}", response_class=HTMLResponse)
async def remote_login_page(session_id: str):
    """远程登录页面"""
    return admin.get_remote_login_page(session_id)


# ==================== 自定义模型管理 API ====================

@app.get("/api/settings/models")
async def api_get_custom_models():
    """获取自定义模型列表"""
    custom = get_custom_models()
    builtin = sorted(BUILTIN_KIRO_MODELS)
    return {
        "builtin_models": builtin,
        "custom_models": custom,
    }

@app.post("/api/settings/models")
async def api_add_custom_model(request: Request):
    """添加自定义模型"""
    data = await request.json()
    model_id = data.get("model_id", "").strip()
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    
    if not model_id:
        raise HTTPException(400, "模型 ID 不能为空")
    
    if model_id in BUILTIN_KIRO_MODELS:
        raise HTTPException(400, f"'{model_id}' 是内置模型，无需添加")
    
    add_custom_model(model_id, name, description)
    return {"ok": True, "model_id": model_id}

@app.delete("/api/settings/models/{model_id:path}")
async def api_remove_custom_model(model_id: str):
    """删除自定义模型"""
    if model_id in BUILTIN_KIRO_MODELS:
        raise HTTPException(400, "不能删除内置模型")
    
    if remove_custom_model(model_id):
        return {"ok": True}
    raise HTTPException(404, "模型不存在")


# ==================== 历史消息管理 API ====================

from .core.rate_limiter import get_rate_limiter

@app.get("/api/settings/history")
async def api_get_history_config():
    """获取历史消息管理配置（已固定，和 kiro.rs 对齐）"""
    return {
        "strategies": ["none"],
        "max_messages": 0,
        "max_chars": 0,
        "retry_max_messages": 0,
        "max_retries": 0,
        "summary_keep_recent": 0,
        "summary_threshold": 0,
        "summary_cache_enabled": False,
        "summary_cache_min_delta_messages": 0,
        "summary_cache_min_delta_chars": 0,
        "summary_cache_max_age_seconds": 0,
        "add_warning_header": False,
        "readonly": True,
    }


@app.post("/api/settings/history")
async def api_update_history_config(request: Request):
    """更新历史消息管理配置（已禁用）"""
    _ = await request.json()
    return {"ok": True, "readonly": True}


# ==================== 限速配置 API ====================

@app.get("/api/settings/rate-limit")
async def api_get_rate_limit_config():
    """获取限速配置"""
    limiter = get_rate_limiter()
    return {
        "enabled": limiter.config.enabled,
        "min_request_interval": limiter.config.min_request_interval,
        "max_requests_per_minute": limiter.config.max_requests_per_minute,
        "global_max_requests_per_minute": limiter.config.global_max_requests_per_minute,
        "quota_cooldown_seconds": limiter.config.quota_cooldown_seconds,
        "stats": limiter.get_stats()
    }


@app.post("/api/settings/rate-limit")
async def api_update_rate_limit_config(request: Request):
    """更新限速配置"""
    data = await request.json()
    limiter = get_rate_limiter()
    limiter.update_config(**data)
    return {"ok": True, "config": {
        "enabled": limiter.config.enabled,
        "min_request_interval": limiter.config.min_request_interval,
        "max_requests_per_minute": limiter.config.max_requests_per_minute,
        "global_max_requests_per_minute": limiter.config.global_max_requests_per_minute,
        "quota_cooldown_seconds": limiter.config.quota_cooldown_seconds,
    }}


# ==================== 文档 API ====================

# 文档标题映射
DOC_TITLES = {
    "zh": {
        "01-quickstart": "快速开始",
        "02-features": "功能特性",
        "03-faq": "常见问题",
        "04-api": "API 参考",
        "05-server-deploy": "服务器部署",
    },
    "en": {
        "01-quickstart": "Quick Start",
        "02-features": "Features",
        "03-faq": "FAQ",
        "04-api": "API Reference",
        "05-server-deploy": "Server Deployment",
    }
}

def _get_docs_dir_for_lang() -> Path:
    """根据当前语言获取文档目录"""
    from .web.i18n import get_current_lang
    lang = get_current_lang()
    lang_docs_dir = get_resource_path(f"kiro_proxy/docs/{lang}")
    if lang_docs_dir.exists():
        return lang_docs_dir, lang
    return get_resource_path("kiro_proxy/docs"), "zh"

@app.get("/api/docs")
async def api_docs_list():
    """获取文档列表"""
    docs_dir, lang = _get_docs_dir_for_lang()
    titles = DOC_TITLES.get(lang, DOC_TITLES["zh"])
    docs = []
    if docs_dir.exists():
        for doc_file in sorted(docs_dir.glob("*.md")):
            doc_id = doc_file.stem
            title = titles.get(doc_id, doc_id)
            docs.append({"id": doc_id, "title": title})
    return {"docs": docs}


@app.get("/api/docs/{doc_id}")
async def api_docs_content(doc_id: str):
    """获取文档内容"""
    docs_dir, lang = _get_docs_dir_for_lang()
    titles = DOC_TITLES.get(lang, DOC_TITLES["zh"])
    doc_file = docs_dir / f"{doc_id}.md"
    if not doc_file.exists():
        # 回退到默认目录
        fallback_dir = get_resource_path("kiro_proxy/docs")
        doc_file = fallback_dir / f"{doc_id}.md"
        if not doc_file.exists():
            error_msg = "Document not found" if lang == "en" else "文档不存在"
            raise HTTPException(status_code=404, detail=error_msg)
    content = doc_file.read_text(encoding="utf-8")
    title = titles.get(doc_id, doc_id)
    return {"id": doc_id, "title": title, "content": content}


# ==================== 启动 ====================

def run(port: int = 8080):
    import uvicorn
    from .core import state
    state.current_port = port  # 设置当前端口供 WebUI 显示
    print(f"\n{'='*50}")
    print(f"  Kiro API Proxy v1.7.16")
    print(f"  http://localhost:{port}")
    print(f"{'='*50}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run(port)
