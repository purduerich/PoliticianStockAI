from datetime import datetime, timezone

from pydantic import BaseModel
from pydantic_ai import Agent

from politicianstockai.config import get_settings
from politicianstockai.models import DailySummary, FlaggedTicker, StockReport

INSTRUCTIONS = """\
You summarize the results of a scan of recently-disclosed congressional stock trading
activity, for someone who wants a quick starting point before digging in themselves.
You're given the tickers flagged by pattern-detection rules in this scan, each with the
specific reasons it was flagged. For most tickers you're also given real AI research
findings — already backed by actual web searches — covering what news/context might
explain the activity, plus a confidence level for that finding.

Weave the specific research findings into your narrative where you have them (e.g.
"GOOGL's flag coincides with its May Search Core Update") rather than only restating
pattern-detection reasons. Don't invent findings beyond what's given to you, and don't
overstate confidence beyond what's provided.

Important: these are recently *disclosed* trades, not necessarily trades that happened
today. By law, members of Congress can file a disclosure up to 45 days after a trade,
so the underlying trades may be from days or weeks before this scan ran. Do not say
trades "happened today" or imply this reflects today's market activity — refer to it as
recently disclosed/reported activity, or activity from this scan.

Write a short summary (3-5 sentences) covering: how many tickers were flagged in this
scan, and any standout cross-cutting patterns (e.g. several tickers showing
cross-chamber overlap, a cluster of buy-heavy activity, unusually high volume), citing
specific research findings where available. Within this prose summary, pick 2-4 tickers
most worth investigating first and explain why in one line each.

For the separate `highlighted_tickers` field: list ONLY the bare ticker symbols you just
discussed (e.g. ["ACN", "NVDA"]) — no extra words, descriptions, or reasons in that
field. The "why" belongs only in the summary text.

This is a starting point for further investigation, not a final analysis or financial
advice.
"""

MAX_SOURCES = 10


class DailySummaryDraft(BaseModel):
    summary: str
    highlighted_tickers: list[str]


def build_summary_agent() -> Agent[None, DailySummaryDraft]:
    settings = get_settings()
    return Agent(settings.research_model, instructions=INSTRUCTIONS, output_type=DailySummaryDraft)


def _aggregate_sources(reports: dict[str, StockReport]) -> list[str]:
    seen: list[str] = []
    for report in reports.values():
        for source in report.sources:
            if source not in seen:
                seen.append(source)
    return seen[:MAX_SOURCES]


def _sanitize_highlighted_tickers(raw: list[str], valid_tickers: set[str]) -> list[str]:
    """Keep only entries that are exactly a flagged ticker symbol, guarding against
    the model drifting into descriptive text instead of bare symbols."""
    sanitized = []
    for entry in raw:
        candidate = entry.split()[0].strip(" -:") if entry.split() else entry
        if candidate in valid_tickers and candidate not in sanitized:
            sanitized.append(candidate)
    return sanitized


async def generate_daily_summary(
    flagged: list[FlaggedTicker], trades_scanned: int, reports: dict[str, StockReport]
) -> DailySummary:
    today = datetime.now(timezone.utc).date().isoformat()
    now = datetime.now(timezone.utc)

    if not flagged:
        return DailySummary(
            date=today,
            summary=f"This scan reviewed {trades_scanned} recently disclosed trades. No notable patterns flagged.",
            highlighted_tickers=[],
            sources=[],
            generated_at=now,
        )

    lines = [f"This scan reviewed {trades_scanned} recently disclosed trades. {len(flagged)} tickers flagged:"]
    for f in flagged:
        lines.append(f"- {f.ticker} (score {f.score}): {'; '.join(f.reasons)}")
        report = reports.get(f.ticker)
        if report is not None:
            lines.append(
                f"  Research finding ({report.confidence} confidence): {report.summary} "
                f"Likely drivers: {'; '.join(report.likely_drivers)}"
            )
    prompt = "\n".join(lines)

    agent = build_summary_agent()
    result = await agent.run(prompt)
    draft = result.output

    valid_tickers = {f.ticker for f in flagged}
    return DailySummary(
        date=today,
        summary=draft.summary,
        highlighted_tickers=_sanitize_highlighted_tickers(draft.highlighted_tickers, valid_tickers),
        sources=_aggregate_sources(reports),
        generated_at=now,
    )
