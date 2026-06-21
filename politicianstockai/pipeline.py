import logging

from politicianstockai import storage
from politicianstockai.fmp_client import fetch_latest_trades
from politicianstockai.models import FlaggedTicker
from politicianstockai.patterns import run_all_flags
from politicianstockai.research import generate_report

logger = logging.getLogger(__name__)

REPORT_FRESHNESS_HOURS = 24


async def run_pipeline() -> list[FlaggedTicker]:
    storage.init_db()

    trades = await fetch_latest_trades()
    inserted = storage.insert_trades(trades)
    logger.info("fetched %d trades, %d new", len(trades), inserted)

    history = storage.get_recent_trades(window_days=90)
    flagged = run_all_flags(history)
    storage.insert_flagged_tickers(flagged)
    logger.info("flagged %d tickers", len(flagged))

    for flag in flagged:
        cached = storage.get_cached_report(flag.ticker, max_age_hours=REPORT_FRESHNESS_HOURS)
        if cached is not None:
            logger.info("skipping %s, fresh report cached", flag.ticker)
            continue
        report = await generate_report(flag)
        storage.insert_report(report)
        logger.info("generated report for %s", flag.ticker)

    return storage.get_latest_flags()
