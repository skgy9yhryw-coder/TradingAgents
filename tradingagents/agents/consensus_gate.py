"""Fail-closed independent model consensus and final ChatGPT veto."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tradingagents.consensus import MODEL_NAMES, evaluate_consensus
from tradingagents.llm_clients import build_llm_kwargs, create_llm_client

logger = logging.getLogger(__name__)


class DirectionVote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    direction: Literal["bullish", "bearish", "neutral"]
    rationale: str = Field(min_length=1, max_length=1200)


class JudgeReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    approved: bool
    rationale: str = Field(min_length=1, max_length=1200)


def _client(config: dict, provider: str, model: str):
    if not provider or not model:
        raise ValueError("consensus provider and model must be configured")
    kwargs = build_llm_kwargs({**config, "llm_provider": provider})
    return create_llm_client(provider, model, **kwargs).get_llm()


def create_consensus_node(config: dict):
    """Create a graph node; provider calls are lazy and any failure means No Trade."""
    def consensus_node(state: dict) -> dict:
        pm_decision = state.get("final_trade_decision", "")
        pm_rating = state.get("final_rating", "REVIEW")
        votes: dict[str, str | None] = {}
        rationales: dict[str, str] = {}
        try:
            prompts = {
                "claude": (
                    config.get("consensus_claude_provider", "anthropic"),
                    config.get("consensus_claude_model", ""),
                ),
                "grok": (
                    config.get("consensus_grok_provider", "xai"),
                    config.get("consensus_grok_model", ""),
                ),
                "deepseek": (
                    config.get("consensus_deepseek_provider", "deepseek"),
                    config.get("consensus_deepseek_model", ""),
                ),
            }
            for name in MODEL_NAMES:
                provider, model = prompts[name]
                llm = _client(config, provider, model)
                structured = llm.with_structured_output(DirectionVote)
                result = structured.invoke([
                    ("system", "Independently assess the supplied market analysis. Return exactly one direction: bullish, bearish, or neutral. Do not infer missing evidence. This is not an order."),
                    ("human", f"Instrument: {state.get('company_of_interest', '')}\nAsset type: {state.get('asset_type', '')}\nTrade date: {state.get('trade_date', '')}\nInstrument context: {state.get('instrument_context', '')}\nMarket report: {state.get('market_report', '')}\nNews report: {state.get('news_report', '')}\nSentiment report: {state.get('sentiment_report', '')}\nFundamentals report: {state.get('fundamentals_report', '')}\nTrader proposal: {state.get('trader_investment_plan', '')}\nPortfolio decision: {pm_decision}"),
                ])
                if not isinstance(result, DirectionVote):
                    result = DirectionVote.model_validate(result, strict=True)
                votes[name] = result.direction
                rationales[name] = result.rationale

            outcome = evaluate_consensus(votes)
            if not outcome.approved:
                raise ValueError(outcome.reason)

            normalized_rating = str(pm_rating).strip().lower()
            pm_direction = (
                "bullish" if normalized_rating in {"buy", "overweight"}
                else "bearish" if normalized_rating in {"sell", "underweight"}
                else None
            )
            if pm_direction != outcome.direction:
                raise ValueError("portfolio_manager_direction_mismatch")

            judge_model = config.get("consensus_judge_model", "")
            judge_provider = config.get("consensus_judge_provider", "chatgpt")
            judge_llm = _client(config, judge_provider, judge_model)
            judge = judge_llm.with_structured_output(JudgeReview).invoke([
                ("system", "You are a conservative veto-only reviewer. Approve only if the unanimous 3-model direction is logically supported by the supplied evidence, risks are addressed, and there are no material contradictions. You may veto but must never change the direction. Return strict structured output."),
                ("human", f"Unanimous direction: {outcome.direction}\nVotes: {votes}\nRationales: {rationales}\nPortfolio decision: {pm_decision}\nReports: {state.get('market_report', '')}\n{state.get('news_report', '')}\n{state.get('sentiment_report', '')}\n{state.get('fundamentals_report', '')}"),
            ])
            if not isinstance(judge, JudgeReview):
                judge = JudgeReview.model_validate(judge, strict=True)
            if not judge.approved:
                raise ValueError("chatgpt_judge_veto: " + judge.rationale)

            label = "BUY / LONG" if outcome.direction == "bullish" else "SELL / SHORT"
            return {
                "consensus_votes": votes,
                "consensus_rationales": rationales,
                "consensus_status": "approved",
                "consensus_direction": outcome.direction,
                "judge_approved": True,
                "judge_rationale": judge.rationale,
                "portfolio_manager_original_decision": pm_decision,
                "portfolio_manager_original_rating": pm_rating,
                "final_trade_decision": f"CONSENSUS APPROVED — {label}\n3/3 independent model votes; ChatGPT judge approved.\nOriginal portfolio decision: {pm_decision}",
                "final_rating": "Buy" if outcome.direction == "bullish" else "Sell",
            }
        except Exception as exc:
            logger.warning("Consensus gate failed closed: %s", exc)
            return {
                "consensus_votes": votes,
                "consensus_rationales": rationales,
                "consensus_status": "no_trade",
                "consensus_direction": None,
                "judge_approved": False,
                "judge_rationale": f"Not approved: {type(exc).__name__}: {exc}",
                "portfolio_manager_original_decision": pm_decision,
                "portfolio_manager_original_rating": pm_rating,
                "final_trade_decision": f"NO TRADE — consensus gate not satisfied. Original portfolio decision: {pm_decision}",
                "final_rating": "REVIEW",
            }

    return consensus_node
