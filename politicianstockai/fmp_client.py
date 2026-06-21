import asyncio

import httpx

from politicianstockai.config import get_settings
from politicianstockai.models import Trade

BASE_URL = "https://financialmodelingprep.com/stable"


def _to_trade(raw: dict, chamber: str) -> Trade:
    return Trade(
        chamber=chamber,
        symbol=raw["symbol"],
        politician=f"{raw['firstName']} {raw['lastName']}",
        owner=raw.get("owner") or None,
        asset_description=raw["assetDescription"],
        asset_type=raw.get("assetType"),
        transaction_type=raw["type"],
        amount_range=raw["amount"],
        transaction_date=raw["transactionDate"],
        disclosure_date=raw["disclosureDate"],
        link=raw.get("link"),
    )


async def fetch_latest_trades() -> list[Trade]:
    """Fetch the most recent Senate + House disclosures.

    Free tier only supports page=0 (~100 most recent rows per chamber), so
    breadth of history comes from repeated refreshes accumulating into storage.
    """
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        senate_resp, house_resp = await asyncio.gather(
            client.get(f"{BASE_URL}/senate-latest", params={"apikey": settings.fmp_api_key}),
            client.get(f"{BASE_URL}/house-latest", params={"apikey": settings.fmp_api_key}),
        )

    senate_resp.raise_for_status()
    house_resp.raise_for_status()

    trades = [_to_trade(r, "senate") for r in senate_resp.json()]
    trades += [_to_trade(r, "house") for r in house_resp.json()]
    return trades
