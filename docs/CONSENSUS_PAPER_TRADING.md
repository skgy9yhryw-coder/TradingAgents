# Consensus Gate and Paper-Trading Operations

This feature is a research and record-keeping workflow. It does **not** place orders with a broker or exchange.

## Approval policy

A directional paper entry through the graph must use `TradingAgentsGraph.open_paper_trade(final_state=...)` or `TradingAgentsGraph.open_consensus_paper_trade(final_state=...)`. Both require the completed graph state and enforce the approval checks.

An entry is accepted only when all of the following hold:

1. Claude, Grok, and DeepSeek each return a valid structured vote.
2. All three votes agree on the same non-neutral direction.
3. The Portfolio Manager's rating agrees with that direction.
4. The ChatGPT judge explicitly approves. The judge can veto; it cannot change the direction.

A missing model, malformed response, provider/authentication error, neutral vote, disagreement, Portfolio Manager mismatch, or judge veto produces **NO TRADE / REVIEW**.

The lower-level `PaperTradeLedger.open_trade()` and `PaperTradeLedger.open_consensus_trade()` methods remain implementation primitives for direct ledger users; they cannot prove that a supplied state came from the completed graph or that a judge actually ran. Do not expose or use them as a substitute for the graph approval workflow. The graph's public `open_paper_trade()` entry point requires `final_state` and delegates to the guarded consensus path.

## Configure the four model IDs

Set model IDs explicitly; there are no silent model defaults for the consensus gate:

```bash
export TRADINGAGENTS_CONSENSUS_CLAUDE_MODEL="your-claude-model-id"
export TRADINGAGENTS_CONSENSUS_GROK_MODEL="your-grok-model-id"
export TRADINGAGENTS_CONSENSUS_DEEPSEEK_MODEL="your-deepseek-model-id"
export TRADINGAGENTS_CONSENSUS_JUDGE_MODEL="your-chatgpt-model-id"
```

Configure credentials using the providers' normal environment variables:

- Claude: `ANTHROPIC_API_KEY`
- Grok: `XAI_API_KEY`
- DeepSeek: `DEEPSEEK_API_KEY`

For the ChatGPT judge, authenticate the local TradingAgents runtime using its supported ChatGPT login flow (`tradingagents login chatgpt`) or configure an approved provider credential. A ChatGPT web subscription by itself does not authenticate a separate local process.

Never commit API keys, OAuth tokens, or local authentication files to this repository.

## Paper ledger

The SQLite ledger is local and separate from broker execution. Entries record caller-supplied hypothetical prices; the ledger does not fetch or verify live quotes. Supply current, independently verified prices and realistic fees when recording a paper trade. Open trades are excluded from closed-trade win-rate calculations.

## Before relying on results

- Run the repository test suite and lint workflow on the current branch.
- Confirm each provider/model ID and authentication in the actual runtime environment.
- Verify quote freshness, instrument availability, market hours, and fees separately.
- Treat the feature as experimental until these checks pass. No win-rate or profitability is promised.
