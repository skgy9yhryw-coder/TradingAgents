## Paper-trade ledger

The optional paper-trade ledger stores hypothetical entries and exits in a local
SQLite database. It does not connect to an exchange or place orders. By default,
the database is stored at `~/.tradingagents/paper_trades.sqlite3`; override it
with `TRADINGAGENTS_PAPER_TRADES_DB_PATH`.

Programmatic use (illustrative values only; this does not create a real signal):

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

graph = TradingAgentsGraph()
trade_id = graph.open_consensus_paper_trade(
    symbol="ETH",
    direction="long",  # or "short"
    quantity=0.1,
    entry_price=2500.0,  # supply a current, independently verified quote
    stop_loss=2400.0,
    take_profit=2700.0,
    strategy="paper-only example",
    news_context="Example context; replace with verified sources.",
    model_votes={"claude": "bullish", "grok": "bullish", "deepseek": "bullish"},
    judge_approved=True,
    judge_rationale="Illustrative approval only; replace with the actual review.",
)
closed = graph.close_paper_trade(trade_id, exit_price=2600.0, fees=0.5)
print(closed["pnl"])
print(graph.paper_trade_performance())
```

Use `open_consensus_paper_trade` for entries that must satisfy the 3-of-3
direction gate and the veto-only judge. The lower-level `open_paper_trade`
method records a manually supplied hypothetical trade and does not enforce
model consensus; do not use it for consensus-qualified entries. The example
above is documentation only, not a market signal or a recommendation. Open
trades are excluded from win-rate calculations until closed. The database is
local to the machine running the application and is not automatically synced
to GitHub.

### Independent consensus gate (paper-trading preparation)

The graph now places a fail-closed consensus gate after the Portfolio Manager. It requests
independent structured direction votes from Anthropic Claude, xAI Grok, and DeepSeek.
All three must return the same explicit direction, and the Portfolio Manager's direction
must agree. A ChatGPT-plan reviewer is then asked for a veto-only review: it can reject
the setup but cannot change the direction. Any missing model ID, missing credentials,
provider error, malformed response, disagreement, or judge failure results in
`NO TRADE` / `REVIEW`.

Configure model IDs in the local environment (never commit API keys):

```bash
export TRADINGAGENTS_CONSENSUS_CLAUDE_MODEL="<your-enabled-Claude-model-id>"
export TRADINGAGENTS_CONSENSUS_GROK_MODEL="<your-enabled-Grok-model-id>"
export TRADINGAGENTS_CONSENSUS_DEEPSEEK_MODEL="<your-enabled-DeepSeek-model-id>"
export TRADINGAGENTS_CONSENSUS_JUDGE_MODEL="<your-ChatGPT-plan-model-id>"
```

Provider credentials must be available in the local runtime using the standard variables
(`ANTHROPIC_API_KEY`, `XAI_API_KEY`, `DEEPSEEK_API_KEY`) and ChatGPT plan authentication
must already be configured for the local runtime. A ChatGPT subscription in the web app
does not automatically authenticate a separate computer or server. Do not paste secrets
into GitHub or chat.

This gate does not fetch or validate a live quote and does not open paper trades
automatically. It only produces an audited consensus decision. Keep the system in
paper/research mode until market-data freshness, instrument mapping, tests, and paper
execution accounting have been validated.
