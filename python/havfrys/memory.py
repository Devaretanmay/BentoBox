"""Engineering Memory — session-scoped record of what worked and what failed.

Tracks strategy outcomes within and across sessions so HAVFRYS can:
- Skip strategies that already failed for similar tasks
- Prioritize strategies that scored well historically
- Avoid re-exploring dead branches on havfrys.resume()
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


MEMORY_DIR = Path.home() / ".havfrys" / "memory"


def _ensure_memory_dir() -> Path:
    """Lazily create memory directory on first use."""
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return MEMORY_DIR


@dataclass
class StrategyOutcome:
    """One recorded outcome of a strategy execution."""

    strategy: str              # e.g. "automated_migration", "manual_rewrite"
    task_fingerprint: str      # hash of the task description
    status: str                # "success" | "failed" | "killed"
    score: float = 0.0        # 0.0–1.0, from Scorer
    execution_time_s: float = 0.0
    attempts: int = 0
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class EngineeringMemory:
    """Session-scoped memory of strategy outcomes.

    Persists to ~/.havfrys/memory/ so havfrys.resume() can skip dead strategies
    and prioritize winners from prior runs.
    """

    def __init__(self, session_id: str = "", memory_dir: Optional[Path] = None):
        self.session_id = session_id
        self._outcomes: list[StrategyOutcome] = []
        base = memory_dir or _ensure_memory_dir()
        self._path = base / f"{session_id}.json" if session_id else None
        if self._path and self._path.exists():
            self._load()

    def record(self, outcome: StrategyOutcome) -> None:
        """Record a strategy outcome."""
        self._outcomes.append(outcome)
        self._persist()

    def failed_strategies(self, task_fingerprint: str = "") -> list[str]:
        """Return strategy names that have failed for this task fingerprint."""
        return [
            o.strategy
            for o in self._outcomes
            if o.status in ("failed", "killed")
            and (not task_fingerprint or o.task_fingerprint == task_fingerprint)
        ]

    def best_strategy(self, task_fingerprint: str = "") -> Optional[str]:
        """Return the highest-scoring successful strategy for a task, or None."""
        successes = [
            o for o in self._outcomes
            if o.status == "success"
            and (not task_fingerprint or o.task_fingerprint == task_fingerprint)
        ]
        if not successes:
            return None
        return max(successes, key=lambda o: o.score).strategy

    def all_outcomes(self) -> list[StrategyOutcome]:
        """Return all recorded outcomes."""
        return list(self._outcomes)

    def _persist(self) -> None:
        """Write outcomes to disk."""
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = [asdict(o) for o in self._outcomes]
            self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load(self) -> None:
        """Load outcomes from disk."""
        if not self._path or not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._outcomes = [StrategyOutcome(**entry) for entry in raw]
        except Exception:
            self._outcomes = []
