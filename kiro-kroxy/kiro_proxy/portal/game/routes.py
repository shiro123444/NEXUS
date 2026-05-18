"""FastAPI routes for the game module.

All endpoints are mounted under /api/game by user_app.
Authentication is cookie-based via the shared require_user helper re-exported
from portal.user_app; we import lazily inside each route to avoid a circular
import at module load time.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import replace
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import achievements as game_achievements
from . import db as game_db
from . import engine as game_engine
from . import summarizer as game_summarizer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/game", tags=["game"])

# Per-run in-process lock. Prevents concurrent /act calls on the same run
# from producing two scenes with the same turn_idx (double-click, retry
# during slow stream, etc.). We don't GC this dict — runs are bounded and
# a Lock object is ~200B; at 10k runs that's 2MB, acceptable.
_RUN_LOCKS: dict[int, asyncio.Lock] = {}


def _run_lock(run_id: int) -> asyncio.Lock:
    lock = _RUN_LOCKS.get(run_id)
    if lock is None:
        lock = asyncio.Lock()
        _RUN_LOCKS[run_id] = lock
    return lock


def _require_user(request: Request) -> dict[str, Any]:
    """Thin wrapper to avoid circular import with user_app at module load."""
    from ..user_app import require_user  # noqa: WPS433 — deliberate lazy import

    return require_user(request)


def _require_admin(request: Request) -> dict[str, Any]:
    from ..user_app import require_admin  # noqa: WPS433 — deliberate lazy import

    return require_admin(request)


def _as_award_dicts(awards: list[Any]) -> list[dict[str, Any]]:
    """Awards are frozen dataclasses — flatten for SSE JSON."""
    return [
        {
            "kind": a.kind,
            "slug": a.slug,
            "title": a.title,
            "detail": a.detail,
            "payload": a.payload,
        }
        for a in awards
    ]


def _initial_state(world_bible: dict[str, Any]) -> dict[str, Any]:
    """Seed state from the generated world bible.

    Keys are narrative-friendly so the turn prompt can reason over them without
    needing schema knowledge — the LLM just reads/writes string values.
    """
    protagonist = (world_bible or {}).get("protagonist") or {}
    plot_spine = (world_bible or {}).get("plot_spine") or {}
    return {
        "location": "（未定）",
        "hp": "完好",
        "mood": "警觉",
        "inventory": [],
        "allies": [],
        "rivals": [],
        "protagonist_name": protagonist.get("name", ""),
        "goal": protagonist.get("goal", ""),
        "act": "opening",
        "tension": "低",
        "ending_pressure": "未进入终局",
        "active_thread": plot_spine.get("central_question", ""),
        "promised_payoff": plot_spine.get("opening_promise", ""),
        "ending_lean": "",
    }


# ── Read endpoints ────────────────────────────────────────────────────────────


@router.get("/genres")
async def get_genres() -> dict[str, Any]:
    """List all genre profiles (slug + display fields). Used by the揭幕 card."""
    from .prompts import GENRE_PROFILES

    return {
        "genres": [
            {
                "slug": p.slug,
                "name": p.name,
                "tagline": p.tagline,
                "setting": p.setting,
            }
            for p in GENRE_PROFILES.values()
        ]
    }


@router.get("/leaderboard")
async def get_leaderboard(
    request: Request,
    scope: str = "all",
    limit: int = 50,
    sort: str = "score",
) -> dict[str, Any]:
    """Unified leaderboard endpoint.

    sort in {score, cg} — run-based. Rows describe a single ended run.
    sort in {achievements, redeemed, gifts_sent, gifts_got} — user-based.
    Rows describe a player and include metric metrics across runs. The
    frontend picks a card template based on the presence of `run_id`.
    """
    RUN_SORTS = {"score", "cg"}
    USER_SORTS = {"achievements", "redeemed", "gifts_sent", "gifts_got"}
    sort_clean = sort if sort in RUN_SORTS | USER_SORTS else "score"
    limit_clean = max(1, min(int(limit or 50), 100))

    if sort_clean in USER_SORTS:
        rows = await game_db.leaderboard_users(sort=sort_clean, limit=limit_clean)
        entries = [
            {
                "user_id": r["user_id"],
                "display_name": r.get("display_name") or r.get("student_id") or "玩家",
                "achievement_count": int(r.get("achievement_count") or 0),
                "redeemed_usd": round(float(r.get("redeemed_usd") or 0.0), 4),
                "gifts_sent": int(r.get("gifts_sent") or 0),
                "gifts_got": int(r.get("gifts_got") or 0),
                "cg_count": int(r.get("cg_count") or 0),
            }
            for r in rows
        ]
        return {"scope": "all", "sort": sort_clean, "entries": entries, "kind": "user"}

    scope_clean = scope if scope in {"all", "weekly"} else "all"
    rows = await game_db.leaderboard_v2(scope=scope_clean, limit=limit_clean)
    if sort_clean == "cg":
        rows = sorted(rows, key=lambda r: int(r.get("cg_count") or 0), reverse=True)
    entries = [
        {
            "run_id": r["id"],
            "user_id": r["user_id"],
            "display_name": r.get("display_name") or r.get("student_id") or "玩家",
            "genre": r.get("genre"),
            "score": r["score"],
            "ending_slug": r.get("ending_slug"),
            "cover_url": r.get("cover_url"),
            "turns": r["turn_idx"],
            "ended_at": r.get("ended_at"),
            "cg_count": int(r.get("cg_count") or 0),
        }
        for r in rows
    ]
    return {"scope": scope_clean, "sort": sort_clean, "entries": entries, "kind": "run"}


@router.get("/gallery/me")
async def my_gallery(request: Request, genre: str | None = None) -> dict[str, Any]:
    user = _require_user(request)
    items = await game_db.list_user_gallery(user["uid"], genre=genre)
    summary = await game_db.gallery_summary(user["uid"])
    return {"items": items, "summary": summary}


@router.get("/gallery/{user_id}")
async def public_gallery(user_id: int, request: Request, genre: str | None = None) -> dict[str, Any]:
    # Authenticated peers can view each other's collection — origin attribution
    # is preserved on every item via origin_user_id + origin_display_name.
    _require_user(request)
    items = await game_db.list_user_gallery(int(user_id), genre=genre)
    summary = await game_db.gallery_summary(int(user_id))
    return {"items": items, "summary": summary}


@router.get("/achievements/me")
async def my_achievements(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    rows = await game_db.list_achievements(user["uid"])
    return {"entries": rows}


@router.get("/history")
async def get_history(request: Request, limit: int = 30) -> dict[str, Any]:
    user = _require_user(request)
    limit_clean = max(1, min(int(limit or 30), 100))
    rows = await game_db.list_history(user["uid"], limit=limit_clean)
    return {"entries": rows}


@router.get("/runs/active")
async def get_active_run(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    run = await game_db.get_active_run(user["uid"])
    return {"run": run}


@router.get("/runs/{run_id}")
async def get_run_detail(run_id: int, request: Request) -> dict[str, Any]:
    user = _require_user(request)
    run = await game_db.get_run(run_id, user_id=user["uid"])
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    scenes = await game_db.list_scenes(run_id, from_turn=0, limit=500)
    return {"run": run, "scenes": scenes}


@router.get("/runs/{run_id}/scenes")
async def get_run_scenes(run_id: int, request: Request, from_turn: int = 0) -> dict[str, Any]:
    user = _require_user(request)
    run = await game_db.get_run(run_id, user_id=user["uid"])
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    scenes = await game_db.list_scenes(run_id, from_turn=max(0, int(from_turn)), limit=500)
    return {"scenes": scenes}


# ── Write endpoints ──────────────────────────────────────────────────────────


@router.post("/runs")
async def start_run(request: Request) -> dict[str, Any]:
    """Create a new run, generate the world bible + opening scene + cover.

    Flow:
    1. Insert a row with status='generating' so a reload can't start a second run.
    2. Call the engine (Sonnet) to produce world bible + opening scene for a
       genre — random pick if the client didn't choose one.
    3. Persist bible + initial state + turn-0 scene.
    4. Try to generate the opening CG synchronously with a tight deadline so
       the first frame is already painted; fall back to fire-and-forget on
       timeout/failure (the frontend's scene-image poll will pick it up).
    5. Flip status to 'running' and return the run summary.
    """
    user = _require_user(request)
    active = await game_db.get_active_run(user["uid"])
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "active_run_exists", "run_id": active["id"]},
        )

    try:
        body = await request.json()
    except Exception:
        body = {}
    requested_genre = None
    if isinstance(body, dict):
        raw = body.get("genre")
        if isinstance(raw, str) and raw.strip():
            requested_genre = raw.strip()

    run_id = await game_db.create_run(user["uid"])
    logger.info(
        "game.start_run user=%s run=%s requested_genre=%s",
        user["uid"],
        run_id,
        requested_genre or "(random)",
    )

    try:
        recent_genres = [] if requested_genre else await game_db.recent_genres(user["uid"], limit=3)
        world_bible, opening, usage, profile = await game_engine.generate_world(
            genre=requested_genre,
            avoid_recent=recent_genres,
        )
    except Exception as exc:
        await game_db.update_run(
            run_id,
            status="abandoned",
            ended_at=datetime.now().isoformat(sep=" ", timespec="seconds"),
        )
        logger.exception("world gen failed run=%s: %s", run_id, exc)
        raise HTTPException(status_code=502, detail=f"世界生成失败：{exc}")

    wb_dict = world_bible.to_dict()
    # Make sure the profile slug is the source of truth — LLM may have echoed
    # something stale into <genre>. The wb_dict gets it back so frontend can
    # render the matching揭幕 card.
    wb_dict["genre"] = profile.slug
    state = _initial_state(wb_dict)

    await game_db.update_run(
        run_id,
        world_bible=wb_dict,
        character=wb_dict.get("protagonist") or {},
        current_state=state,
        genre=profile.slug,
        status="running",
        turn_idx=0,
        chapter_idx=1,
        total_tokens_in=usage["input_tokens"],
        total_tokens_out=usage["output_tokens"],
    )

    await game_db.insert_scene(
        run_id,
        0,
        is_keynote=True,
        narrative=opening.narrative,
        choices=[{"text": c} for c in opening.choices],
        player_action=None,
        state_delta={"state": state},
        visual_tag={"tag": opening.visual_tag, "art_style": wb_dict.get("art_style", "")},
        image_url=None,
        tokens_in=usage["input_tokens"],
        tokens_out=usage["output_tokens"],
    )

    # Block on the opening cover — generating it in parallel with returning
    # the /runs response used to give us a "text without art" flash that
    # felt like two disconnected products. Now the client gets the run only
    # after the first frame is already painted. 90s hard cap so a wedged
    # upstream doesn't leave the client waiting forever; we still fall back
    # to fire-and-forget past that bound.
    cover_ready = False
    try:
        url, _cost, _hit = await asyncio.wait_for(
            game_engine.generate_pixel_image(
                opening.visual_tag, wb_dict.get("art_style", ""), kind="cover"
            ),
            timeout=90.0,
        )
        if not url:
            raise RuntimeError("cover image generation returned empty url")
        await game_db.update_run(run_id, cover_url=url)
        turn0_scenes = await game_db.list_scenes(run_id, from_turn=0, limit=1)
        if turn0_scenes:
            scene_id_0 = int(turn0_scenes[0]["id"])
            await game_db.update_scene_image(scene_id_0, url)
            await _grant_origin_ownership(scene_id_0)
        cover_ready = True
        logger.info("game.preheat cover ready run=%s", run_id)
    except asyncio.TimeoutError:
        logger.warning("game.preheat cover timeout run=%s — deferring", run_id)
    except Exception as exc:
        logger.warning("game.preheat cover failed run=%s: %s", run_id, exc)

    if not cover_ready:
        asyncio.create_task(
            _generate_cover_async(run_id, opening.visual_tag, wb_dict.get("art_style", ""))
        )

    run = await game_db.get_run(run_id, user_id=user["uid"])
    scenes = await game_db.list_scenes(run_id, from_turn=0, limit=5)
    return {"run": run, "scenes": scenes}


async def _generate_cover_async(run_id: int, visual_tag: str, art_style: str) -> None:
    try:
        url, _cost, _hit = await game_engine.generate_pixel_image(visual_tag, art_style, kind="cover")
        if not url:
            raise RuntimeError("cover image generation returned empty url")
        await game_db.update_run(run_id, cover_url=url)
        # Tag the turn-0 scene + grant origin ownership so the cover is also
        # the first CG in the user's gallery.
        turn0_scenes = await game_db.list_scenes(run_id, from_turn=0, limit=1)
        if turn0_scenes:
            scene_id_0 = int(turn0_scenes[0]["id"])
            await game_db.update_scene_image(scene_id_0, url)
            await _grant_origin_ownership(scene_id_0)
        logger.info("game.cover run=%s url=%s", run_id, url)
    except Exception as exc:
        logger.warning("game.cover failed run=%s: %s", run_id, exc)


@router.post("/runs/{run_id}/act")
async def act_on_run(run_id: int, request: Request) -> StreamingResponse:
    """Advance the story by one turn via Server-Sent Events.

    Validation errors (404/409/400) are raised before the stream opens so they
    surface as proper HTTP status codes. Once the stream opens, protocol is:
      - ``event: start`` with the projected new turn_idx
      - ``event: delta`` per narrative fragment as Haiku streams
      - ``event: meta`` with the persisted ``{run, scene}`` after upstream close
      - ``event: done`` final
      - ``event: error`` on any failure (replaces done)

    No retry on parse failure — a mid-stream retry would re-emit narrative.
    """
    user = _require_user(request)
    run = await game_db.get_run(run_id, user_id=user["uid"])
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run["status"] != "running":
        raise HTTPException(status_code=409, detail="run is not active")

    try:
        payload = await request.json()
    except Exception:
        payload = {}
    action = (payload.get("action") or "").strip() if isinstance(payload, dict) else ""
    if not action:
        raise HTTPException(status_code=400, detail="action is required")
    if len(action) > 400:
        raise HTTPException(status_code=400, detail="action is too long")

    uid = user["uid"]
    expected_turn_idx = int(run["turn_idx"])
    lock = _run_lock(run_id)

    def _sse(event: str, data: dict[str, Any]) -> bytes:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode(
            "utf-8"
        )

    async def event_gen() -> Any:
        try:
            async with lock:
                # Re-read the run inside the lock. A concurrent /act (double-
                # click, retry) may have already advanced turn_idx or ended
                # the run; in that case surface a clean error instead of
                # burning a second LLM call and producing a dup scene.
                latest = await game_db.get_run(run_id, user_id=uid)
                if latest is None:
                    yield _sse("error", {"detail": "run not found"})
                    return
                if latest["status"] != "running":
                    yield _sse("error", {"detail": "run is not active"})
                    return
                if int(latest["turn_idx"]) != expected_turn_idx:
                    yield _sse(
                        "error",
                        {
                            "detail": "run已被其它请求推进，请刷新后重试",
                            "code": "turn_advanced",
                            "current_turn_idx": int(latest["turn_idx"]),
                        },
                    )
                    return

                # Memory for the turn prompt =
                #   past_chapters: 所有已经落盘的章节摘要（来自 game_summaries）
                #   recent_turns:  最近 3 回合的原文（未被摘要覆盖的尾巴）
                summaries = await game_db.list_summaries(run_id)
                last_summarized_turn = max(
                    (int(s["covers_turn_to"]) for s in summaries), default=-1
                )
                tail_from = max(last_summarized_turn + 1, expected_turn_idx - 2)
                recent_scenes = await game_db.list_scenes(
                    run_id, from_turn=max(0, tail_from), limit=4
                )
                recent_summary = game_summarizer.format_memory_for_prompt(
                    summaries, recent_scenes
                )

                current_state = latest.get("current_state") or {}
                world_bible = latest.get("world_bible") or {}
                new_turn_idx = expected_turn_idx + 1
                art_style = world_bible.get("art_style", "")

                yield _sse("start", {"turn_idx": new_turn_idx})

                # We start image generation the moment the model closes the
                # <visual_tag> block — that fires well before the final event,
                # so the image pipeline runs in parallel with the rest of the
                # narrative stream. scene_id isn't known yet though (it only
                # gets assigned after commit_turn), so the image task waits
                # for this future before writing image_url + granting origin.
                scene_id_future: asyncio.Future[int] = asyncio.get_event_loop().create_future()
                image_task: asyncio.Task[None] | None = None

                final_result = None
                final_usage = {"input_tokens": 0, "output_tokens": 0}
                async for ev in game_engine.generate_turn_stream(
                    world_bible=world_bible,
                    current_state=current_state,
                    recent_summary=recent_summary,
                    player_action=action,
                    turn_idx=new_turn_idx,
                ):
                    et = ev.get("type")
                    if et == "narrative":
                        text = ev.get("text") or ""
                        if text:
                            yield _sse("delta", {"text": text})
                    elif et == "visual_tag":
                        tag = ev.get("tag") or ""
                        if tag and image_task is None:
                            image_task = asyncio.create_task(
                                _generate_scene_image_deferred(
                                    scene_id_future, tag, art_style
                                )
                            )
                    elif et == "final":
                        final_result = ev.get("result")
                        final_usage = ev.get("usage") or final_usage

                if final_result is None:
                    # Cancel the speculative image task — the stream never
                    # produced a usable turn so committing a dangling image
                    # would leak.
                    if image_task is not None:
                        scene_id_future.cancel()
                        image_task.cancel()
                    raise RuntimeError("stream ended without a final turn result")

                if (
                    new_turn_idx >= game_engine.GAME_MAX_TURNS
                    and not final_result.ending_slug
                ):
                    final_result = replace(
                        final_result,
                        choices=[],
                        ending_slug="deadline_closure",
                        ending_text=(
                            final_result.narrative.strip()
                            or "故事在此刻收束。你接受已经发生的一切，也承担此前选择留下的代价。"
                        ),
                        beat_kind="ending",
                        is_keynote=True,
                    )

                new_state = game_engine.apply_state_delta(
                    current_state, final_result.state_delta
                )
                current_codex = latest.get("codex") or {}
                new_codex = game_engine.apply_codex_delta(
                    current_codex, final_result.codex_delta, turn_idx=new_turn_idx
                )

                run_updates: dict[str, Any] = {
                    "current_state": new_state,
                    "codex": new_codex,
                    "turn_idx": new_turn_idx,
                    "total_tokens_in": int(latest["total_tokens_in"])
                    + final_usage["input_tokens"],
                    "total_tokens_out": int(latest["total_tokens_out"])
                    + final_usage["output_tokens"],
                }
                if final_result.ending_slug:
                    run_updates["ending_slug"] = final_result.ending_slug
                    run_updates["ending_text"] = final_result.ending_text or ""
                    run_updates["status"] = "ended"
                    run_updates["ended_at"] = datetime.now().isoformat(
                        sep=" ", timespec="seconds"
                    )
                    run_updates["score"] = game_engine.compute_score(
                        new_turn_idx, final_result.ending_slug
                    )

                # Atomic: scene INSERT + run UPDATE in one transaction.
                scene_id = await game_db.commit_turn(
                    run_id,
                    scene={
                        "turn_idx": new_turn_idx,
                        "is_keynote": final_result.is_keynote,
                        "narrative": final_result.narrative,
                        "choices": [{"text": c} for c in final_result.choices],
                        "player_action": action,
                        "state_delta": final_result.state_delta,
                        "visual_tag": {
                            "tag": final_result.visual_tag,
                            "art_style": art_style,
                        },
                        "image_url": None,
                        "tokens_in": final_usage["input_tokens"],
                        "tokens_out": final_usage["output_tokens"],
                    },
                    run_updates=run_updates,
                )

                # 章节摘要：触发后 chapter_idx 向前走一格，turn prompt 下一轮就会
                # 拿到完整的历史压缩。摘要失败不阻塞玩家 —— maybe_summarize 内部吞异常。
                new_summary = await game_summarizer.maybe_summarize(
                    run_id=run_id,
                    chapter_idx=int(latest.get("chapter_idx") or 1) + 1,
                    turn_idx=new_turn_idx,
                    is_keynote=bool(final_result.is_keynote),
                )
                if new_summary is not None:
                    await game_db.update_run(
                        run_id, chapter_idx=int(new_summary["chapter_idx"])
                    )

                if final_result.visual_tag:
                    if image_task is None:
                        # Model didn't close <visual_tag> mid-stream (rare —
                        # maybe truncated upstream). Fall back to the classic
                        # "fire after commit" path so we still get an image.
                        asyncio.create_task(
                            _generate_scene_image_async(
                                scene_id, final_result.visual_tag, art_style
                            )
                        )
                    else:
                        # Unblock the early-started image task so it can write
                        # image_url once the upstream image generation
                        # finishes.
                        if not scene_id_future.done():
                            scene_id_future.set_result(scene_id)
                elif image_task is not None:
                    # Final parse disagreed with the streaming extractor —
                    # tear down the orphan job.
                    scene_id_future.cancel()
                    image_task.cancel()

                # M5: achievement checks. Pioneer + collector on ending; hidden
                # rules every turn. Awards become a `meta.awards` array so the
                # frontend can flash a toast.
                granted: list[dict[str, Any]] = []
                try:
                    if final_result.ending_slug:
                        end_genre = (
                            (latest.get("world_bible") or {}).get("genre")
                            or latest.get("genre")
                            or "xianxia"
                        )
                        end_awards = await game_achievements.check_on_ending(
                            user_id=uid,
                            run_id=run_id,
                            genre=end_genre,
                            ending_slug=final_result.ending_slug,
                        )
                        new_ones = await game_achievements.commit_awards(
                            uid, end_awards
                        )
                        granted.extend(_as_award_dicts(new_ones))

                    # Hidden rules look at scenes_so_far including the new one.
                    scenes_so_far = await game_db.list_scenes(
                        run_id, from_turn=0, limit=max(8, new_turn_idx + 1)
                    )
                    turn_awards = await game_achievements.check_on_turn(
                        user_id=uid,
                        run_id=run_id,
                        turn_idx=new_turn_idx,
                        scenes_so_far=scenes_so_far,
                    )
                    new_ones = await game_achievements.commit_awards(uid, turn_awards)
                    granted.extend(_as_award_dicts(new_ones))
                except Exception as exc:
                    logger.warning(
                        "game.achievement_check failed run=%s: %s", run_id, exc
                    )

                fresh_run = await game_db.get_run(run_id, user_id=uid)
                scenes_tail = await game_db.list_scenes(
                    run_id, from_turn=new_turn_idx, limit=1
                )
                scene = scenes_tail[0] if scenes_tail else None
                yield _sse(
                    "meta", {"run": fresh_run, "scene": scene, "awards": granted}
                )
                yield _sse("done", {})
        except Exception as exc:
            logger.exception("game.turn_stream failed run=%s: %s", run_id, exc)
            yield _sse("error", {"detail": str(exc)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _generate_scene_image_async(scene_id: int, visual_tag: str, art_style: str) -> None:
    try:
        url, _cost, _hit = await game_engine.generate_pixel_image(
            visual_tag, art_style, kind="scene"
        )
        if not url:
            raise RuntimeError("scene image generation returned empty url")
        await game_db.update_scene_image(scene_id, url)
        logger.info("game.scene_image scene=%s url=%s", scene_id, url)
        # M5: auto-grant ownership to the run's owner (origin) and surface
        # any collector achievements that just unlocked.
        await _grant_origin_ownership(scene_id)
    except Exception as exc:
        logger.warning("game.scene_image failed scene=%s: %s", scene_id, exc)


async def _generate_scene_image_deferred(
    scene_id_future: asyncio.Future[int], visual_tag: str, art_style: str
) -> None:
    """Start image generation now, write it once ``scene_id`` is known.

    Called speculatively from ``act_on_run`` as soon as the model emits
    ``<visual_tag>`` — this lets the image pipeline run in parallel with the
    rest of the narrative stream. If ``commit_turn`` eventually cancels the
    future (parse failure, mid-stream teardown), we log and drop the image.
    """
    try:
        url, _cost, _hit = await game_engine.generate_pixel_image(
            visual_tag, art_style, kind="scene"
        )
        if not url:
            raise RuntimeError("scene image generation returned empty url")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("game.scene_image early gen failed tag=%r: %s", visual_tag, exc)
        return
    try:
        scene_id = await scene_id_future
    except asyncio.CancelledError:
        logger.info(
            "game.scene_image generated but scene cancelled tag=%r url=%s",
            visual_tag,
            url,
        )
        return
    try:
        await game_db.update_scene_image(scene_id, url)
        logger.info("game.scene_image (early) scene=%s url=%s", scene_id, url)
        await _grant_origin_ownership(scene_id)
    except Exception as exc:
        logger.warning("game.scene_image persist failed scene=%s: %s", scene_id, exc)


async def _grant_origin_ownership(scene_id: int) -> None:
    """Insert origin-source CG ownership and run collector-tier checks."""
    info = await game_db.get_scene_run_owner(scene_id)
    if not info or not info.get("owner_id"):
        return
    owner_id = int(info["owner_id"])
    rarity = "rare" if info.get("is_keynote") else "common"
    created = await game_db.grant_ownership(
        owner_id, scene_id, owner_id, source="origin", rarity=rarity
    )
    if created:
        new_awards = await game_achievements.commit_awards(
            owner_id,
            await game_achievements.check_on_ownership_grant(user_id=owner_id),
        )
        for a in new_awards:
            logger.info("achievement (gallery) user=%s slug=%s", owner_id, a.slug)


@router.post("/runs/{run_id}/abandon")
async def abandon_run(run_id: int, request: Request) -> dict[str, Any]:
    user = _require_user(request)
    run = await game_db.get_run(run_id, user_id=user["uid"])
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run["status"] not in {"generating", "running"}:
        return {"ok": True, "already_ended": True}

    await game_db.update_run(
        run_id,
        status="abandoned",
        ended_at=datetime.now().isoformat(sep=" ", timespec="seconds"),
    )
    return {"ok": True}


# ─── M6: Gifts & redemption ───────────────────────────────────────────────────

GIFT_DAILY_LIMIT = 20
GIFT_MESSAGE_MAX = 140


@router.get("/reward-pool")
async def get_reward_pool(request: Request) -> dict[str, Any]:
    """Public view of the reward pool — lets the achievements screen show
    "当前奖池：$12.34 / 已发放 $3.21" so redemption pressure is legible.
    """
    _require_user(request)
    return await game_db.get_reward_pool()


@router.post("/achievements/{achievement_id}/redeem")
async def redeem_achievement(achievement_id: int, request: Request) -> dict[str, Any]:
    user = _require_user(request)
    try:
        result = await game_db.redeem_achievement(
            int(achievement_id), int(user["uid"])
        )
    except ValueError as exc:
        payload = exc.args[0] if exc.args else {"code": "unknown"}
        code = payload.get("code") if isinstance(payload, dict) else str(payload)
        status_map = {
            "not_found": 404,
            "already_redeemed": 409,
            "not_redeemable": 422,
            "pool_empty": 503,
        }
        raise HTTPException(
            status_code=status_map.get(code, 400),
            detail={"code": code, **(payload if isinstance(payload, dict) else {})},
        )
    return result


@router.get("/users/lookup")
async def lookup_user(
    request: Request,
    student_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Resolve a student_id or display_name → user(s).

    By student_id: returns a single match (exact).
    By display_name: returns up to 10 fuzzy matches.
    """
    _require_user(request)

    # name-based fuzzy search
    q = (name or "").strip()
    if q:
        found = await game_db.find_user_by_display_name(q)
        return {
            "matches": [
                {
                    "user_id": int(r["id"]),
                    "student_id": r["student_id"],
                    "display_name": r.get("display_name") or r["student_id"],
                }
                for r in found
            ]
        }

    # legacy student_id exact match
    sid = (student_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="name or student_id required")
    found = await game_db.find_user_by_student_id(sid)
    if found is None:
        raise HTTPException(status_code=404, detail="user not found")
    return {
        "user_id": int(found["id"]),
        "student_id": found["student_id"],
        "display_name": found.get("display_name") or found["student_id"],
    }


@router.post("/gifts")
async def send_gift(request: Request) -> dict[str, Any]:
    """Gift one CG to another user.

    Body:
      {
        "scene_id": int,                   # CG the sender owns
        "to_student_id": "..."  OR
        "to_user_id": int,
        "message": "..."        (<=140 chars, optional)
      }

    Rate-limited per-day. All transfer rules live in
    ``game_db.transfer_cg_gift``.
    """
    user = _require_user(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be JSON object")

    try:
        scene_id = int(body.get("scene_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="scene_id required")

    to_user_id: int | None = None
    raw_to_uid = body.get("to_user_id")
    if isinstance(raw_to_uid, (int, str)) and str(raw_to_uid).strip():
        try:
            to_user_id = int(raw_to_uid)
        except ValueError:
            to_user_id = None

    to_student = body.get("to_student_id")
    if to_user_id is None and isinstance(to_student, str) and to_student.strip():
        found = await game_db.find_user_by_student_id(to_student.strip())
        if found is None:
            raise HTTPException(status_code=404, detail="recipient not found")
        to_user_id = int(found["id"])

    if to_user_id is None:
        raise HTTPException(status_code=400, detail="to_user_id or to_student_id required")

    if to_user_id == int(user["uid"]):
        raise HTTPException(status_code=400, detail={"code": "self_gift"})

    message = body.get("message")
    if isinstance(message, str) and len(message) > GIFT_MESSAGE_MAX:
        raise HTTPException(
            status_code=400,
            detail={"code": "message_too_long", "max": GIFT_MESSAGE_MAX},
        )

    sent_today = await game_db.count_gifts_sent_today(int(user["uid"]))
    if sent_today >= GIFT_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "rate_limited",
                "limit": GIFT_DAILY_LIMIT,
                "reset": "today",
            },
        )

    try:
        result = await game_db.transfer_cg_gift(
            from_user_id=int(user["uid"]),
            to_user_id=to_user_id,
            scene_id=scene_id,
            message=message if isinstance(message, str) else None,
        )
    except ValueError as exc:
        payload = exc.args[0] if exc.args else {"code": "unknown"}
        code = payload.get("code") if isinstance(payload, dict) else str(payload)
        status_map = {
            "self_gift": 400,
            "not_owned": 403,
            "not_transferable": 403,
            "already_owned": 409,
        }
        raise HTTPException(
            status_code=status_map.get(code, 400),
            detail={"code": code, **(payload if isinstance(payload, dict) else {})},
        )

    logger.info(
        "game.gift from=%s to=%s scene=%s transfer=%s",
        user["uid"],
        to_user_id,
        scene_id,
        result.get("transfer_id"),
    )
    return result


@router.get("/gifts/sent")
async def list_gifts_sent(request: Request, limit: int = 50) -> dict[str, Any]:
    user = _require_user(request)
    limit_clean = max(1, min(int(limit or 50), 200))
    items = await game_db.list_transfers(int(user["uid"]), "sent", limit_clean)
    return {"direction": "sent", "items": items}


@router.get("/gifts/received")
async def list_gifts_received(request: Request, limit: int = 50) -> dict[str, Any]:
    user = _require_user(request)
    limit_clean = max(1, min(int(limit or 50), 200))
    items = await game_db.list_transfers(int(user["uid"]), "received", limit_clean)
    return {"direction": "received", "items": items}


# ─── M6 · PR2: trade offers ───────────────────────────────────────────────────


def _offer_error_to_http(exc: ValueError) -> HTTPException:
    payload = exc.args[0] if exc.args else {"code": "unknown"}
    code = payload.get("code") if isinstance(payload, dict) else str(payload)
    status_map = {
        # create
        "self_trade": 400,
        "empty_offer": 400,
        "too_many_items": 400,
        "duplicate_items": 400,
        "too_many_active": 429,
        "not_owned": 403,
        "not_owned_by_target": 422,
        "not_transferable": 403,
        # respond
        "not_found": 404,
        "wrong_role": 403,
        "already_responded": 409,
        "expired": 410,
        "not_owned_anymore": 409,
        "already_owned": 409,
        "bad_action": 400,
    }
    return HTTPException(
        status_code=status_map.get(code, 400),
        detail={"code": code, **(payload if isinstance(payload, dict) else {})},
    )


@router.post("/trades")
async def create_trade(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be JSON object")

    # Resolve recipient — students can send by student_id (friendlier) or
    # user_id (useful for bots / admin tools / the frontend's lookup flow).
    to_user_id: int | None = None
    raw_uid = body.get("to_user_id")
    if isinstance(raw_uid, (int, str)) and str(raw_uid).strip():
        try:
            to_user_id = int(raw_uid)
        except ValueError:
            to_user_id = None
    sid = body.get("to_student_id")
    if to_user_id is None and isinstance(sid, str) and sid.strip():
        found = await game_db.find_user_by_student_id(sid.strip())
        if found is None:
            raise HTTPException(status_code=404, detail="recipient not found")
        to_user_id = int(found["id"])
    if to_user_id is None:
        raise HTTPException(status_code=400, detail="to_user_id or to_student_id required")

    def _as_id_list(v: Any) -> list[int]:
        if not isinstance(v, list):
            return []
        out: list[int] = []
        for x in v:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                pass
        return out

    offered = _as_id_list(body.get("offered_scene_ids"))
    wanted = _as_id_list(body.get("wanted_scene_ids"))
    message = body.get("message")
    if isinstance(message, str) and len(message) > 140:
        raise HTTPException(
            status_code=400, detail={"code": "message_too_long", "max": 140}
        )

    try:
        result = await game_db.create_trade_offer(
            from_user_id=int(user["uid"]),
            to_user_id=to_user_id,
            offered_ids=offered,
            wanted_ids=wanted,
            message=message if isinstance(message, str) else None,
        )
    except ValueError as exc:
        raise _offer_error_to_http(exc)

    logger.info(
        "game.trade created offer=%s from=%s to=%s offered=%s wanted=%s",
        result.get("offer_id"), user["uid"], to_user_id, offered, wanted,
    )
    return result


@router.get("/trades/incoming")
async def list_trades_incoming(request: Request, limit: int = 50) -> dict[str, Any]:
    user = _require_user(request)
    lim = max(1, min(int(limit or 50), 200))
    items = await game_db.list_trade_offers(int(user["uid"]), scope="incoming", limit=lim)
    return {"scope": "incoming", "items": items}


@router.get("/trades/outgoing")
async def list_trades_outgoing(request: Request, limit: int = 50) -> dict[str, Any]:
    user = _require_user(request)
    lim = max(1, min(int(limit or 50), 200))
    items = await game_db.list_trade_offers(int(user["uid"]), scope="outgoing", limit=lim)
    return {"scope": "outgoing", "items": items}


@router.get("/trades/history")
async def list_trades_history(request: Request, limit: int = 100) -> dict[str, Any]:
    user = _require_user(request)
    lim = max(1, min(int(limit or 100), 200))
    items = await game_db.list_trade_offers(int(user["uid"]), scope="history", limit=lim)
    return {"scope": "history", "items": items}


@router.get("/trades/{offer_id}")
async def get_trade(offer_id: int, request: Request) -> dict[str, Any]:
    user = _require_user(request)
    offer = await game_db.get_trade_offer(int(offer_id), int(user["uid"]))
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    return {"offer": offer}


async def _respond_trade(request: Request, offer_id: int, action: str) -> dict[str, Any]:
    user = _require_user(request)
    try:
        result = await game_db.respond_trade_offer(
            offer_id=int(offer_id), user_id=int(user["uid"]), action=action
        )
    except ValueError as exc:
        raise _offer_error_to_http(exc)
    logger.info(
        "game.trade %s offer=%s user=%s result=%s",
        action, offer_id, user["uid"], result,
    )
    return result


@router.post("/trades/{offer_id}/accept")
async def accept_trade(offer_id: int, request: Request) -> dict[str, Any]:
    return await _respond_trade(request, offer_id, "accept")


@router.post("/trades/{offer_id}/reject")
async def reject_trade(offer_id: int, request: Request) -> dict[str, Any]:
    return await _respond_trade(request, offer_id, "reject")


@router.post("/trades/{offer_id}/cancel")
async def cancel_trade(offer_id: int, request: Request) -> dict[str, Any]:
    return await _respond_trade(request, offer_id, "cancel")


# ─── M6: Admin — reward pool management ───────────────────────────────────────


@router.post("/admin/reward-pool/topup")
async def admin_topup_reward_pool(request: Request) -> dict[str, Any]:
    """Admin-only: fund the reward pool by debiting an existing user's
    balance_usd.

    Body:
      {"from_student_id": "<sid>", "amount_usd": <float>}
      — or —
      {"from_user_id": <int>, "amount_usd": <float>}

    The balance transfer is atomic: rejects with 400 ``insufficient_balance``
    when the donor doesn't have enough to cover ``amount_usd``. Negative
    amounts are rejected (use a future /drain endpoint if we ever need to
    shrink the pool — doing it here would silently return money without a
    clean trail of who received it).
    """
    _require_admin(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be JSON object")

    try:
        amount = float(body.get("amount_usd"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="amount_usd required")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount_usd must be > 0")

    from_uid: int | None = None
    raw_uid = body.get("from_user_id")
    if isinstance(raw_uid, (int, str)) and str(raw_uid).strip():
        try:
            from_uid = int(raw_uid)
        except ValueError:
            from_uid = None
    sid = body.get("from_student_id")
    if from_uid is None and isinstance(sid, str) and sid.strip():
        found = await game_db.find_user_by_student_id(sid.strip())
        if found is None:
            raise HTTPException(status_code=404, detail="donor user not found")
        from_uid = int(found["id"])
    if from_uid is None:
        raise HTTPException(
            status_code=400, detail="from_user_id or from_student_id required"
        )

    try:
        pool = await game_db.topup_reward_pool(amount, from_user_id=from_uid)
    except ValueError as exc:
        payload = exc.args[0] if exc.args else {"code": "unknown"}
        code = payload.get("code") if isinstance(payload, dict) else str(payload)
        status_map = {
            "insufficient_balance": 400,
            "user_not_found": 404,
        }
        raise HTTPException(
            status_code=status_map.get(code, 400),
            detail={"code": code, **(payload if isinstance(payload, dict) else {})},
        )
    logger.info("game.reward_pool topup from_uid=%s amount=%.4f pool=%s", from_uid, amount, pool)
    return {"ok": True, "pool": pool, "from_user_id": from_uid, "amount_usd": amount}


# ─── M7: Marketplace ─────────────────────────────────────────────────────────


def _listing_error_to_http(exc: ValueError) -> HTTPException:
    payload = exc.args[0] if exc.args else {"code": "unknown"}
    code = payload.get("code") if isinstance(payload, dict) else str(payload)
    status_map = {
        "not_owned": 400,
        "pioneer_locked": 403,
        "bad_price": 400,
        "not_found": 404,
        "not_seller": 403,
        "already_resolved": 400,
        "already_sold": 400,
        "self_buy": 400,
        "insufficient_balance": 400,
    }
    return HTTPException(
        status_code=status_map.get(code, 400),
        detail={"code": code, **(payload if isinstance(payload, dict) else {})},
    )


@router.post("/marketplace")
async def create_market_listing(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be JSON object")

    scene_id = body.get("scene_id")
    if not isinstance(scene_id, (int, str)) or not str(scene_id).strip():
        raise HTTPException(status_code=400, detail="scene_id required")
    try:
        scene_id = int(scene_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="scene_id must be int")

    try:
        price = float(body.get("price_usd"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="price_usd required")
    if price <= 0:
        raise HTTPException(status_code=400, detail="price_usd must be > 0")

    message = body.get("message")
    if isinstance(message, str) and len(message) > 140:
        raise HTTPException(status_code=400, detail="message too long")

    try:
        result = await game_db.create_listing(
            seller_id=int(user["uid"]),
            scene_id=scene_id,
            price_usd=price,
            message=message if isinstance(message, str) else None,
        )
    except ValueError as exc:
        raise _listing_error_to_http(exc)

    logger.info("game.marketplace created listing=%s seller=%s scene=%s price=%.2f",
                result.get("listing_id"), user["uid"], scene_id, price)
    return result


@router.get("/marketplace")
async def list_market(request: Request, scope: str = "all", limit: int = 50) -> dict[str, Any]:
    user = _require_user(request)
    lim = max(1, min(int(limit or 50), 200))
    uid = int(user["uid"]) if scope in ("my", "bought") else None
    items = await game_db.list_marketplace(user_id=uid, scope=scope, limit=lim)
    return {"scope": scope, "items": items}


@router.post("/marketplace/{listing_id}/buy")
async def buy_market_listing(listing_id: int, request: Request) -> dict[str, Any]:
    user = _require_user(request)
    try:
        result = await game_db.buy_listing(int(user["uid"]), int(listing_id))
    except ValueError as exc:
        raise _listing_error_to_http(exc)
    logger.info("game.marketplace buy listing=%s buyer=%s", listing_id, user["uid"])
    return result


@router.post("/marketplace/{listing_id}/cancel")
async def cancel_market_listing(listing_id: int, request: Request) -> dict[str, Any]:
    user = _require_user(request)
    try:
        result = await game_db.cancel_listing(int(user["uid"]), int(listing_id))
    except ValueError as exc:
        raise _listing_error_to_http(exc)
    logger.info("game.marketplace cancel listing=%s seller=%s", listing_id, user["uid"])
    return result


# ─── M7: Admin — reward config ───────────────────────────────────────────────


@router.get("/admin/rewards")
async def admin_list_rewards(request: Request) -> dict[str, Any]:
    _require_admin(request)
    from . import rewards as rewards_mod
    overrides = await game_db.get_reward_overrides()
    return {
        "overrides": overrides,
        "defaults": {
            "pioneer": rewards_mod.PIONEER_USD,
            "cg:5": rewards_mod.CG_TIER_USD.get(5, 0),
            "cg:15": rewards_mod.CG_TIER_USD.get(15, 0),
            "cg:30": rewards_mod.CG_TIER_USD.get(30, 0),
            "genre_endings": rewards_mod.GENRE_ENDINGS_USD,
            "multigenre:3": rewards_mod.MULTIGENRE_3_USD,
            "total:50": rewards_mod.TOTAL_TIER_USD.get(50, 0),
            "total:200": rewards_mod.TOTAL_TIER_USD.get(200, 0),
            "hidden": rewards_mod.HIDDEN_USD,
        },
    }


@router.post("/admin/rewards")
async def admin_set_reward(request: Request) -> dict[str, Any]:
    _require_admin(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be JSON object")

    slug = (body.get("slug") or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug required")
    try:
        reward = float(body.get("reward_usd"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="reward_usd required")
    if reward < 0:
        raise HTTPException(status_code=400, detail="reward_usd must be >= 0")

    result = await game_db.admin_set_reward(slug, reward)
    # Refresh in-memory cache
    overrides = await game_db.get_reward_overrides()
    from . import rewards as rewards_mod
    rewards_mod.set_overrides(overrides)
    logger.info("game.admin set_reward slug=%s reward=%.2f", slug, reward)
    return result
