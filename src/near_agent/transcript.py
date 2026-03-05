"""Demo transcript logger — captures agent decisions for competition submission."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path


class Transcript:
    """Records agent actions into a Markdown demo log + structured JSON."""

    def __init__(self, output_dir: str = "transcripts"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.entries: list[dict] = []
        self.start_time = time.monotonic()
        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    def log(self, action: str, detail: str, data: dict | None = None):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(time.monotonic() - self.start_time, 1),
            "action": action,
            "detail": detail,
            "data": data or {},
        }
        self.entries.append(entry)
        icon = {
            "discover": "🔍", "evaluate": "🧠", "bid": "💰",
            "awarded": "🏆", "execute": "⚙️", "submit": "📦",
            "message": "💬", "skip": "⏭️", "error": "❌",
            "start": "🚀", "status": "📊",
        }.get(action, "▸")
        print(f"  {icon} [{entry['elapsed_s']:>7.1f}s] {action}: {detail}")

    def save(self):
        # JSON log
        json_path = self.output_dir / f"session_{self.session_id}.json"
        with open(json_path, "w") as f:
            json.dump(self.entries, f, indent=2)

        # Markdown transcript
        md_path = self.output_dir / f"session_{self.session_id}.md"
        with open(md_path, "w") as f:
            f.write(f"# Agent Market Demo — Session {self.session_id}\n\n")
            f.write(f"**Started:** {self.entries[0]['timestamp'] if self.entries else 'N/A'}\n")
            f.write(f"**Entries:** {len(self.entries)}\n\n---\n\n")
            for e in self.entries:
                f.write(f"### [{e['elapsed_s']}s] {e['action'].upper()}\n\n")
                f.write(f"{e['detail']}\n\n")
                if e["data"]:
                    f.write(f"```json\n{json.dumps(e['data'], indent=2)[:500]}\n```\n\n")
        return md_path, json_path
