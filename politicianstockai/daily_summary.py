from datetime import datetime, timezone

from pydantic import BaseModel
from pydantic_ai import Agent

from politicianstockai.config import get_settings
from politicianstockai.models import DailySummary, FlaggedTicker

INSTRUCTIONS = """\
You summarize a day of congressional stock trading activity for someone who wants a
quick starting point before digging in themselves. You're given the tickers flagged
today by pattern-detection rules, each with the specific reasons it was flagged.

Write a short summary (3-5 sentences) covering: how many tickers were flagged, and any
standout cross-cutting patterns (e.g. several tickers showing cross-chamber overlap, a
cluster of buy-heavy activity, unusually high volume). Then pick 2-4 tickers most worth
investigating first and explain why in one line each.

This is a starting point for further investigation, not a final analysis or financial
advice — don't speculate about specific causes here, that's handled by per-ticker
research elsewhere.
"""


class DailySummaryDraft(BaseModel):
    summary: str
    highlighted_tickers: list[str]


def build_summary_agent() -> Agent[None, DailySummaryDraft]:
    settings = get_settings()
    return Agent(settings.research_model, instructions=INSTRUCTIONS, output_type=DailySummaryDraft)


async def generate_daily_summary(flagged: list[FlaggedTicker], trades_scanned: int) -> DailySummary:
    today = datetime.now(timezone.utc).date().isoformat()
    now = datetime.now(timezone.utc)

    if not flagged:
        return DailySummary(
            date=today,
            summary=f"Scanned {trades_scanned} disclosures today. No notable patterns flagged.",
            highlighted_tickers=[],
            generated_at=now,
        )

    lines = [f"Scanned {trades_scanned} disclosures today. {len(flagged)} tickers flagged:"]
    for f in flagged:
        lines.append(f"- {f.ticker} (score {f.score}): {'; '.join(f.reasons)}")
    prompt = "\n".join(lines)

    agent = build_summary_agent()
    result = await agent.run(prompt)
    draft = result.output

    return DailySummary(
        date=today,
        summary=draft.summary,
        highlighted_tickers=draft.highlighted_tickers,
        generated_at=now,
    )
