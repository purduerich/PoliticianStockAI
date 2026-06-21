import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import libsql

from politicianstockai.config import get_settings
from politicianstockai.models import DailySummary, FlaggedTicker, StockReport, Trade

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chamber TEXT NOT NULL,
    symbol TEXT NOT NULL,
    politician TEXT NOT NULL,
    owner TEXT,
    asset_description TEXT NOT NULL,
    asset_type TEXT,
    transaction_type TEXT NOT NULL,
    amount_range TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    disclosure_date TEXT NOT NULL,
    link TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(symbol, politician, transaction_date, transaction_type, amount_range)
);

CREATE TABLE IF NOT EXISTS flagged_tickers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    reasons TEXT NOT NULL,
    score REAL NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    flagged_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_flagged_ticker_time ON flagged_tickers(ticker, flagged_at);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    summary TEXT NOT NULL,
    likely_drivers TEXT NOT NULL,
    sources TEXT NOT NULL,
    confidence TEXT NOT NULL,
    generated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_report_ticker_time ON reports(ticker, generated_at);

CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    highlighted_tickers TEXT NOT NULL,
    sources TEXT NOT NULL DEFAULT '[]',
    generated_at TEXT NOT NULL
);
"""

MIGRATIONS = [
    "ALTER TABLE daily_summaries ADD COLUMN sources TEXT NOT NULL DEFAULT '[]'",
]


@contextmanager
def _connect(db_path: str | None = None):
    settings = get_settings()
    if db_path is None and settings.turso_database_url:
        conn = libsql.connect(database=settings.turso_database_url, auth_token=settings.turso_auth_token)
    else:
        path = db_path or settings.db_path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _as_dicts(cursor) -> list[dict]:
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def init_db(db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        for migration in MIGRATIONS:
            try:
                conn.execute(migration)
            except Exception:
                pass  # column already exists


def insert_trades(trades: list[Trade], db_path: str | None = None) -> int:
    if not trades:
        return 0
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = [
        (
            t.chamber,
            t.symbol,
            t.politician,
            t.owner,
            t.asset_description,
            t.asset_type,
            t.transaction_type,
            t.amount_range,
            t.transaction_date,
            t.disclosure_date,
            t.link,
            fetched_at,
        )
        for t in trades
    ]
    with _connect(db_path) as conn:
        cur = conn.executemany(
            """INSERT OR IGNORE INTO trades
               (chamber, symbol, politician, owner, asset_description, asset_type,
                transaction_type, amount_range, transaction_date, disclosure_date, link, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        return cur.rowcount


def get_recent_trades(window_days: int = 60, db_path: str | None = None) -> list[Trade]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).date().isoformat()
    with _connect(db_path) as conn:
        rows = _as_dicts(
            conn.execute(
                "SELECT * FROM trades WHERE transaction_date >= ? ORDER BY transaction_date DESC",
                (cutoff,),
            )
        )
    return [
        Trade(
            chamber=r["chamber"],
            symbol=r["symbol"],
            politician=r["politician"],
            owner=r["owner"],
            asset_description=r["asset_description"],
            asset_type=r["asset_type"],
            transaction_type=r["transaction_type"],
            amount_range=r["amount_range"],
            transaction_date=r["transaction_date"],
            disclosure_date=r["disclosure_date"],
            link=r["link"],
        )
        for r in rows
    ]


def insert_flagged_tickers(flagged: list[FlaggedTicker], db_path: str | None = None) -> None:
    if not flagged:
        return
    rows = [
        (f.ticker, json.dumps(f.reasons), f.score, f.window_start, f.window_end, f.flagged_at.isoformat())
        for f in flagged
    ]
    with _connect(db_path) as conn:
        conn.executemany(
            """INSERT INTO flagged_tickers (ticker, reasons, score, window_start, window_end, flagged_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )


def get_latest_flags(db_path: str | None = None) -> list[FlaggedTicker]:
    with _connect(db_path) as conn:
        rows = _as_dicts(
            conn.execute(
                """SELECT t1.* FROM flagged_tickers t1
                   WHERE t1.flagged_at = (
                       SELECT MAX(t2.flagged_at) FROM flagged_tickers t2 WHERE t2.ticker = t1.ticker
                   )
                   ORDER BY t1.score DESC"""
            )
        )
    return [
        FlaggedTicker(
            ticker=r["ticker"],
            reasons=json.loads(r["reasons"]),
            score=r["score"],
            window_start=r["window_start"],
            window_end=r["window_end"],
            flagged_at=r["flagged_at"],
        )
        for r in rows
    ]


def get_cached_report(ticker: str, max_age_hours: int = 24, db_path: str | None = None) -> StockReport | None:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    with _connect(db_path) as conn:
        rows = _as_dicts(
            conn.execute(
                """SELECT * FROM reports WHERE ticker = ? AND generated_at >= ?
                   ORDER BY generated_at DESC LIMIT 1""",
                (ticker, cutoff),
            )
        )
    if not rows:
        return None
    row = rows[0]
    return StockReport(
        ticker=row["ticker"],
        summary=row["summary"],
        likely_drivers=json.loads(row["likely_drivers"]),
        sources=json.loads(row["sources"]),
        confidence=row["confidence"],
        generated_at=row["generated_at"],
    )


def insert_report(report: StockReport, db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT INTO reports (ticker, summary, likely_drivers, sources, confidence, generated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                report.ticker,
                report.summary,
                json.dumps(report.likely_drivers),
                json.dumps(report.sources),
                report.confidence,
                report.generated_at.isoformat(),
            ),
        )


def get_report_history(ticker: str, db_path: str | None = None) -> list[StockReport]:
    with _connect(db_path) as conn:
        rows = _as_dicts(
            conn.execute(
                "SELECT * FROM reports WHERE ticker = ? ORDER BY generated_at DESC",
                (ticker,),
            )
        )
    return [
        StockReport(
            ticker=r["ticker"],
            summary=r["summary"],
            likely_drivers=json.loads(r["likely_drivers"]),
            sources=json.loads(r["sources"]),
            confidence=r["confidence"],
            generated_at=r["generated_at"],
        )
        for r in rows
    ]


def get_summary_for_date(date: str, db_path: str | None = None) -> DailySummary | None:
    with _connect(db_path) as conn:
        rows = _as_dicts(conn.execute("SELECT * FROM daily_summaries WHERE date = ?", (date,)))
    if not rows:
        return None
    row = rows[0]
    return DailySummary(
        date=row["date"],
        summary=row["summary"],
        highlighted_tickers=json.loads(row["highlighted_tickers"]),
        sources=json.loads(row.get("sources") or "[]"),
        generated_at=row["generated_at"],
    )


def insert_daily_summary(summary: DailySummary, db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO daily_summaries (date, summary, highlighted_tickers, sources, generated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                summary.date,
                summary.summary,
                json.dumps(summary.highlighted_tickers),
                json.dumps(summary.sources),
                summary.generated_at.isoformat(),
            ),
        )


def get_summary_history(limit: int = 14, db_path: str | None = None) -> list[DailySummary]:
    with _connect(db_path) as conn:
        rows = _as_dicts(
            conn.execute(
                "SELECT * FROM daily_summaries ORDER BY date DESC LIMIT ?",
                (limit,),
            )
        )
    return [
        DailySummary(
            date=r["date"],
            summary=r["summary"],
            highlighted_tickers=json.loads(r["highlighted_tickers"]),
            sources=json.loads(r.get("sources") or "[]"),
            generated_at=r["generated_at"],
        )
        for r in rows
    ]
