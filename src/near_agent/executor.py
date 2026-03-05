"""Work Executor — LLM-powered task completion for awarded jobs."""
from __future__ import annotations

import hashlib

import anthropic

from .api import Job, MarketClient
from .config import Config
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


async def execute_job(
    client: MarketClient,
    job: Job,
    config: Config,
    transcript: Transcript,
) -> str | None:
    """Execute an awarded job by generating a deliverable via LLM.

    Returns the deliverable text or None on failure.
    """
    transcript.log("execute", f"Starting work on: {job.title}", {"job_id": job.job_id})

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
        deliverable = response.content[0].text.strip()
    except Exception as e:
        transcript.log("error", f"LLM execution failed: {e}")
        return None

    transcript.log(
        "execute",
        f"Deliverable generated ({len(deliverable)} chars)",
        {"preview": deliverable[:200]},
    )
    return deliverable


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
    """Check for awarded bids, execute work, submit deliverables. Returns list of completed job IDs."""
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

        deliverable = await execute_job(client, job, config, transcript)
        if deliverable:
            success = await submit_work(client, job, deliverable, transcript)
            if success:
                completed.append(job.job_id)

    return completed
