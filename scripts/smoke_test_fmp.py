import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from politicianstockai.fmp_client import fetch_latest_trades


async def main() -> None:
    trades = await fetch_latest_trades()
    print(f"Fetched {len(trades)} trades")
    for t in trades[:5]:
        print(t)


if __name__ == "__main__":
    asyncio.run(main())
