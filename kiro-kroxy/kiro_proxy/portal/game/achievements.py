"""Achievement engine — pure functions + db effects.

Three families:
  * pioneer  — first user to land a (genre, ending_slug) combo.
                Uses pioneer_locks for atomic "first wins" semantics.
  * collector — N CG owned in a single genre (10 / 25), or all known endings
                for one genre in their gallery.
  * hidden   — narrative pattern detectors (e.g. survived 8 turns without
                fighting). Two示范 rules wired in for now.

Each rule returns a (slug, title, detail, kind, payload) tuple via
``Award`` so the dispatcher can INSERT-OR-IGNORE through db.award_achievement.

Routes call:
  * ``check_on_ending(...)``  after a run ends
  * ``check_on_ownership_grant(...)`` after a new CG ownership row lands
  * ``check_on_turn(...)`` after each turn persists
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from . import db as game_db
from .prompts import GENRE_PROFILES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Award:
    kind: str
    slug: str
    title: str
    detail: str
    payload: dict[str, Any]


# Collector thresholds — easy to tweak without touching the rule code below.
GENRE_COLLECTOR_TIERS: tuple[tuple[int, str], ...] = (
    (5, "初学的猎人"),
    (15, "执着的搜集"),
    (30, "题材通鉴"),
)


def _genre_name(slug: str) -> str:
    profile = GENRE_PROFILES.get(slug)
    return profile.name if profile else slug


# ─── Triggers ────────────────────────────────────────────────────────────────


async def check_on_ending(
    *, user_id: int, run_id: int, genre: str, ending_slug: str
) -> list[Award]:
    """Run after `routes.act_on_run` flips status='ended'.

    Pioneer claim is global-atomic (sqlite UNIQUE on slug). Collector
    "全 ending" check counts user's distinct (genre, ending) pairs.
    """
    awarded: list[Award] = []
    if not ending_slug:
        return awarded

    pioneer_slug = f"pioneer:{genre}:{ending_slug}"
    if await game_db.try_claim_pioneer(pioneer_slug, user_id, run_id):
        awarded.append(
            Award(
                kind="pioneer",
                slug=pioneer_slug,
                title=f"首登 · {_genre_name(genre)} · {ending_slug}",
                detail=f"全站第一个抵达【{_genre_name(genre)}】的『{ending_slug}』结局。",
                payload={"genre": genre, "ending": ending_slug, "run_id": run_id},
            )
        )

    # Collector: 完成同一题材内的所有"已知"结局 (从 world_bible.possible_endings 里取).
    by_genre = await game_db.count_user_endings(user_id)
    user_endings = by_genre.get(genre, set())
    if len(user_endings) >= 4:
        # 4+ distinct endings in the same genre — without needing to read each
        # run's wb to know whether it's "all" of them. Treat 4 as the bar.
        slug = f"collector:endings:{genre}"
        awarded.append(
            Award(
                kind="collector",
                slug=slug,
                title=f"题材通晓 · {_genre_name(genre)}",
                detail=f"在【{_genre_name(genre)}】走出了 {len(user_endings)} 种不同结局。",
                payload={"genre": genre, "endings": sorted(user_endings)},
            )
        )

    # 跨题材集邮：曾抵达 6 个题材中至少 3 个的结局.
    distinct_genres = sum(1 for v in by_genre.values() if v)
    if distinct_genres >= 3:
        awarded.append(
            Award(
                kind="collector",
                slug="collector:multigenre:3",
                title="游历者",
                detail=f"在 {distinct_genres} 个题材里走完过结局。",
                payload={"genres": list(by_genre.keys())},
            )
        )

    return awarded


async def check_on_ownership_grant(
    *, user_id: int
) -> list[Award]:
    """Run after a new ownership row lands (origin or trade or gift).

    Scans gallery_summary once and emits any newly-passed thresholds.
    """
    awarded: list[Award] = []
    summary = await game_db.gallery_summary(user_id)
    per_genre = summary.get("per_genre") or {}
    total = int(summary.get("total") or 0)

    for genre, count in per_genre.items():
        if not genre or genre == "unknown":
            continue
        for threshold, title in GENRE_COLLECTOR_TIERS:
            if count >= threshold:
                slug = f"collector:cg:{genre}:{threshold}"
                awarded.append(
                    Award(
                        kind="collector",
                        slug=slug,
                        title=f"{title} · {_genre_name(genre)}",
                        detail=f"在【{_genre_name(genre)}】收藏达到 {threshold} 张 CG。",
                        payload={"genre": genre, "count": count, "threshold": threshold},
                    )
                )

    # Total-volume tier — counts cross-genre.
    for threshold, title in ((50, "百珍图"), (200, "万象图鉴")):
        if total >= threshold:
            awarded.append(
                Award(
                    kind="collector",
                    slug=f"collector:total:{threshold}",
                    title=title,
                    detail=f"累计收藏 {threshold} 张 CG。",
                    payload={"total": total, "threshold": threshold},
                )
            )

    return awarded


async def check_on_turn(
    *, user_id: int, run_id: int, turn_idx: int, scenes_so_far: list[dict[str, Any]]
) -> list[Award]:
    """Hidden-achievement detectors. Cheap to run per-turn — bail early
    when the data shape can't possibly satisfy the rule.

    Two示范 rules:
      * ``pacifist_8`` — first 8 turns, no scene visual_tag contains
        "battle"/"sword"/"weapon" keywords.
      * ``confidant_3`` — codex.relations has ≥3 entries by turn N (handled
        elsewhere — needs the run row).
    """
    awarded: list[Award] = []

    if turn_idx >= 8:
        battle_words = ("battle", "sword", "weapon", "blood", "fight")
        peaceful = True
        for s in scenes_so_far[:8]:
            tag = (s.get("visual_tag") or {}).get("tag") or ""
            t = tag.lower()
            if any(w in t for w in battle_words):
                peaceful = False
                break
        if peaceful:
            awarded.append(
                Award(
                    kind="hidden",
                    slug=f"hidden:pacifist_8:{run_id}",
                    title="无刃八回",
                    detail="前八回未涉刀兵 — 你以另一种方式存在着。",
                    payload={"run_id": run_id},
                )
            )

    return awarded


async def commit_awards(user_id: int, awards: list[Award]) -> list[Award]:
    """Persist via INSERT OR IGNORE; return only the rows that actually
    landed (so the caller can flash them to the UI)."""
    new_ones: list[Award] = []
    for a in awards:
        ok = await game_db.award_achievement(
            user_id,
            kind=a.kind,
            slug=a.slug,
            title=a.title,
            detail=a.detail,
            payload=a.payload,
        )
        if ok:
            new_ones.append(a)
            logger.info("achievement granted user=%s slug=%s", user_id, a.slug)
    return new_ones
