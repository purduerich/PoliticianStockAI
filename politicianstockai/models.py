from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Trade(BaseModel):
    chamber: Literal["senate", "house"]
    symbol: str
    politician: str
    owner: str | None = None
    asset_description: str
    asset_type: str | None = None
    transaction_type: str
    amount_range: str
    transaction_date: str
    disclosure_date: str
    link: str | None = None


class FlaggedTicker(BaseModel):
    ticker: str
    reasons: list[str]
    score: float
    window_start: str
    window_end: str
    flagged_at: datetime


class SearchResult(BaseModel):
    title: str
    link: str
    snippet: str


class StockReport(BaseModel):
    ticker: str
    summary: str
    likely_drivers: list[str]
    sources: list[str]
    confidence: Literal["low", "medium", "high"]
    generated_at: datetime


class DailySummary(BaseModel):
    date: str
    summary: str
    highlighted_tickers: list[str]
    generated_at: datetime
