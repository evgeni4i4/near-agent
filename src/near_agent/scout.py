"""Job Scout — discovers and evaluates marketplace jobs using LLM scoring."""
from __future__ import annotations

import anthropic

from .api import Job, MarketClient
from .config import Config
from .transcript import Transcript

# Cache of already-evaluated job IDs → avoids re-scoring the same jobs every cycle
_evaluated_jobs: dict[str, int] = {}  # job_id → fit_score

SCORE_PROMPT = """\
You are evaluating a job listing on an AI agent marketplace to decide if our agent should bid.

Our agent's capabilities:
- Skills: {skills}
- Can generate code (Python, TypeScript, Bash, YAML)
- Can write documentation, guides, blog posts, technical reports
- Can do research and analysis
- Can create GitHub repos, gists, Action workflows
- Can do code review and security audits

Job details:
- Title: {title}
- Budget: {budget} NEAR
- Tags: {tags}
- Bids already placed: {bid_count}
- Description:
{description}

Evaluate this job and respond with EXACTLY this JSON format (no other text):
{{
  "fit_score": <0-100>,
  "can_complete": <true/false>,
  "estimated_hours": <number>,
  "reasoning": "<1-2 sentences>",
  "proposed_approach": "<1-2 sentences on how to do it>",
  "bid_amount": "<suggested bid in NEAR as string>"
}}

Scoring guidance:
- fit_score 80+: We can definitely do this well
- fit_score 50-79: We can probably do this adequately
- fit_score <50: Poor fit, likely skip
- Set can_complete=false if the job requires physical presence, specific hardware, or deep domain expertise we lack
- bid_amount should be at or slightly below the budget for competitive positioning
"""


async def evaluate_job(job: Job, config: Config) -> dict | None:
    """Use LLM to score a job's fit for our agent. Returns parsed evaluation or None on failure."""
    if not job.description or len(job.description) < 30:
        return None

    prompt = SCORE_PROMPT.format(
        skills=", ".join(config.agent.skills),
        title=job.title,
        budget=job.budget_amount or "unspecified",
        tags=", ".join(job.tags),
        bid_count=job.bid_count,
        description=job.description[:3000],
    )

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=config.llm.model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Extract JSON from response
        if "{" in text:
            json_str = text[text.index("{"):text.rindex("}") + 1]
            import json
            return json.loads(json_str)
    except Exception as e:
        import sys
        print(f"    [debug] LLM eval error for '{job.title[:40]}': {e}", file=sys.stderr)
        return None
    return None


async def discover_and_rank(
    client: MarketClient,
    config: Config,
    transcript: Transcript,
    limit: int = 20,
) -> list[tuple[Job, dict]]:
    """Discover open jobs, evaluate with LLM, return ranked (job, evaluation) pairs."""
    transcript.log("discover", f"Fetching open jobs from marketplace (limit={limit})")

    jobs = await client.list_jobs(status="open", sort="created_at", order="desc", limit=limit)

    # Pre-filter: skip test jobs, require budget
    candidates = []
    for j in jobs:
        if j.title.strip().lower() in ("job1", "test job", ""):
            continue
        if j.budget_float < config.agent.min_budget:
            continue
        if j.job_type == "competition":
            continue  # Handle competitions separately
        candidates.append(j)

    transcript.log("discover", f"Found {len(candidates)} candidate jobs (filtered from {len(jobs)} total)")

    # Filter out already-evaluated jobs
    new_candidates = [j for j in candidates if j.job_id not in _evaluated_jobs]
    cached_count = len(candidates) - len(new_candidates)
    if cached_count:
        transcript.log("discover", f"Skipping {cached_count} already-evaluated jobs")

    ranked: list[tuple[Job, dict]] = []
    for job in new_candidates[:15]:  # Evaluate top 15 to save LLM calls
        # Fetch full job details (list endpoint may truncate description)
        try:
            job = await client.get_job(job.job_id)
        except Exception:
            pass
        evaluation = await evaluate_job(job, config)
        score = evaluation.get("fit_score", 0) if evaluation else 0
        _evaluated_jobs[job.job_id] = score

        if evaluation and evaluation.get("can_complete") and score >= 50:
            ranked.append((job, evaluation))
            transcript.log(
                "evaluate",
                f"Score {evaluation['fit_score']}/100 — {job.title} ({job.budget_amount}N)",
                {"job_id": job.job_id, "fit_score": evaluation["fit_score"], "reasoning": evaluation.get("reasoning", "")},
            )
        else:
            transcript.log("skip", f"Score {score}/100 — {job.title}")

    ranked.sort(key=lambda x: x[1].get("fit_score", 0), reverse=True)
    return ranked
