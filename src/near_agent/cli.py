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

    args = parser.parse_args()
    config = Config.load(args.config)

    if args.command == "status":
        asyncio.run(_show_status(config))
    elif args.command == "bids":
        asyncio.run(_show_bids(config))
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


if __name__ == "__main__":
    main()
