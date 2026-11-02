from tradingagents.agents import consensus_gate
from tradingagents.agents.consensus_gate import DirectionVote, JudgeReview, create_consensus_node


class _Structured:
    def __init__(self, schema, result):
        self.schema = schema
        self.result = result

    def invoke(self, _messages):
        return self.result


class _FakeLLM:
    def __init__(self, schema, result):
        self.schema = schema
        self.result = result

    def with_structured_output(self, schema):
        return _Structured(schema, self.result)


def _state(rating="Buy"):
    return {
        "company_of_interest": "NVDA",
        "asset_type": "stock",
        "trade_date": "2026-10-30",
        "instrument_context": "NVIDIA Corporation",
        "market_report": "Trend is constructive.",
        "news_report": "No material negative news.",
        "sentiment_report": "Sentiment is positive.",
        "fundamentals_report": "Fundamentals are supportive.",
        "trader_investment_plan": "Proposed long position.",
        "final_trade_decision": "Buy based on the analysis.",
        "final_rating": rating,
    }


def _config():
    return {
        "consensus_claude_provider": "anthropic",
        "consensus_claude_model": "claude-test",
        "consensus_grok_provider": "xai",
        "consensus_grok_model": "grok-test",
        "consensus_deepseek_provider": "deepseek",
        "consensus_deepseek_model": "deepseek-test",
        "consensus_judge_provider": "chatgpt",
        "consensus_judge_model": "judge-test",
    }


def test_unanimous_votes_and_judge_approval(monkeypatch):
    vote = DirectionVote(direction="bullish", rationale="Evidence supports upside.")
    judge = JudgeReview(approved=True, rationale="No material contradiction.")
    clients = iter([_FakeLLM(DirectionVote, vote) for _ in range(3)] + [_FakeLLM(JudgeReview, judge)])
    monkeypatch.setattr(consensus_gate, "_client", lambda *_args: next(clients))

    result = create_consensus_node(_config())(_state())

    assert result["consensus_status"] == "approved"
    assert result["consensus_votes"] == {
        "claude": "bullish", "grok": "bullish", "deepseek": "bullish"
    }
    assert result["judge_approved"] is True
    assert result["final_rating"] == "Buy"


def test_pm_hold_rating_cannot_be_overridden_by_unanimous_votes(monkeypatch):
    vote = DirectionVote(direction="bullish", rationale="Evidence supports upside.")
    clients = iter([_FakeLLM(DirectionVote, vote) for _ in range(3)])
    monkeypatch.setattr(consensus_gate, "_client", lambda *_args: next(clients))

    result = create_consensus_node(_config())(_state(rating="Hold"))

    assert result["consensus_status"] == "no_trade"
    assert result["judge_approved"] is False
    assert result["final_rating"] == "REVIEW"
    assert "portfolio_manager_direction_mismatch" in result["judge_rationale"]


def test_missing_model_configuration_fails_closed():
    result = create_consensus_node({})(_state())

    assert result["consensus_status"] == "no_trade"
    assert result["final_rating"] == "REVIEW"
    assert result["consensus_votes"] == {}


def test_judge_veto_blocks_unanimous_votes(monkeypatch):
    vote = DirectionVote(direction="bearish", rationale="Evidence supports downside.")
    judge = JudgeReview(approved=False, rationale="Material risk remains unresolved.")
    clients = iter(
        [_FakeLLM(DirectionVote, vote) for _ in range(3)]
        + [_FakeLLM(JudgeReview, judge)]
    )
    monkeypatch.setattr(consensus_gate, "_client", lambda *_args: next(clients))

    result = create_consensus_node(_config())(_state(rating="Sell"))

    assert result["consensus_status"] == "no_trade"
    assert result["judge_approved"] is False
    assert result["final_rating"] == "REVIEW"
    assert "chatgpt_judge_veto" in result["judge_rationale"]


def test_provider_failure_after_partial_votes_fails_closed(monkeypatch):
    vote = DirectionVote(direction="bullish", rationale="Evidence supports upside.")
    clients = iter([_FakeLLM(DirectionVote, vote), RuntimeError("provider unavailable")])

    def fake_client(*_args):
        value = next(clients)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(consensus_gate, "_client", fake_client)

    result = create_consensus_node(_config())(_state())

    assert result["consensus_status"] == "no_trade"
    assert result["consensus_votes"] == {"claude": "bullish"}
    assert result["judge_approved"] is False
    assert result["final_rating"] == "REVIEW"


def test_portfolio_manager_bearish_rating_rejects_bullish_consensus(monkeypatch):
    vote = DirectionVote(direction="bullish", rationale="Evidence supports upside.")
    clients = iter([_FakeLLM(DirectionVote, vote) for _ in range(3)])
    monkeypatch.setattr(consensus_gate, "_client", lambda *_args: next(clients))

    result = create_consensus_node(_config())(_state(rating="Sell"))

    assert result["consensus_status"] == "no_trade"
    assert result["judge_approved"] is False
    assert result["final_rating"] == "REVIEW"
    assert "portfolio_manager_direction_mismatch" in result["judge_rationale"]
