"""Admin portal router — mounts on port 8081 main app.

All routes require a valid admin session cookie.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from . import db as portal_db
from .auth import verify_admin_session

router = APIRouter(prefix="/admin/api")


def _require_admin(request: Request):
    token = request.cookies.get("admin_session")
    if not token or not verify_admin_session(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/users")
async def list_users(request: Request):
    _require_admin(request)
    users = await portal_db.get_all_users()
    return {"users": users}


@router.post("/users")
async def create_user(request: Request):
    _require_admin(request)
    body = await request.json()
    sid = (body.get("student_id") or "").strip()
    pwd = (body.get("password") or "").strip()
    notes = (body.get("notes") or "").strip()
    total_tokens = int(body.get("total_tokens") or portal_db.DEFAULT_TOKEN_QUOTA)
    if not sid or not pwd:
        raise HTTPException(400, "学号和密码不能为空")
    result = await portal_db.create_user(sid, pwd)
    if result.get("ok"):
        # Update quota/notes if non-default
        users = await portal_db.get_all_users()
        user = next((u for u in users if u["student_id"] == sid), None)
        if user and (total_tokens != portal_db.DEFAULT_TOKEN_QUOTA or notes):
            await portal_db.update_user(user["id"], total_tokens=total_tokens, notes=notes)
    return result


@router.put("/users/{user_id}")
async def update_user(user_id: int, request: Request):
    _require_admin(request)
    body = await request.json()
    # Whitelist updatable fields
    allowed = {"total_tokens", "is_active", "notes", "display_name"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if "total_tokens" in updates:
        updates["total_tokens"] = int(updates["total_tokens"])
    if "is_active" in updates:
        updates["is_active"] = int(bool(updates["is_active"]))
    ok = await portal_db.update_user(user_id, **updates)
    return {"ok": ok}


@router.delete("/users/{user_id}")
async def deactivate_user(user_id: int, request: Request):
    """Deactivate (soft-delete) a user."""
    _require_admin(request)
    ok = await portal_db.update_user(user_id, is_active=0)
    return {"ok": ok}


@router.post("/users/{user_id}/activate")
async def activate_user(user_id: int, request: Request):
    _require_admin(request)
    ok = await portal_db.update_user(user_id, is_active=1)
    return {"ok": ok}


@router.get("/stats")
async def get_portal_stats(request: Request):
    _require_admin(request)
    stats = await portal_db.admin_get_stats()
    return stats


@router.get("/users/{user_id}/logs")
async def get_user_logs(user_id: int, request: Request, limit: int = 50, offset: int = 0):
    _require_admin(request)
    logs = await portal_db.get_logs(user_id, min(limit, 200), offset)
    return {"logs": logs}


# ─── Checkin API (admin) ───────────────────────────────────────────────────────

@router.get("/checkin/config")
async def admin_get_checkin_config(request: Request):
    _require_admin(request)
    config = await portal_db.get_checkin_config()
    return config


@router.post("/checkin/config")
async def admin_update_checkin_config(request: Request):
    _require_admin(request)
    body = await request.json()
    min_tokens = body.get("min_tokens")
    max_tokens = body.get("max_tokens")

    if min_tokens is None or max_tokens is None:
        raise HTTPException(400, "min_tokens 和 max_tokens 不能为空")

    try:
        min_tokens = int(min_tokens)
        max_tokens = int(max_tokens)
    except (ValueError, TypeError):
        raise HTTPException(400, "参数必须是整数")

    # Get admin username from session
    token = request.cookies.get("admin_session")
    admin_name = "admin"
    if token:
        admin_info = verify_admin_session(token)
        if admin_info:
            admin_name = admin_info.get("username", "admin")

    result = await portal_db.update_checkin_config(min_tokens, max_tokens, admin_name)
    return result


@router.get("/checkin/stats")
async def admin_checkin_stats(request: Request, days: int = 7):
    _require_admin(request)
    if days < 1 or days > 365:
        days = 7
    result = await portal_db.get_checkin_stats(days)
    return result

