"""CLI entrypoint for near-agent."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .agent import run_agent
from .config import Config


def main():
    parser = argparse.ArgumentParser(
        prog="near-agent",
        description="Autonomous agent for market.near.ai — discover, bid, execute, deliver",
    )
    parser.add_argument("-c", "--config", default="config.toml", help="Path to config file")
    parser.add_argument("--cycles", type=int, default=1, help="Number of cycles to run (default: 1)")
    parser.add_argument("--continuous", action="store_true", help="Run continuously until stopped")

    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Run the agent (default)")
    run_parser.add_argument("--cycles", type=int, default=1, help="Number of cycles (default: 1)")
    run_parser.add_argument("--continuous", action="store_true", help="Run continuously")
    sub.add_parser("status", help="Show agent status and balance")
    sub.add_parser("bids", help="List active bids")
    sub.add_parser("pending", help="List deliverables waiting for approval")
    submit_parser = sub.add_parser("submit", help="Approve and submit a pending deliverable")
    submit_parser.add_argument("job_id", help="Job ID to submit (or 'all')")

    args = parser.parse_args()
    config = Config.load(args.config)

    if args.command == "status":
        asyncio.run(_show_status(config))
    elif args.command == "bids":
        asyncio.run(_show_bids(config))
    elif args.command == "pending":
        _show_pending(config)
    elif args.command == "submit":
        asyncio.run(_submit_pending(config, args.job_id))
    else:
        print(f"\n  near-agent v0.1.0")
        print(f"  Agent: {config.market.handle}")
        print(f"  Strategy: {config.agent.bid_strategy}")
        print(f"  Skills: {', '.join(config.agent.skills)}\n")
        asyncio.run(run_agent(config, cycles=args.cycles, continuous=args.continuous))


async def _show_status(config: Config):
    from .api import MarketClient
    client = MarketClient(config.market.base_url, config.market.api_key)
    try:
        profile = await client.me()
        wallet = await client.balance()
        print(f"\n  Agent: {profile.get('handle')}")
        print(f"  ID: {profile.get('agent_id')}")
        print(f"  NEAR Account: {profile.get('near_account_id')}")
        print(f"  Balance: {wallet.get('balance', '0')} NEAR")
        print(f"  Reputation: {profile.get('reputation_score', 0)}/100")
        print(f"  Jobs completed: {profile.get('jobs_completed', 0)}")
        print(f"  Total earned: {profile.get('total_earned', '0')} NEAR\n")
    finally:
        await client.close()


async def _show_bids(config: Config):
    from .api import MarketClient
    client = MarketClient(config.market.base_url, config.market.api_key)
    try:
        bids = await client.my_bids()
        if not bids:
            print("\n  No active bids.\n")
            return
        print(f"\n  Active bids ({len(bids)}):\n")
        for b in bids:
            print(f"  [{b.status:>10}] {b.amount} NEAR — Job: {b.job_id[:8]}...")
        print()
    finally:
        await client.close()


def _show_pending(config: Config):
    import json
    pending_dir = Path(config.logging.transcript_dir) / "pending"
    if not pending_dir.exists():
        print("\n  No pending deliverables.\n")
        return
    files = sorted(pending_dir.glob("*.json"))
    if not files:
        print("\n  No pending deliverables.\n")
        return
    print(f"\n  Pending deliverables ({len(files)}):\n")
    for f in files:
        data = json.loads(f.read_text())
        print(f"  [{data.get('quality_score', '?')}/100] {data['job_title']}")
        print(f"           Job ID: {data['job_id']}")
        print(f"           Bid: {data.get('bid_amount', '?')} NEAR")
        print(f"           File: {f}")
        print()
    print(f"  To approve: near-agent submit <job_id>")
    print(f"  To review:  cat {pending_dir}/<job_id>.md\n")


async def _submit_pending(config: Config, job_id: str):
    import json
    from .api import MarketClient
    from .executor import submit_work
    from .notifier import notify_submitted
    from .transcript import Transcript

    pending_dir = Path(config.logging.transcript_dir) / "pending"

    if job_id == "all":
        files = sorted(pending_dir.glob("*.json"))
    else:
        files = [pending_dir / f"{job_id}.json"]

    if not files or not files[0].exists():
        print(f"\n  No pending deliverable for job {job_id}\n")
        return

    client = MarketClient(config.market.base_url, config.market.api_key)
    transcript = Transcript(config.logging.transcript_dir)

    try:
        for f in files:
            if not f.exists():
                continue
            data = json.loads(f.read_text())
            job = await client.get_job(data["job_id"])

            print(f"\n  Submitting: {data['job_title']} (score: {data.get('quality_score', '?')}/100)")
            success = await submit_work(client, job, data["deliverable"], transcript)
            if success:
                print(f"  Submitted successfully!")
                f.unlink()  # remove .json
                md_file = f.with_suffix(".md")
                if md_file.exists():
                    md_file.unlink()
                # Send confirmation email
                email = config.notify.email
                rkey = config.notify.resend_api_key
                if email and rkey:
                    notify_submitted(email, data["job_title"], data["job_id"], data.get("bid_amount", "?"), api_key=rkey)
                    print(f"  Confirmation email sent to {email}")
            else:
                print(f"  Submission failed!")
    finally:
        transcript.save()
        await client.close()


if __name__ == "__main__":
    main()
