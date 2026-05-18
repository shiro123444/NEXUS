"""Typed data structures for the game module.

Dataclasses used as DTOs between routes, engine, and db layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RunStatus = Literal["generating", "running", "ended", "abandoned"]


@dataclass(frozen=True)
class Choice:
    """A single option presented to the player at the end of a scene."""

    id: str
    label: str
    risk: Literal["low", "medium", "high"] = "medium"


@dataclass(frozen=True)
class VisualTag:
    """Structured visual descriptor; hashes into the image cache key."""

    scene: str = ""
    mood: str = ""
    characters: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "scene": self.scene,
            "mood": self.mood,
            "characters": list(self.characters),
            "effects": list(self.effects),
        }


@dataclass(frozen=True)
class StateDelta:
    """Incremental change applied to a run's character snapshot after a turn."""

    hp: int = 0
    mana: int = 0
    reputation: int = 0
    items_added: tuple[str, ...] = ()
    items_removed: tuple[str, ...] = ()
    relations: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "hp": self.hp,
            "mana": self.mana,
            "reputation": self.reputation,
            "items_added": list(self.items_added),
            "items_removed": list(self.items_removed),
            "relations": dict(self.relations),
        }


@dataclass(frozen=True)
class GameRunSummary:
    """Lightweight row for listing / leaderboard / history endpoints."""

    id: int
    user_id: int
    status: RunStatus
    cover_url: str | None
    chapter_idx: int
    turn_idx: int
    ending_slug: str | None
    score: int
    started_at: str
    ended_at: str | None
