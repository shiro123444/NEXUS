"""XML parsing helpers for LLM output.

We don't use stdlib xml.etree because Claude's output occasionally has stray
whitespace/markdown around the outermost tag, and we want to tolerate that
without crashing. Regex + minimal validation is enough for our fixed schema.

If the model returns malformed XML we raise ``ParseError``; the caller decides
whether to retry or fall back to a canned scene.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class ParseError(ValueError):
    """Raised when LLM output doesn't match the expected XML schema."""


_TAG_RE = re.compile(r"<([a-zA-Z_][\w-]*)(\s[^>]*)?>(.*?)</\1>", re.DOTALL)


def _strip_outer_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        if t.endswith("```"):
            t = t[: -3]
    return t.strip()


def _extract_block(text: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", text, re.DOTALL)
    return m.group(1).strip() if m else None


def _extract_all(text: str, tag: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(rf"<{tag}\b[^>]*>(.*?)</{tag}>", text, re.DOTALL)]


def _inner(xml: str, tag: str, default: str = "") -> str:
    v = _extract_block(xml, tag)
    return v if v is not None else default


def _attr(xml_tag_text: str, attr: str) -> str | None:
    m = re.search(rf'{attr}\s*=\s*"([^"]*)"', xml_tag_text)
    return m.group(1) if m else None


@dataclass(frozen=True)
class WorldBible:
    era: str
    protagonist: dict[str, str]
    npcs: list[dict[str, str]]
    factions: list[dict[str, str]]
    possible_endings: list[dict[str, str]]
    plot_spine: dict[str, Any]
    art_style: str
    genre: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "era": self.era,
            "protagonist": dict(self.protagonist),
            "npcs": [dict(n) for n in self.npcs],
            "factions": [dict(f) for f in self.factions],
            "possible_endings": [dict(e) for e in self.possible_endings],
            "plot_spine": dict(self.plot_spine),
            "art_style": self.art_style,
            "genre": self.genre,
        }


@dataclass(frozen=True)
class OpeningScene:
    narrative: str
    visual_tag: str
    choices: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"narrative": self.narrative, "visual_tag": self.visual_tag, "choices": list(self.choices)}


@dataclass(frozen=True)
class TurnResult:
    narrative: str
    state_delta: list[dict[str, str]]
    codex_delta: list[dict[str, str]]
    visual_tag: str
    is_keynote: bool
    choices: list[str]
    ending_slug: str
    ending_text: str
    beat_kind: str = "scene"  # scene | choice | ending

    def to_dict(self) -> dict[str, Any]:
        return {
            "narrative": self.narrative,
            "state_delta": [dict(c) for c in self.state_delta],
            "codex_delta": [dict(c) for c in self.codex_delta],
            "visual_tag": self.visual_tag,
            "is_keynote": self.is_keynote,
            "choices": list(self.choices),
            "ending_slug": self.ending_slug,
            "ending_text": self.ending_text,
            "beat_kind": self.beat_kind,
        }


def parse_world_and_opening(raw: str) -> tuple[WorldBible, OpeningScene]:
    text = _strip_outer_fences(raw)
    wb_block = _extract_block(text, "world_bible")
    op_block = _extract_block(text, "opening_scene")
    if wb_block is None or op_block is None:
        raise ParseError("missing <world_bible> or <opening_scene> block")

    protagonist_block = _extract_block(wb_block, "protagonist") or ""
    protagonist = {
        "name": _inner(protagonist_block, "name"),
        "origin": _inner(protagonist_block, "origin"),
        "goal": _inner(protagonist_block, "goal"),
    }
    if not protagonist["name"]:
        raise ParseError("protagonist.name is empty")

    npcs_block = _extract_block(wb_block, "npcs") or ""
    npcs: list[dict[str, str]] = []
    for raw_npc in _extract_all(npcs_block, "npc"):
        npcs.append(
            {
                "name": _inner(raw_npc, "name"),
                "role": _inner(raw_npc, "role"),
                "stance": _inner(raw_npc, "stance"),
                "motive": _inner(raw_npc, "motive"),
            }
        )

    factions_block = _extract_block(wb_block, "factions") or ""
    factions: list[dict[str, str]] = []
    for raw_f in _extract_all(factions_block, "faction"):
        factions.append({"name": _inner(raw_f, "name"), "agenda": _inner(raw_f, "agenda")})

    endings_block = _extract_block(wb_block, "possible_endings") or ""
    endings: list[dict[str, str]] = []
    for m in re.finditer(r'<ending\s+slug\s*=\s*"([^"]+)"\s*>(.*?)</ending>', endings_block, re.DOTALL):
        endings.append({"slug": m.group(1).strip(), "text": m.group(2).strip()})
    if len(endings) < 2:
        raise ParseError("need at least 2 possible endings")

    plot_spine_block = _extract_block(wb_block, "plot_spine") or ""
    acts_block = _extract_block(plot_spine_block, "acts") or ""
    acts = [
        {
            "name": _attr(attrs, "name") or "",
            "turns": _attr(attrs, "turns") or "",
            "goal": value.strip(),
        }
        for attrs, value in re.findall(r"<act\s+([^>]*)>(.*?)</act>", acts_block, re.DOTALL)
        if value.strip()
    ]
    foreshadow_block = _extract_block(plot_spine_block, "foreshadow") or ""
    foreshadow = [
        {
            "seed": _inner(raw_seed, "seed"),
            "meaning": _inner(raw_seed, "meaning"),
            "payoff": _inner(raw_seed, "payoff"),
        }
        for raw_seed in _extract_all(foreshadow_block, "item")
        if raw_seed.strip()
    ]
    ending_conditions_block = _extract_block(plot_spine_block, "ending_conditions") or ""
    ending_conditions = [
        {
            "slug": _attr(attrs, "slug") or "",
            "condition": value.strip(),
        }
        for attrs, value in re.findall(r"<condition\s+([^>]*)>(.*?)</condition>", ending_conditions_block, re.DOTALL)
        if value.strip()
    ]
    plot_spine = {
        "central_question": _inner(plot_spine_block, "central_question"),
        "opening_promise": _inner(plot_spine_block, "opening_promise"),
        "reversal_seed": _inner(plot_spine_block, "reversal_seed"),
        "acts": acts,
        "foreshadow": foreshadow,
        "ending_conditions": ending_conditions,
    }

    wb = WorldBible(
        era=_inner(wb_block, "era"),
        protagonist=protagonist,
        npcs=npcs,
        factions=factions,
        possible_endings=endings,
        plot_spine=plot_spine,
        art_style=_inner(wb_block, "art_style"),
        genre=_inner(wb_block, "genre"),
    )

    op_choices = [c for c in _extract_all(op_block, "choice") if c]
    if len(op_choices) < 2:
        raise ParseError("opening scene needs at least 2 choices")

    scene = OpeningScene(
        narrative=_strip_markup(_inner(op_block, "narrative")),
        visual_tag=_inner(op_block, "visual_tag"),
        choices=op_choices[:3],
    )
    if not scene.narrative:
        raise ParseError("opening narrative is empty")
    return wb, scene


