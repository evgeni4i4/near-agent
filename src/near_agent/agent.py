"""Agent Core — main orchestration loop."""
from __future__ import annotations

import asyncio

from .api import MarketClient
from .bidder import place_bids
from .config import Config
from .executor import check_and_execute_awarded
from .scout import discover_and_rank
from .transcript import Transcript


async def run_cycle(
    client: MarketClient,
    config: Config,
    transcript: Transcript,
) -> dict:
    """Run one full agent cycle: discover → evaluate → bid → execute → submit."""
    stats = {"jobs_found": 0, "jobs_evaluated": 0, "bids_placed": 0, "jobs_completed": 0}

    # Phase 1: Check for awarded jobs and execute
    transcript.log("status", "Phase 1: Checking for awarded jobs...")
    completed = await check_and_execute_awarded(client, config, transcript)
    stats["jobs_completed"] = len(completed)

    # Phase 2: Discover and evaluate new jobs
    transcript.log("status", "Phase 2: Discovering and evaluating jobs...")
    ranked = await discover_and_rank(client, config, transcript)
    stats["jobs_found"] = len(ranked)
    stats["jobs_evaluated"] = len(ranked)

    # Phase 3: Place bids on best matches
    if ranked:
        transcript.log("status", f"Phase 3: Placing bids on top {min(3, len(ranked))} jobs...")
        placed = await place_bids(client, ranked, config, transcript)
        stats["bids_placed"] = len(placed)
    else:
        transcript.log("status", "Phase 3: No suitable jobs found for bidding")

    return stats


async def run_agent(config: Config, cycles: int = 1, continuous: bool = False):
    """Run the agent for N cycles or continuously."""
    transcript = Transcript(config.logging.transcript_dir)
    client = MarketClient(config.market.base_url, config.market.api_key)

    transcript.log("start", f"Agent starting — handle={config.market.handle}, cycles={'continuous' if continuous else cycles}")

    # Show agent status
    try:
        profile = await client.me()
        wallet = await client.balance()
        transcript.log("status", f"Agent profile loaded", {
            "handle": profile.get("handle"),
            "reputation": profile.get("reputation_score", 0),
            "balance": wallet.get("balance", "0"),
        })
    except Exception as e:
        transcript.log("error", f"Failed to load profile: {e}")

    cycle_num = 0
    total_stats = {"jobs_found": 0, "jobs_evaluated": 0, "bids_placed": 0, "jobs_completed": 0}

    try:
        while True:
            cycle_num += 1
            transcript.log("status", f"=== Cycle {cycle_num} ===")

            stats = await run_cycle(client, config, transcript)
            for k in total_stats:
                total_stats[k] += stats[k]

            transcript.log("status", f"Cycle {cycle_num} complete", stats)

            if not continuous and cycle_num >= cycles:
                break

            transcript.log("status", f"Sleeping {config.agent.poll_interval_seconds}s before next cycle...")
            await asyncio.sleep(config.agent.poll_interval_seconds)

    except KeyboardInterrupt:
        transcript.log("status", "Agent stopped by user")
    finally:
        transcript.log("status", f"Session complete — totals", total_stats)
        md_path, json_path = transcript.save()
        print(f"\n  Transcript saved:")
        print(f"    Markdown: {md_path}")
        print(f"    JSON:     {json_path}")
        await client.close()
