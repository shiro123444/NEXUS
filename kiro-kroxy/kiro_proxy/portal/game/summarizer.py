"""Chapter summarizer — compresses stretches of scenes into a 80-150 字 note.

Why this exists:
- turn prompt 的上下文必须保持有界，否则 20+ 回合的 run 会让 token 预算爆。
- 单纯按 "最近 N 回合原文" 截断会让 LLM 忘掉前面发生过的关键转折。
- 摘要表 `game_summaries` 已经建好，但从来没人写 —— 本模块补上这条路径。

触发策略（见 `should_summarize`）:
- 每 5 回合触发一次（chapter_idx 自增 1），或
- 本回合 is_keynote=true 时也触发。
两者叠加时只摘一次。

失败策略:
- 摘要失败不应该阻塞玩家的回合推进，所以 routes 里用 `asyncio.create_task`
  或 try/except 包住 —— 本模块只负责 "尝试"，不负责调度。
"""
from __future__ import annotations

import logging
from typing import Any

from . import db as game_db
from . import engine as game_engine

logger = logging.getLogger(__name__)


SUMMARY_SYSTEM = """你是文字冒险游戏的章节总结器。只输出一段中文散文摘要。

你会收到一段连续的回合原文（按回合号升序排列）。请用 80-150 字、2-3 短段，
把它压缩成一份"玩家手札"风格的章节小记：
- 第二人称"你"，和正文保持一致。
- 保留关键事件、遇到的 NPC、立下的承诺/背叛、获得或失去的重要物件。
- 不要写成流水账，重要节拍优先；琐碎的环境描写可以省。
- 绝对禁止 HTML/Markdown（无 <br>、** 加粗、# 标题 等），段落间空一行即可。
- 不要重复人物名过多次；第一次点名后用代称（"他"/"她"/身份）。
- 不要超过 150 字，不要附加 XML 标签或额外解释。
"""


def _should_summarize(*, turn_idx: int, is_keynote: bool) -> bool:
    """True 时应当触发章节摘要。

    Rules:
      * turn_idx >= 1 且 turn_idx % 5 == 0 —— 每 5 回合一道章节切线。
      * 本回合 is_keynote=True —— 关键转折也切一次。

    turn_idx=0（开场）不触发：还没发生任何推进，没什么可摘的。
    """
    if turn_idx <= 0:
        return False
    return (turn_idx % 5 == 0) or bool(is_keynote)


def _format_scenes(scenes: list[dict[str, Any]]) -> str:
    """把 scene 列表拼成摘要器的输入文本。"""
    lines: list[str] = []
    for s in scenes:
        narrative = (s.get("narrative") or "").strip()
        if not narrative:
            continue
        action = (s.get("player_action") or "").strip()
        header = f"[回合{s['turn_idx']}]"
        if action:
            header += f" 玩家：{action}"
        lines.append(f"{header}\n{narrative}")
    return "\n\n".join(lines)


async def maybe_summarize(
    *,
    run_id: int,
    chapter_idx: int,
    turn_idx: int,
    is_keynote: bool,
) -> dict[str, Any] | None:
    """Try to write a new summary row if trigger conditions are met.

    Returns the inserted summary dict on success, None otherwise (including
    when the trigger didn't fire). Never raises — callers can fire-and-forget.

    chapter_idx here is the *new* chapter number we'd assign if we write. The
    caller is responsible for then bumping run.chapter_idx so future turns
    know which chapter they're in.
    """
    if not _should_summarize(turn_idx=turn_idx, is_keynote=is_keynote):
        return None

    try:
        existing = await game_db.list_summaries(run_id)
        last_to = max((int(s["covers_turn_to"]) for s in existing), default=-1)
        turn_from = last_to + 1
        if turn_from > turn_idx:
            # 已经摘要过这段；不重复摘。
            return None

        scenes = await game_db.list_scenes(run_id, from_turn=turn_from, limit=200)
        scenes = [s for s in scenes if int(s["turn_idx"]) <= turn_idx]
        if not scenes:
            return None

        body = _format_scenes(scenes)
        if not body.strip():
            return None

        user_prompt = (
            f"以下是玩家从回合 {turn_from} 到回合 {turn_idx} 的原文，请按系统指令压缩：\n\n{body}"
        )
        text, _usage = await game_engine.call_text_model(
            system=SUMMARY_SYSTEM,
            user=user_prompt,
            model=game_engine.SUMMARY_MODEL,
            max_tokens=400,
        )
        summary_text = text.strip()
        if not summary_text:
            logger.warning("game.summarize empty text run=%s", run_id)
            return None

        sid = await game_db.insert_summary(
            run_id,
            chapter_idx,
            summary_text,
            turn_from,
            turn_idx,
        )
        logger.info(
            "game.summarize run=%s chapter=%s turns=%s..%s id=%s",
            run_id,
            chapter_idx,
            turn_from,
            turn_idx,
            sid,
        )
        return {
            "id": sid,
            "chapter_idx": chapter_idx,
            "summary": summary_text,
            "covers_turn_from": turn_from,
            "covers_turn_to": turn_idx,
        }
    except Exception as exc:
        logger.warning("game.summarize failed run=%s: %s", run_id, exc)
        return None


def format_memory_for_prompt(
    summaries: list[dict[str, Any]], recent_scenes: list[dict[str, Any]]
) -> str:
    """Build the `recent_summary` payload for the turn prompt.

    Layout:
      <past_chapters>
      第1章 [回合0-4] …摘要…
      第2章 [回合5-9] …摘要…
      </past_chapters>

      <recent_turns>
      [回合10 scene] 原文…
      [回合11 choice] 原文…
      </recent_turns>

    If summaries is empty we emit only <recent_turns> so the LLM still has
    some continuity signal.
    """
    parts: list[str] = []
    if summaries:
        past_lines = [
            f"第{s['chapter_idx']}章 [回合{s['covers_turn_from']}-{s['covers_turn_to']}] {s['summary']}"
            for s in summaries
            if s.get("summary")
        ]
        if past_lines:
            parts.append("<past_chapters>\n" + "\n\n".join(past_lines) + "\n</past_chapters>")

    if recent_scenes:
        recent_lines: list[str] = []
        for s in recent_scenes:
            narrative = (s.get("narrative") or "").strip()
            if not narrative:
                continue
            raw_choices = s.get("choices") or []
            try:
                n = sum(1 for c in raw_choices if (c.get("text") if isinstance(c, dict) else c))
            except Exception:
                n = 0
            beat = "choice" if n >= 2 else "scene"
            recent_lines.append(f"[回合{s['turn_idx']} {beat}] {narrative}")
        if recent_lines:
            parts.append("<recent_turns>\n" + "\n".join(recent_lines) + "\n</recent_turns>")

    return "\n\n".join(parts)
