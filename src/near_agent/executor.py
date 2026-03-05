"""Work Executor — multi-pass LLM execution with email notifications."""
from __future__ import annotations

import asyncio
import hashlib

import anthropic

from .api import Job, MarketClient
from .config import Config
from .notifier import notify_bid_awarded, notify_deliverable_ready, notify_submitted, notify_error
from .transcript import Transcript

WORK_PROMPT = """\
You are an AI agent completing a job on a freelance marketplace. Produce the deliverable now.

Job title: {title}
Job description:
{description}

Requirements:
- Produce a COMPLETE deliverable that fully satisfies the job description
- Format as Markdown
- If code is required, include working code blocks with comments
- If research/writing is required, produce a thorough, well-structured document
- If a report is required, include findings, analysis, and recommendations
- Be thorough — this deliverable determines if you get paid

Output ONLY the deliverable content. No preamble, no meta-commentary.
"""

REVIEW_PROMPT = """\
You are reviewing a deliverable produced by an AI agent for a freelance job.

Job title: {title}
Job description:
{description}

--- DELIVERABLE ---
{deliverable}
--- END DELIVERABLE ---

Evaluate this deliverable critically. Score it 0-100 and provide specific feedback.

Respond in this exact JSON format:
{{
  "score": <int 0-100>,
  "strengths": ["..."],
  "weaknesses": ["..."],
  "missing": ["..."],
  "suggestions": ["..."]
}}
"""

REFINE_PROMPT = """\
You are an AI agent refining a deliverable based on self-review feedback.

Job title: {title}
Job description:
{description}

--- ORIGINAL DELIVERABLE ---
{deliverable}
--- END DELIVERABLE ---

--- REVIEW FEEDBACK ---
{feedback}
--- END FEEDBACK ---

Produce an IMPROVED version of the deliverable that addresses the feedback.
Fix all weaknesses, fill in missing items, and apply the suggestions.
Output ONLY the improved deliverable content. No preamble, no meta-commentary.
"""


async def generate_deliverable(job: Job, config: Config) -> str | None:
    """Pass 1: Generate initial deliverable via LLM."""
    llm = anthropic.Anthropic()
    try:
        response = llm.messages.create(
            model=config.llm.model,
            max_tokens=config.llm.max_tokens,
            messages=[{"role": "user", "content": WORK_PROMPT.format(
                title=job.title,
                description=job.description[:4000],
            )}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        raise RuntimeError(f"LLM generation failed: {e}") from e


async def review_deliverable(job: Job, deliverable: str, config: Config) -> tuple[int, str]:
    """Pass 2: Self-review the deliverable. Returns (score, feedback_json)."""
    llm = anthropic.Anthropic()
    try:
        response = llm.messages.create(
            model=config.llm.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": REVIEW_PROMPT.format(
                title=job.title,
                description=job.description[:4000],
                deliverable=deliverable[:6000],
            )}],
        )
        feedback = response.content[0].text.strip()
        # Extract score from JSON response
        import json
        try:
            parsed = json.loads(feedback)
            score = int(parsed.get("score", 0))
        except (json.JSONDecodeError, ValueError):
            score = 50  # default if parsing fails
        return score, feedback
    except Exception as e:
        raise RuntimeError(f"LLM review failed: {e}") from e


