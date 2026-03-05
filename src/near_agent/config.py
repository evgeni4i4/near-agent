"""Configuration loader."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MarketConfig:
    base_url: str = "https://market.near.ai"
    api_key: str = ""
    agent_id: str = ""
    handle: str = ""


@dataclass
class AgentConfig:
    skills: list[str] = field(default_factory=lambda: ["python", "typescript", "api-development"])
    min_budget: float = 1.0
    max_bid: float = 10.0
    max_concurrent_jobs: int = 3
    poll_interval_seconds: int = 60
    bid_strategy: str = "competitive"


@dataclass
class LLMConfig:
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096


@dataclass
class LogConfig:
    transcript_dir: str = "transcripts"
    level: str = "INFO"


@dataclass
class NotifyConfig:
    email: str = ""
    auto_submit_delay_minutes: int = 10


@dataclass
class Config:
    market: MarketConfig = field(default_factory=MarketConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    logging: LogConfig = field(default_factory=LogConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)

    @classmethod
    def load(cls, path: str | Path = "config.toml") -> Config:
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p, "rb") as f:
            raw = tomllib.load(f)
        cfg = cls()
        if "market" in raw:
            cfg.market = MarketConfig(**raw["market"])
        if "agent" in raw:
            cfg.agent = AgentConfig(**raw["agent"])
        if "llm" in raw:
            cfg.llm = LLMConfig(**raw["llm"])
        if "logging" in raw:
            cfg.logging = LogConfig(**raw["logging"])
        if "notify" in raw:
            cfg.notify = NotifyConfig(**raw["notify"])
        return cfg
