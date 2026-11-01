import pytest

from tradingagents.paper_trading import PaperTradeLedger


def test_paper_trade_persists_and_calculates_long_pnl(tmp_path):
    ledger = PaperTradeLedger(tmp_path / "paper.sqlite3")
    trade_id = ledger.open_trade(
        symbol="lit", direction="long", quantity=2, entry_price=10,
        stop_loss=9, take_profit=12, model_votes={"claude": "bullish"},
        judge_approved=True,
    )

    reopened = PaperTradeLedger(tmp_path / "paper.sqlite3")
    assert reopened.list_trades(status="open")[0]["trade_id"] == trade_id
    closed = reopened.close_trade(trade_id, exit_price=12, fees=0.5)
    assert closed["pnl"] == pytest.approx(3.5)
    assert reopened.performance() == {
        "closed_trades": 1, "wins": 1, "losses": 0,
        "net_pnl": 3.5, "win_rate": 1.0,
    }


def test_short_trade_pnl_and_open_trades_not_in_win_rate(tmp_path):
    ledger = PaperTradeLedger(tmp_path / "paper.sqlite3")
    trade_id = ledger.open_trade(
        symbol="xpl", direction="short", quantity=3, entry_price=20,
        stop_loss=22, take_profit=16,
    )
    assert ledger.performance()["closed_trades"] == 0
    closed = ledger.close_trade(trade_id, exit_price=18)
    assert closed["pnl"] == pytest.approx(6)
    assert ledger.performance()["win_rate"] == 1.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"symbol": "", "direction": "long", "quantity": 1, "entry_price": 10},
        {"symbol": "ABC", "direction": "sideways", "quantity": 1, "entry_price": 10},
        {"symbol": "ABC", "direction": "long", "quantity": 0, "entry_price": 10},
        {"symbol": "ABC", "direction": "long", "quantity": 1, "entry_price": 10, "stop_loss": 11},
        {"symbol": "ABC", "direction": "short", "quantity": 1, "entry_price": 10, "take_profit": 11},
    ],
)
def test_invalid_paper_entries_are_rejected(tmp_path, kwargs):
    ledger = PaperTradeLedger(tmp_path / "paper.sqlite3")
    with pytest.raises(ValueError):
        ledger.open_trade(**kwargs)


def test_unknown_or_already_closed_trade_cannot_be_closed(tmp_path):
    ledger = PaperTradeLedger(tmp_path / "paper.sqlite3")
    with pytest.raises(KeyError):
        ledger.close_trade("missing", exit_price=10)
    trade_id = ledger.open_trade(
        symbol="ETH", direction="long", quantity=1, entry_price=100
    )
    ledger.close_trade(trade_id, exit_price=101)
    with pytest.raises(ValueError):
        ledger.close_trade(trade_id, exit_price=102)

def test_consensus_entry_requires_three_matching_votes_and_judge(tmp_path):
    ledger = PaperTradeLedger(tmp_path / "paper.sqlite3")
    votes = {"claude": "bullish", "grok": "bullish", "deepseek": "bullish"}
    with pytest.raises(ValueError, match="judge approval"):
        ledger.open_consensus_trade(
            symbol="ETH", direction="long", quantity=1, entry_price=100,
            model_votes=votes, judge_approved=False,
        )
    with pytest.raises(ValueError, match="not unanimous"):
        ledger.open_consensus_trade(
            symbol="ETH", direction="long", quantity=1, entry_price=100,
            model_votes={**votes, "deepseek": "bearish"}, judge_approved=True,
        )
    trade_id = ledger.open_consensus_trade(
        symbol="ETH", direction="long", quantity=1, entry_price=100,
        model_votes=votes, judge_approved=True, judge_rationale="Approved for paper test",
    )
    trade = ledger.list_trades(status="open")[0]
    assert trade["trade_id"] == trade_id
    assert trade["judge_approved"] == 1
    assert '"approval_gate": "3_of_3_plus_judge"' in trade["metadata"]


def test_consensus_entry_direction_must_match_votes(tmp_path):
    ledger = PaperTradeLedger(tmp_path / "paper.sqlite3")
    with pytest.raises(ValueError, match="not unanimous"):
        ledger.open_consensus_trade(
            symbol="ETH", direction="short", quantity=1, entry_price=100,
            model_votes={"claude": "bullish", "grok": "bullish", "deepseek": "bullish"},
            judge_approved=True,
        )