_SLUG_RE = re.compile(r"[a-z0-9_]+")
_HTML_TAG_RE = re.compile(r"<[^<>]{0,40}>")


def _strip_markup(text: str) -> str:
    """Remove stray HTML tags and markdown bold/italic markers from narration."""
    if not text:
        return text
    cleaned = _HTML_TAG_RE.sub("", text)
    for marker in ("**", "__"):
        cleaned = cleaned.replace(marker, "")
    return cleaned


def _normalize_slug(raw: str) -> str:
    """Lowercase, keep [a-z0-9_], collapse runs, cap at 40. Empty → ''."""
    if not raw:
        return ""
    cleaned = raw.strip().lower().replace(" ", "_").replace("-", "_")
    cleaned = "".join(ch for ch in cleaned if ch.isalnum() or ch == "_")
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        return ""
    # Slugs must start with a letter to stay valid for URLs/tags.
    if not cleaned[0].isalpha():
        cleaned = "e_" + cleaned
    return cleaned[:40]


def parse_turn(raw: str) -> TurnResult:
    text = _strip_outer_fences(raw)
    block = _extract_block(text, "turn")
    if block is None:
        raise ParseError("missing <turn> block")

    state_delta_block = _extract_block(block, "state_delta") or ""
    state_delta: list[dict[str, str]] = []
    for m in re.finditer(r"<change\s+([^>]*)>(.*?)</change>", state_delta_block, re.DOTALL):
        attrs, value = m.group(1), m.group(2).strip()
        key = _attr(attrs, "key") or ""
        op = _attr(attrs, "op") or "set"
        if key:
            state_delta.append({"key": key, "op": op, "value": value})

    codex_delta_block = _extract_block(block, "codex_delta") or ""
    codex_delta: list[dict[str, str]] = []
    for m in re.finditer(r"<entry\s+([^>]*)>(.*?)</entry>", codex_delta_block, re.DOTALL):
        attrs, value = m.group(1), m.group(2).strip()
        key = _attr(attrs, "key") or ""
        ctype = (_attr(attrs, "type") or "keynote").lower()
        op = (_attr(attrs, "op") or "set").lower()
        if ctype not in {"relation", "keynote", "secret"}:
            ctype = "keynote"
        if op not in {"set", "remove"}:
            op = "set"
        if key:
            codex_delta.append({"type": ctype, "key": key, "op": op, "value": value})

    is_keynote = _inner(block, "is_keynote", "false").strip().lower() in {"true", "1", "yes"}
    choices = [c for c in _extract_all(_inner(block, "choices", ""), "choice")]
    choices = [c for c in choices if c]

    ending_slug_raw = _inner(block, "ending_slug")
    ending_slug = _normalize_slug(ending_slug_raw)
    ending_text = _inner(block, "ending_text")
    # Ending text only meaningful if slug is set; otherwise discard.
    if not ending_slug:
        ending_text = ""

    beat_raw = _inner(block, "beat_kind", "").strip().lower()
    if ending_slug:
        beat_kind = "ending"
        choices = []
    elif beat_raw == "choice" and len(choices) >= 2:
        beat_kind = "choice"
    elif beat_raw == "choice" and len(choices) < 2:
        # Model claimed choice but didn't produce enough options — treat as
        # scene so the frontend auto-advances instead of showing a dead panel.
        beat_kind = "scene"
        choices = []
    else:
        # Default: free-flowing narration. Drop stray choices so the UI
        # doesn't flash an overlay.
        beat_kind = "scene"
        choices = []

    result = TurnResult(
        narrative=_strip_markup(_inner(block, "narrative")),
        state_delta=state_delta,
        codex_delta=codex_delta,
        visual_tag=_inner(block, "visual_tag"),
        is_keynote=is_keynote,
        choices=choices[:3],
        ending_slug=ending_slug,
        ending_text=_strip_markup(ending_text),
        beat_kind=beat_kind,
    )
    if not result.narrative:
        raise ParseError("turn narrative is empty")
    return result
