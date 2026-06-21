from datetime import date, timedelta

from politicianstockai.models import Trade
from politicianstockai.patterns import run_all_flags


def make_trade(symbol, politician, chamber, txn_type, days_ago, owner=None):
    txn_date = (date.today() - timedelta(days=days_ago)).isoformat()
    return Trade(
        chamber=chamber,
        symbol=symbol,
        politician=politician,
        owner=owner,
        asset_description=f"{symbol} Corp",
        asset_type="Stock",
        transaction_type=txn_type,
        amount_range="$1,001 - $15,000",
        transaction_date=txn_date,
        disclosure_date=txn_date,
        link=None,
    )


def test_flags_high_volume_and_cross_politician_overlap():
    trades = [
        make_trade("NVDA", f"Politician {i}", "senate", "Purchase", days_ago=1)
        for i in range(6)
    ]
    flagged = run_all_flags(trades)
    assert len(flagged) == 1
    flag = flagged[0]
    assert flag.ticker == "NVDA"
    assert any("trades in window" in r for r in flag.reasons)
    assert any("distinct politicians" in r for r in flag.reasons)


def test_flags_cross_chamber_overlap():
    trades = [
        make_trade("AAPL", "Senator A", "senate", "Purchase", days_ago=1),
        make_trade("AAPL", "Rep B", "house", "Purchase", days_ago=1),
    ]
    flagged = run_all_flags(trades)
    assert len(flagged) == 1
    assert "traded in both House and Senate" in flagged[0].reasons


def test_flags_buy_sell_skew():
    trades = [make_trade("TSLA", f"Pol {i}", "senate", "Purchase", days_ago=1) for i in range(4)]
    trades.append(make_trade("TSLA", "Pol X", "senate", "Sale", days_ago=1))
    flagged = run_all_flags(trades)
    assert len(flagged) == 1
    assert any("buy/sell ratio" in r for r in flagged[0].reasons)


def test_no_flags_for_quiet_ticker():
    trades = [make_trade("MSFT", "Pol 1", "senate", "Purchase", days_ago=1)]
    flagged = run_all_flags(trades)
    assert flagged == []


def test_empty_input_returns_empty():
    assert run_all_flags([]) == []
