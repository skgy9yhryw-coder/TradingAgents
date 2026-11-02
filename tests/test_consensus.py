import pytest

from tradingagents.consensus import evaluate_consensus, normalize_direction


@pytest.mark.parametrize(
    ("votes", "direction"),
    [
        ({"claude": "Buy", "grok": "Long", "deepseek": "Overweight"}, "bullish"),
        ({"claude": "Sell", "grok": "Short", "deepseek": "Underweight"}, "bearish"),
    ],
)
def test_unanimous_direction_is_approved(votes, direction):
    result = evaluate_consensus(votes)
    assert result.approved
    assert result.direction == direction
    assert result.reason == "unanimous_3_of_3"


@pytest.mark.parametrize(
    ("votes", "reason"),
    [
        ({"claude": "Buy", "grok": "Sell", "deepseek": "Buy"}, "direction_disagreement"),
        ({"claude": "Buy", "grok": "Buy", "deepseek": "Hold"}, "neutral_vote"),
        ({"claude": "Buy", "grok": "Buy"}, "missing_or_invalid_vote"),
        ({"claude": "Buy", "grok": "Buy", "deepseek": "maybe"}, "missing_or_invalid_vote"),
        ({}, "missing_or_invalid_vote"),
    ],
)
def test_non_unanimous_or_incomplete_votes_fail_closed(votes, reason):
    result = evaluate_consensus(votes)
    assert not result.approved
    assert result.status == "no_trade"
    assert result.direction is None
    assert result.reason == reason


def test_direction_normalization_is_strict():
    assert normalize_direction("  LONG ") == "bullish"
    assert normalize_direction("short") == "bearish"
    assert normalize_direction("hold") == "neutral"
    assert normalize_direction("probably bullish") is None
