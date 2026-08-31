from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import PROMPTS_DIR

EMAIL_GUIDE_DIR = PROMPTS_DIR.parent / "email_guides"


PROMPT_FILES = {
    "entity": "01_entity_resolver_system.md",
    "entity_web": "01b_entity_resolver_web_system.md",
    "research": "02_account_researcher_system.md",
    "scoring": "03_lead_scorer_system.md",
    "strategy": "04_sales_strategist_system.md",
    "writer": "05_email_writer_system.md",
    "review": "06_sales_reviewer_system.md",
}


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    base = (PROMPTS_DIR / PROMPT_FILES[name]).read_text(encoding="utf-8")
    if name == "writer":
        guide_path = EMAIL_GUIDE_DIR / "agora_deterministic_template_guide.md"
        if guide_path.exists():
            base += "\n\n# MANDATORY DETERMINISTIC TEMPLATE GUIDE\n\n"
            base += guide_path.read_text(encoding="utf-8")
    return base


SUPPLEMENTAL_RESEARCH_PROMPT = """
당신은 Agora Korea의 Account Intelligence Researcher다.
기존 회사 research에서 부족했던 특정 lead-level 질문만 보완한다.
반드시 웹 검색을 사용하고, 한국시장/local operation에 직접 관련된 근거를 우선한다.
입력된 supplemental queries에 집중하며 검색 범위를 넓히지 않는다.
모든 factual claim은 evidence ID와 exact source URL을 포함한다.
확인되지 않으면 unknown으로 남긴다.
""".strip()


REWRITE_PROMPT = """
당신은 기존 Email Writer와 동일한 역할이다.
Reviewer가 지적한 문제만 수정한다.
새로운 사실, 새로운 사례, 새로운 수치를 추가하지 않는다.
기존 전략의 approved writer slots와 evidence references의 범위 안에서 더 정확하고 자연스럽게 다시 작성한다.
빈 slot을 새로 추론해서 채우지 않는다.
""".strip()
