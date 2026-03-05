"""Bid Engine — composes and places bids with LLM-generated proposals."""
from __future__ import annotations

import anthropic

from .api import Job, MarketClient
from .config import Config
from .transcript import Transcript

PROPOSAL_PROMPT = """\
Write a concise, professional bid proposal for this marketplace job. You are an AI agent called "ivinco_agent" bidding on work.

Job title: {title}
Job description (excerpt):
{description}

Our planned approach: {approach}
Our estimated delivery time: {eta_hours} hours

Write a proposal (3-5 sentences) that:
1. Shows you understand the specific requirements
2. Briefly explains your approach
3. Mentions relevant capabilities
4. Is confident but not arrogant

Return ONLY the proposal text, no quotes or formatting.
"""


async def compose_proposal(job: Job, evaluation: dict, config: Config) -> str:
    """Generate a tailored bid proposal using LLM."""
    client = anthropic.Anthropic()
    prompt = PROPOSAL_PROMPT.format(
        title=job.title,
        description=job.description[:2000],
        approach=evaluation.get("proposed_approach", "systematic analysis and delivery"),
        eta_hours=evaluation.get("estimated_hours", 24),
    )
    try:
        response = client.messages.create(
            model=config.llm.model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception:
        return f"I can complete this job efficiently. My approach: {evaluation.get('proposed_approach', 'systematic delivery with quality focus')}. Estimated delivery within {evaluation.get('estimated_hours', 24)} hours."


async def place_bids(
    client: MarketClient,
    ranked_jobs: list[tuple[Job, dict]],
    config: Config,
    transcript: Transcript,
    max_bids: int = 3,
) -> list[dict]:
    """Place bids on the top-ranked jobs."""
    placed = []
    active_bids = await client.my_bids()
    active_job_ids = {b.job_id for b in active_bids if b.status == "pending"}

    for job, evaluation in ranked_jobs[:max_bids]:
        if job.job_id in active_job_ids:
            transcript.log("skip", f"Already bid on: {job.title}")
            continue

        bid_amount = evaluation.get("bid_amount", str(job.budget_float))
        try:
            bid_amount_f = float(bid_amount)
        except (ValueError, TypeError):
            bid_amount_f = job.budget_float
        if bid_amount_f > config.agent.max_bid:
            bid_amount_f = config.agent.max_bid
        bid_amount = str(round(bid_amount_f, 2))

        eta_hours = evaluation.get("estimated_hours", 24)
        eta_seconds = int(eta_hours * 3600)

        proposal = await compose_proposal(job, evaluation, config)

        transcript.log(
            "bid",
            f"Bidding {bid_amount} NEAR on: {job.title}",
            {"job_id": job.job_id, "amount": bid_amount, "eta_hours": eta_hours, "proposal_preview": proposal[:100]},
        )

        try:
            bid = await client.place_bid(job.job_id, bid_amount, eta_seconds, proposal)
            placed.append({"job": job, "bid": bid, "evaluation": evaluation})
            transcript.log("bid", f"Bid placed successfully: {bid.bid_id}")
        except Exception as e:
            transcript.log("error", f"Failed to bid on {job.title}: {e}")

    return placed
