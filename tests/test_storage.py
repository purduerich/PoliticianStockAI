from datetime import datetime, timedelta, timezone

import pytest

from politicianstockai import storage
from politicianstockai.models import DailySummary, FlaggedTicker, StockReport, Trade


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    storage.init_db(path)
    return path


def make_trade(symbol="NVDA", politician="Jane Doe", txn_date="2026-06-01"):
    return Trade(
        chamber="senate",
        symbol=symbol,
        politician=politician,
        owner=None,
        asset_description=f"{symbol} Corp",
        asset_type="Stock",
        transaction_type="Purchase",
        amount_range="$1,001 - $15,000",
        transaction_date=txn_date,
        disclosure_date=txn_date,
        link=None,
    )


def test_insert_and_get_recent_trades(db_path):
    storage.insert_trades([make_trade()], db_path)
    trades = storage.get_recent_trades(window_days=365, db_path=db_path)
    assert len(trades) == 1
    assert trades[0].symbol == "NVDA"


def test_insert_trades_dedupes_on_natural_key(db_path):
    trade = make_trade()
    inserted_first = storage.insert_trades([trade], db_path)
    inserted_second = storage.insert_trades([trade], db_path)
    assert inserted_first == 1
    assert inserted_second == 0
    assert len(storage.get_recent_trades(window_days=365, db_path=db_path)) == 1


def test_flagged_tickers_round_trip_and_latest_only(db_path):
    older = FlaggedTicker(
        ticker="NVDA", reasons=["old reason"], score=1.0,
        window_start="2026-05-01", window_end="2026-05-30",
        flagged_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    newer = FlaggedTicker(
        ticker="NVDA", reasons=["new reason"], score=2.0,
        window_start="2026-06-01", window_end="2026-06-21",
        flagged_at=datetime.now(timezone.utc),
    )
    storage.insert_flagged_tickers([older, newer], db_path)
    latest = storage.get_latest_flags(db_path)
    assert len(latest) == 1
    assert latest[0].reasons == ["new reason"]


def test_report_freshness_cache(db_path):
    assert storage.get_cached_report("NVDA", db_path=db_path) is None

    report = StockReport(
        ticker="NVDA", summary="test summary", likely_drivers=["earnings"],
        sources=["https://example.com"], confidence="medium",
        generated_at=datetime.now(timezone.utc),
    )
    storage.insert_report(report, db_path)

    fresh = storage.get_cached_report("NVDA", max_age_hours=24, db_path=db_path)
    assert fresh is not None
    assert fresh.summary == "test summary"

    stale = storage.get_cached_report("NVDA", max_age_hours=0, db_path=db_path)
    assert stale is None


def test_report_history_ordered_desc(db_path):
    old_report = StockReport(
        ticker="NVDA", summary="old", likely_drivers=[], sources=[], confidence="low",
        generated_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    new_report = StockReport(
        ticker="NVDA", summary="new", likely_drivers=[], sources=[], confidence="high",
        generated_at=datetime.now(timezone.utc),
    )
    storage.insert_report(old_report, db_path)
    storage.insert_report(new_report, db_path)

    history = storage.get_report_history("NVDA", db_path)
    assert [r.summary for r in history] == ["new", "old"]


def test_daily_summary_round_trip(db_path):
    assert storage.get_summary_for_date("2026-06-21", db_path) is None

    summary = DailySummary(
        date="2026-06-21", summary="Quiet day overall.", highlighted_tickers=["NVDA", "AAPL"],
        sources=["https://example.com/a"], generated_at=datetime.now(timezone.utc),
    )
    storage.insert_daily_summary(summary, db_path)

    fetched = storage.get_summary_for_date("2026-06-21", db_path)
    assert fetched is not None
    assert fetched.summary == "Quiet day overall."
    assert fetched.highlighted_tickers == ["NVDA", "AAPL"]
    assert fetched.sources == ["https://example.com/a"]


def test_daily_summary_upserts_on_date(db_path):
    first = DailySummary(
        date="2026-06-21", summary="First version.", highlighted_tickers=[],
        sources=[], generated_at=datetime.now(timezone.utc),
    )
    second = DailySummary(
        date="2026-06-21", summary="Updated version.", highlighted_tickers=["TSLA"],
        sources=["https://example.com/b"], generated_at=datetime.now(timezone.utc),
    )
    storage.insert_daily_summary(first, db_path)
    storage.insert_daily_summary(second, db_path)

    fetched = storage.get_summary_for_date("2026-06-21", db_path)
    assert fetched.summary == "Updated version."
    assert fetched.sources == ["https://example.com/b"]
    assert len(storage.get_summary_history(db_path=db_path)) == 1


def test_daily_summary_history_ordered_desc(db_path):
    older = DailySummary(
        date="2026-06-19", summary="day 1", highlighted_tickers=[],
        sources=[], generated_at=datetime.now(timezone.utc),
    )
    newer = DailySummary(
        date="2026-06-21", summary="day 3", highlighted_tickers=[],
        sources=[], generated_at=datetime.now(timezone.utc),
    )
    storage.insert_daily_summary(older, db_path)
    storage.insert_daily_summary(newer, db_path)

    history = storage.get_summary_history(db_path=db_path)
    assert [s.date for s in history] == ["2026-06-21", "2026-06-19"]


def test_daily_summary_migration_backfills_sources_column(db_path):
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE daily_summaries")
    conn.execute(
        """CREATE TABLE daily_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            summary TEXT NOT NULL,
            highlighted_tickers TEXT NOT NULL,
            generated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        "INSERT INTO daily_summaries (date, summary, highlighted_tickers, generated_at) VALUES (?, ?, ?, ?)",
        ("2026-06-20", "old-schema row", "[]", datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

    storage.init_db(db_path)

    fetched = storage.get_summary_for_date("2026-06-20", db_path)
    assert fetched is not None
    assert fetched.summary == "old-schema row"
    assert fetched.sources == []
