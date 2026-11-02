import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph


class _LedgerSpy:
    def __init__(self):
        self.calls = []

    def open_consensus_trade(self, **kwargs):
        self.calls.append(kwargs)
        return "paper-trade-id"


def _graph_without_initializing():
    graph = object.__new__(TradingAgentsGraph)
    graph._paper_ledger = _LedgerSpy()
    return graph


def _approved_state():
    return {
        "consensus_status": "approved",
        "judge_approved": True,
        "consensus_votes": {
            "claude": "bullish",
            "grok": "bullish",
            "deepseek": "bullish",
        },
        "consensus_direction": "bullish",
        "final_rating": "Buy",
        "judge_rationale": "No material contradiction.",
    }


def test_public_paper_entry_requires_completed_final_state():
    graph = _graph_without_initializing()
    with pytest.raises(TypeError):
        graph.open_paper_trade(symbol="ETH", direction="long", quantity=1, entry_price=100)
    assert graph._paper_ledger.calls == []


@pytest.mark.parametrize(
    "changes",
    [
        {"consensus_status": "no_trade"},
        {"judge_approved": False},
        {"consensus_direction": "bearish"},
        {"final_rating": "Hold"},
        {"consensus_votes": {"claude": "bullish", "grok": "bullish", "deepseek": "bearish"}},
    ],
)
def test_public_paper_entry_fails_closed(changes):
    graph = _graph_without_initializing()
    state = {**_approved_state(), **changes}
    with pytest.raises(ValueError):
        graph.open_paper_trade(
            final_state=state, symbol="ETH", direction="long", quantity=1, entry_price=100,
        )
    assert graph._paper_ledger.calls == []


def test_public_paper_entry_uses_guarded_ledger_path():
    graph = _graph_without_initializing()
    trade_id = graph.open_paper_trade(
        final_state=_approved_state(),
        symbol="ETH", direction="long", quantity=1, entry_price=100,
    )
    assert trade_id == "paper-trade-id"
    assert len(graph._paper_ledger.calls) == 1
    assert graph._paper_ledger.calls[0]["judge_approved"] is True