async def refine_deliverable(job: Job, deliverable: str, feedback: str, config: Config) -> str | None:
    """Pass 3: Refine deliverable based on review feedback."""
    llm = anthropic.Anthropic()
    try:
        response = llm.messages.create(
            model=config.llm.model,
            max_tokens=config.llm.max_tokens,
            messages=[{"role": "user", "content": REFINE_PROMPT.format(
                title=job.title,
                description=job.description[:4000],
                deliverable=deliverable[:6000],
                feedback=feedback[:2000],
            )}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        raise RuntimeError(f"LLM refinement failed: {e}") from e


async def execute_job(
    client: MarketClient,
    job: Job,
    config: Config,
    transcript: Transcript,
) -> tuple[str | None, int]:
    """Execute an awarded job using multi-pass LLM generation.

    Returns (deliverable_text, quality_score) or (None, 0) on failure.
    """
    transcript.log("execute", f"Starting multi-pass execution: {job.title}", {"job_id": job.job_id})

    # Pass 1: Generate
    transcript.log("execute", "Pass 1/3: Generating initial deliverable...")
    try:
        deliverable = await generate_deliverable(job, config)
    except RuntimeError as e:
        transcript.log("error", str(e))
        return None, 0

    if not deliverable:
        transcript.log("error", "Pass 1 produced empty deliverable")
        return None, 0

    transcript.log("execute", f"Pass 1 complete ({len(deliverable)} chars)", {"preview": deliverable[:200]})

    # Pass 2: Self-review
    transcript.log("execute", "Pass 2/3: Self-reviewing deliverable...")
    try:
        score, feedback = await review_deliverable(job, deliverable, config)
    except RuntimeError as e:
        transcript.log("error", str(e))
        # If review fails, use the initial deliverable
        return deliverable, 50

    transcript.log("execute", f"Pass 2 complete — quality score: {score}/100", {"feedback_preview": feedback[:300]})

    # Pass 3: Refine (only if score < 85)
    if score < 85:
        transcript.log("execute", f"Pass 3/3: Refining deliverable (score {score} < 85 threshold)...")
        try:
            refined = await refine_deliverable(job, deliverable, feedback, config)
            if refined and len(refined) > len(deliverable) * 0.5:
                deliverable = refined
                transcript.log("execute", f"Pass 3 complete — refined ({len(deliverable)} chars)")
            else:
                transcript.log("execute", "Pass 3 produced unusable result, keeping original")
        except RuntimeError as e:
            transcript.log("error", f"Refinement failed, keeping original: {e}")
    else:
        transcript.log("execute", f"Skipping Pass 3 — quality score {score}/100 exceeds threshold")

    return deliverable, score


async def submit_work(
    client: MarketClient,
    job: Job,
    deliverable: str,
    transcript: Transcript,
) -> bool:
    """Submit a completed deliverable to the marketplace."""
    content_hash = "sha256:" + hashlib.sha256(deliverable.encode()).hexdigest()

    transcript.log("submit", f"Submitting deliverable for: {job.title}", {
        "job_id": job.job_id,
        "hash": content_hash,
        "length": len(deliverable),
    })

    try:
        result = await client.submit_deliverable(job.job_id, deliverable, content_hash)
        transcript.log("submit", f"Deliverable accepted by platform", {"result": str(result)[:200]})
        return True
    except Exception as e:
        transcript.log("error", f"Submission failed: {e}")
        return False


async def check_and_execute_awarded(
    client: MarketClient,
    config: Config,
    transcript: Transcript,
) -> list[str]:
    """Check for awarded bids, execute work with multi-pass, submit deliverables."""
    email = config.notify.email
    rkey = config.notify.resend_api_key
    delay_minutes = config.notify.auto_submit_delay_minutes

    bids = await client.my_bids()
    awarded = [b for b in bids if b.status == "accepted"]

    completed = []
    for bid in awarded:
        job = await client.get_job(bid.job_id)

        # Check if we already submitted
        if job.my_assignments:
            assignment = job.my_assignments[0]
            if assignment.get("status") in ("submitted", "accepted"):
                transcript.log("status", f"Already submitted for: {job.title}")
                continue

        transcript.log("awarded", f"Won bid on: {job.title} ({bid.amount} NEAR)")

        # Email: bid was awarded
        if email and rkey:
            notify_bid_awarded(email, job.title, bid.amount, job.job_id, api_key=rkey)
            transcript.log("notify", f"Sent bid-awarded email to {email}")

        # Multi-pass execution
        deliverable, score = await execute_job(client, job, config, transcript)

        if not deliverable:
            if email and rkey:
                notify_error(email, job.title, job.job_id, "Failed to generate deliverable", api_key=rkey)
            continue

        # Email: deliverable ready with preview — wait before auto-submit
        if email and rkey and delay_minutes > 0:
            notify_deliverable_ready(email, job.title, job.job_id, deliverable, score, api_key=rkey)
            transcript.log("notify", f"Sent deliverable-preview email, waiting {delay_minutes}m before submit")
            await asyncio.sleep(delay_minutes * 60)

        # Submit
        success = await submit_work(client, job, deliverable, transcript)
        if success:
            completed.append(job.job_id)
            if email and rkey:
                notify_submitted(email, job.title, job.job_id, bid.amount, api_key=rkey)
                transcript.log("notify", f"Sent submission-confirmation email")
        else:
            if email and rkey:
                notify_error(email, job.title, job.job_id, "Submission to marketplace failed", api_key=rkey)

    return completed
