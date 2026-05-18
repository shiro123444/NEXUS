"""Game module — AI-driven open-world text adventure.

Public surface:
- router: FastAPI router to mount at /api/game
- init_tables: coroutine called from portal lifespan to create game tables
- load_reward_overrides: coroutine to populate rewards cache from DB
"""
from .routes import router
from .db import init_tables, get_reward_overrides
from . import rewards as _rewards


async def load_reward_overrides() -> None:
    """Load admin-configured reward overrides into memory at startup."""
    overrides = await get_reward_overrides()
    _rewards.set_overrides(overrides)


__all__ = ["router", "init_tables", "load_reward_overrides"]
