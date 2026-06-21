from datetime import datetime, timezone

import httpx
from pydantic_ai import Agent, RunContext

from politicianstockai.config import get_settings
from politicianstockai.models import FlaggedTicker, SearchResult, StockReport

SERPER_URL = "https://google.serper.dev/search"

INSTRUCTIONS = """\
You are a financial research assistant. You are given a stock ticker that has been
flagged for unusual congressional trading activity, along with the specific reasons
it was flagged. Use the search_web tool to research recent news about the company
and explain what is likely driving the trading activity (earnings, regulation,
M&A, sector trends, etc). Cite the source URLs you actually used. If you cannot
find a clear driver, say so and set confidence to "low".
"""


async def serper_search(query: str, num_results: int = 5) -> list[SearchResult]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            SERPER_URL,
            headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
            json={"q": query, "num": num_results},
        )
    resp.raise_for_status()
    organic = resp.json().get("organic", [])
    return [
        SearchResult(title=r.get("title", ""), link=r.get("link", ""), snippet=r.get("snippet", ""))
        for r in organic[:num_results]
    ]


def build_research_agent() -> Agent[None, StockReport]:
    settings = get_settings()
    agent = Agent(settings.research_model, instructions=INSTRUCTIONS, output_type=StockReport)

    @agent.tool
    async def search_web(ctx: RunContext[None], query: str) -> list[SearchResult]:
        """Search Google for recent news/context about a company or ticker."""
        return await serper_search(query)

    return agent


async def generate_report(flagged: FlaggedTicker) -> StockReport:
    agent = build_research_agent()
    prompt = (
        f"Ticker: {flagged.ticker}\n"
        f"Flag reasons: {'; '.join(flagged.reasons)}\n"
        f"Window: {flagged.window_start} to {flagged.window_end}\n"
        "Research this ticker and produce a StockReport."
    )
    result = await agent.run(prompt)
    report = result.output
    report.generated_at = datetime.now(timezone.utc)
    return report
