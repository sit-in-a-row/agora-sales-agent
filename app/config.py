from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = Path("/tmp/agora-sales-agent-runs") if os.getenv("VERCEL") else ROOT / "runs"
STATIC_DIR = ROOT / "app" / "static"
KNOWLEDGE_DIR = ROOT / "knowledge" / "agora_sales_retrieval_dataset_v1"
PROMPTS_DIR = ROOT / "docs" / "prompts"
DEFAULT_CONFIG_PATH = ROOT / "config" / "default_config.json"

RUNS_DIR.mkdir(parents=True, exist_ok=True)


def load_default_config() -> dict[str, Any]:
    return json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


DEFAULT_CONFIG = load_default_config()


@dataclass(slots=True)
class RunOptions:
    source_mode: str = "impt_all"
    max_leads: int = 0
    demo_mode: bool = False
    quick_mode: bool = True
    sender_name: str = "박세빈"
    sender_title: str = "한국 매니저"
    sender_signature: str = "박세빈 (Sebin Park)"
    concurrency: int = int(DEFAULT_CONFIG.get("concurrency", 4))
    selected_visitor_ids: list[str] = field(default_factory=list)
    excluded_visitor_ids: list[str] = field(default_factory=list)
    email_style_reference: str = ""
