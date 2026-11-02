"""Strict three-model voting policy for trade direction.

This module is deliberately deterministic and has no provider/network dependency.
Provider orchestration can call it only after collecting one valid vote from each
independent model. Missing, malformed, neutral, or disagreeing votes fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

MODEL_NAMES = ("claude", "grok", "deepseek")
BULLISH_RATINGS = frozenset({"buy", "overweight", "bullish", "long"})
BEARISH_RATINGS = frozenset({"sell", "underweight", "bearish", "short"})
NEUTRAL_RATINGS = frozenset({"hold", "neutral", "no trade", "no_trade"})


@dataclass(frozen=True)
class ConsensusResult:
    """Auditable result of the three independent model votes."""

    status: str
    direction: str | None
    votes: dict[str, str | None]
    reason: str

    @property
    def approved(self) -> bool:
        return self.status == "approved"


def normalize_direction(vote: str | None) -> str | None:
    """Map an explicit directional rating to bullish/bearish; reject ambiguity."""
    if not isinstance(vote, str):
        return None
    normalized = " ".join(vote.strip().lower().replace("_", " ").split())
    if normalized in BULLISH_RATINGS:
        return "bullish"
    if normalized in BEARISH_RATINGS:
        return "bearish"
    if normalized in NEUTRAL_RATINGS:
        return "neutral"
    return None


def evaluate_consensus(votes: dict[str, str | None]) -> ConsensusResult:
    """Approve only when Claude, Grok and DeepSeek all give the same direction.

    Extra keys are ignored. A missing/invalid/neutral vote or any disagreement
    returns No Trade. The caller must not infer or fill in a missing vote.
    """
    normalized = {
        name: normalize_direction(votes.get(name))
        for name in MODEL_NAMES
    }
    if any(direction is None for direction in normalized.values()):
        return ConsensusResult(
            "no_trade", None, normalized,
            "missing_or_invalid_vote",
        )
    if any(direction == "neutral" for direction in normalized.values()):
        return ConsensusResult(
            "no_trade", None, normalized,
            "neutral_vote",
        )
    directions = set(normalized.values())
    if len(directions) != 1:
        return ConsensusResult(
            "no_trade", None, normalized,
            "direction_disagreement",
        )
    return ConsensusResult(
        "approved", next(iter(directions)), normalized,
        "unanimous_3_of_3",
    )
