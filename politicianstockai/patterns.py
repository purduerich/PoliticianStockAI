from datetime import datetime, timezone

import pandas as pd

from politicianstockai.models import FlaggedTicker, Trade

MIN_TRADE_COUNT = 5
MIN_DISTINCT_POLITICIANS = 3
MIN_BUY_SELL_RATIO = 3.0
SHORT_WINDOW_DAYS = 7
LONG_WINDOW_DAYS = 30
MIN_VOLUME_MULTIPLE = 2.0


def trades_to_dataframe(trades: list[Trade]) -> pd.DataFrame:
    df = pd.DataFrame([t.model_dump() for t in trades])
    if df.empty:
        return df
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    return df


def flag_high_volume(df: pd.DataFrame) -> dict[str, str]:
    counts = df.groupby("symbol").size()
    flagged = counts[counts >= MIN_TRADE_COUNT]
    return {
        ticker: f"{count} trades in window (>= {MIN_TRADE_COUNT})"
        for ticker, count in flagged.items()
    }


def flag_cross_politician_overlap(df: pd.DataFrame) -> dict[str, str]:
    distinct = df.groupby("symbol")["politician"].nunique()
    flagged = distinct[distinct >= MIN_DISTINCT_POLITICIANS]
    return {
        ticker: f"traded by {count} distinct politicians (>= {MIN_DISTINCT_POLITICIANS})"
        for ticker, count in flagged.items()
    }


def flag_buy_sell_skew(df: pd.DataFrame) -> dict[str, str]:
    reasons: dict[str, str] = {}
    counts = df.groupby(["symbol", "transaction_type"]).size().unstack(fill_value=0)
    buys = counts.get("Purchase", pd.Series(dtype=int))
    sells = counts.get("Sale", pd.Series(dtype=int))
    for ticker in counts.index:
        b, s = buys.get(ticker, 0), sells.get(ticker, 0)
        if s > 0 and b / s >= MIN_BUY_SELL_RATIO:
            reasons[ticker] = f"buy/sell ratio {b}:{s} (>= {MIN_BUY_SELL_RATIO}x)"
        elif b > 0 and s / b >= MIN_BUY_SELL_RATIO:
            reasons[ticker] = f"sell/buy ratio {s}:{b} (>= {MIN_BUY_SELL_RATIO}x)"
    return reasons


def flag_cross_chamber_overlap(df: pd.DataFrame) -> dict[str, str]:
    chambers = df.groupby("symbol")["chamber"].nunique()
    flagged = chambers[chambers >= 2]
    return {ticker: "traded in both House and Senate" for ticker in flagged.index}


def flag_volume_delta(df: pd.DataFrame) -> dict[str, str]:
    reasons: dict[str, str] = {}
    now = df["transaction_date"].max()
    if pd.isna(now):
        return reasons
    short_cutoff = now - pd.Timedelta(days=SHORT_WINDOW_DAYS)
    long_cutoff = now - pd.Timedelta(days=LONG_WINDOW_DAYS)

    short_counts = df[df["transaction_date"] >= short_cutoff].groupby("symbol").size()
    long_df = df[(df["transaction_date"] >= long_cutoff) & (df["transaction_date"] < short_cutoff)]
    long_counts = long_df.groupby("symbol").size()
    long_daily_rate = long_counts / max(LONG_WINDOW_DAYS - SHORT_WINDOW_DAYS, 1)
    short_daily_rate = short_counts / SHORT_WINDOW_DAYS

    for ticker, short_rate in short_daily_rate.items():
        baseline = long_daily_rate.get(ticker, 0)
        if baseline > 0 and short_rate / baseline >= MIN_VOLUME_MULTIPLE:
            reasons[ticker] = (
                f"recent trade rate {short_rate:.2f}/day vs baseline {baseline:.2f}/day "
                f"(>= {MIN_VOLUME_MULTIPLE}x)"
            )
    return reasons


def run_all_flags(trades: list[Trade]) -> list[FlaggedTicker]:
    df = trades_to_dataframe(trades)
    if df.empty:
        return []

    rule_results = [
        flag_high_volume(df),
        flag_cross_politician_overlap(df),
        flag_buy_sell_skew(df),
        flag_cross_chamber_overlap(df),
        flag_volume_delta(df),
    ]

    merged: dict[str, list[str]] = {}
    for result in rule_results:
        for ticker, reason in result.items():
            merged.setdefault(ticker, []).append(reason)

    window_start = df["transaction_date"].min().date().isoformat()
    window_end = df["transaction_date"].max().date().isoformat()
    flagged_at = datetime.now(timezone.utc)

    return [
        FlaggedTicker(
            ticker=ticker,
            reasons=reasons,
            score=float(len(reasons)),
            window_start=window_start,
            window_end=window_end,
            flagged_at=flagged_at,
        )
        for ticker, reasons in merged.items()
    ]
