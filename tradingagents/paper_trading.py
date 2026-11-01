"""Local SQLite ledger for paper trades; never places broker orders.

The ledger stores hypothetical fills supplied by the caller. It is intentionally
separate from live execution and uses only the Python standard library.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tradingagents.consensus import MODEL_NAMES, evaluate_consensus


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _positive_number(value: float, field: str) -> float:
    number = float(value)
    if number <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return number


class PaperTradeLedger:
    """Append-only trade history with explicit open/close operations."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_trades (
                    trade_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('long', 'short')),
                    quantity REAL NOT NULL CHECK(quantity > 0),
                    entry_price REAL NOT NULL CHECK(entry_price > 0),
                    stop_loss REAL,
                    take_profit REAL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    exit_price REAL,
                    status TEXT NOT NULL CHECK(status IN ('open', 'closed')),
                    pnl REAL,
                    fees REAL NOT NULL DEFAULT 0,
                    strategy TEXT NOT NULL DEFAULT '',
                    news_context TEXT NOT NULL DEFAULT '',
                    model_votes TEXT NOT NULL DEFAULT '{}',
                    judge_approved INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_paper_trades_opened_at "
                "ON paper_trades(opened_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def open_trade(
        self,
        *,
        symbol: str,
        direction: str,
        quantity: float,
        entry_price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        strategy: str = "",
        news_context: str = "",
        model_votes: dict[str, Any] | None = None,
        judge_approved: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record a hypothetical entry. This method never contacts an exchange."""
        symbol = symbol.strip().upper()
        direction = direction.strip().lower()
        if not symbol:
            raise ValueError("symbol is required")
        if direction not in {"long", "short"}:
            raise ValueError("direction must be 'long' or 'short'")
        quantity = _positive_number(quantity, "quantity")
        entry_price = _positive_number(entry_price, "entry_price")
        if stop_loss is not None:
            stop_loss = _positive_number(stop_loss, "stop_loss")
        if take_profit is not None:
            take_profit = _positive_number(take_profit, "take_profit")
        if stop_loss is not None:
            if direction == "long" and stop_loss >= entry_price:
                raise ValueError("long stop_loss must be below entry_price")
            if direction == "short" and stop_loss <= entry_price:
                raise ValueError("short stop_loss must be above entry_price")
        if take_profit is not None:
            if direction == "long" and take_profit <= entry_price:
                raise ValueError("long take_profit must be above entry_price")
            if direction == "short" and take_profit >= entry_price:
                raise ValueError("short take_profit must be below entry_price")

        trade_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO paper_trades (
                    trade_id, symbol, direction, quantity, entry_price,
                    stop_loss, take_profit, opened_at, status, strategy,
                    news_context, model_votes, judge_approved, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)
                """,
                (
                    trade_id, symbol, direction, quantity, entry_price,
                    stop_loss, take_profit, _utc_now(), strategy, news_context,
                    json.dumps(model_votes or {}, ensure_ascii=False, sort_keys=True),
                    int(bool(judge_approved)),
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
        return trade_id

    def open_consensus_trade(
        self,
        *,
        symbol: str,
        direction: str,
        quantity: float,
        entry_price: float,
        model_votes: dict[str, str | None],
        judge_approved: bool,
        judge_rationale: str = "",
        **trade_metadata: Any,
    ) -> str:
        """Open a paper trade only after strict 3/3 direction and judge approval.

        This is a paper-ledger gate, not a substitute for market-data validation.
        The caller remains responsible for supplying a current, verified quote.
        """
        result = evaluate_consensus(model_votes)
        requested = "bullish" if direction.strip().lower() in {"long", "bullish", "buy"} else (
            "bearish" if direction.strip().lower() in {"short", "bearish", "sell"} else None
        )
        if not result.approved or result.direction != requested:
            raise ValueError("paper entry blocked: the three model votes are not unanimous for this direction")
        if not judge_approved:
            raise ValueError("paper entry blocked: ChatGPT judge approval is required")
        normalized_votes = {name: model_votes.get(name) for name in MODEL_NAMES}
        return self.open_trade(
            symbol=symbol,
            direction="long" if requested == "bullish" else "short",
            quantity=quantity,
            entry_price=entry_price,
            model_votes=normalized_votes,
            judge_approved=True,
            metadata={
                **(trade_metadata.pop("metadata", {}) or {}),
                "consensus_direction": result.direction,
                "consensus_reason": result.reason,
                "judge_rationale": judge_rationale,
                "approval_gate": "3_of_3_plus_judge",
            },
            **trade_metadata,
        )

    def close_trade(self, trade_id: str, *, exit_price: float, fees: float = 0) -> dict[str, Any]:
        """Close a paper trade and calculate net P&L after supplied fees."""
        exit_price = _positive_number(exit_price, "exit_price")
        fees = float(fees)
        if fees < 0:
            raise ValueError("fees cannot be negative")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paper_trades WHERE trade_id = ?", (trade_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown paper trade: {trade_id}")
            if row["status"] != "open":
                raise ValueError("paper trade is already closed")
            sign = 1 if row["direction"] == "long" else -1
            pnl = (exit_price - row["entry_price"]) * row["quantity"] * sign - fees
            connection.execute(
                """
                UPDATE paper_trades
                SET exit_price = ?, closed_at = ?, status = 'closed', pnl = ?, fees = ?
                WHERE trade_id = ? AND status = 'open'
                """,
                (exit_price, _utc_now(), pnl, fees, trade_id),
            )
            updated = connection.execute(
                "SELECT * FROM paper_trades WHERE trade_id = ?", (trade_id,)
            ).fetchone()
        return dict(updated)

    def list_trades(self, *, status: str | None = None) -> list[dict[str, Any]]:
        if status not in {None, "open", "closed"}:
            raise ValueError("status must be None, 'open', or 'closed'")
        query = "SELECT * FROM paper_trades"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY opened_at, trade_id"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def performance(self) -> dict[str, Any]:
        """Return closed-trade counts and win rate; open trades are excluded."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS closed_count,
                       COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
                       COALESCE(SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END), 0) AS losses,
                       COALESCE(SUM(pnl), 0) AS net_pnl
                FROM paper_trades WHERE status = 'closed'
                """
            ).fetchone()
        closed = int(row["closed_count"])
        wins = int(row["wins"])
        return {
            "closed_trades": closed,
            "wins": wins,
            "losses": int(row["losses"]),
            "net_pnl": float(row["net_pnl"]),
            "win_rate": (wins / closed) if closed else None,
        }
