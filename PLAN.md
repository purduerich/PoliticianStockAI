# Politician Stock Trade Analyzer — Architecture

## Summary

An AI agent that scans public congressional stock trading disclosures, flags notable
trading patterns (high volume, cross-politician overlap, cross-chamber overlap, buy/sell
skew, unusual volume spikes), and uses web research (OpenAI + Serper) to explain what's
likely driving the activity for flagged tickers. Results are surfaced in a Streamlit
dashboard, refreshed on demand via a "Refresh / Scan" button.

Note: each trade has a transaction date (when it occurred) and a disclosure date (when
it was filed, up to 45 days later by law) — the app and its UI always frame results as
"this scan" rather than implying the underlying trades happened "today."

## Current Architecture

- **Data source**: [Financial Modeling Prep](https://site.financialmodelingprep.com/)
  `senate-latest` / `house-latest` REST endpoints — `politicianstockai/fmp_client.py`.
  Free tier only supports `page=0` (no pagination), returning the ~100 most recent
  disclosures per chamber per call. History accumulates across repeated refreshes via
  the SQLite/Turso cache rather than from any single call.

  *(Originally planned to use the [`mcp-capitol-trades`](https://github.com/anguslin/mcp-capitol-trades)
  MCP server scraping capitoltrades.com directly — abandoned because capitoltrades.com
  blocks scraping at the infrastructure level via a Vercel bot challenge, confirmed by a
  429 response even on a plain `curl` to the homepage.)*

- **Pattern detection**: pure pandas heuristics, no LLM — `politicianstockai/patterns.py`.
  Five rules (`flag_high_volume`, `flag_cross_politician_overlap`, `flag_buy_sell_skew`,
  `flag_cross_chamber_overlap`, `flag_volume_delta`), each contributing one reason string
  to a ticker's `FlaggedTicker.reasons`; the displayed "Score" is just the count of rules
  that fired (not a weighted/magnitude measure).

- **Storage**: `politicianstockai/storage.py`. Production uses a remote
  [Turso](https://turso.tech) (libSQL) database so data survives Streamlit Cloud
  redeploys/restarts; local `sqlite3` is the fallback when no `TURSO_DATABASE_URL` is
  configured (used by the test suite). Three tables: `trades` (deduped via a natural-key
  unique constraint), `flagged_tickers` (append-only history; UI shows latest per
  ticker), `reports` (append-only history; 24h freshness cache avoids redundant
  OpenAI/Serper spend).

- **Research agent**: one PydanticAI `Agent` (OpenAI model + a Serper-backed
  `search_web` tool) — `politicianstockai/research.py`. Produces a structured
  `StockReport` (summary, likely drivers, sources, confidence). Confidence is
  explicitly calibrated in the agent instructions: "high" requires a specific, dated
  catalyst within the trade window; "medium" is the default for circumstantial/generic
  evidence; "low" is for no relevant findings. Blue-chip tickers will still skew "high"
  more often since they tend to have frequent, genuine news catalysts — that's evidence,
  not miscalibration.

- **Orchestration**: `politicianstockai/pipeline.py` — fetch (FMP) → cache (storage) →
  flag (patterns) → research only newly-flagged or stale tickers → persist.

- **UI**: `app.py` (Streamlit). "Refresh / Scan" button runs the pipeline; flagged-ticker
  table + bar chart; per-ticker detail view with the cached report, underlying trades,
  and a "Force re-research" button that bypasses the 24h freshness cache for that ticker.

## Hosting & Deployment

- **Streamlit Community Cloud** (free), connected to the GitHub repo
  (`github.com/purduerich/PoliticianStockAI`). Deploys automatically via a GitHub
  webhook on every push to `main` — no separate deploy pipeline.
  *(Originally planned for Azure App Service/Container Apps with a Dockerfile bundling
  Node.js, specifically to support the MCP server's `npx` subprocess. Once the data
  source moved to a plain REST API, that requirement — and the Azure/Docker setup — no
  longer applied.)*
- Secrets (configured in the Streamlit app's dashboard, and locally via `.env`):
  `OPENAI_API_KEY`, `SERPER_API_KEY`, `FMP_API_KEY`, `TURSO_DATABASE_URL`,
  `TURSO_AUTH_TOKEN`.
- `runtime.txt` pins Python 3.12 — required because `libsql` (the Turso client) only
  ships prebuilt wheels for standard CPython versions, not newer/unusual ones.
- `.github/workflows/ci.yml` runs `ruff check` + `pytest` on PRs/pushes (lint + unit
  tests only — `patterns.py`/`storage.py` are deterministic; live MCP/OpenAI/Serper/FMP
  calls are excluded from CI to avoid cost and flakiness).

## Known Limitations

- FMP's free tier has no pagination beyond the latest ~100 disclosures per chamber per
  call — if more than that many new disclosures are filed between refreshes, the gap is
  silently missed (never backfilled), not overwritten.
- Confidence calibration is evidence-based: it reflects whether news genuinely explains
  the trade pattern, not a guarantee of the politician's actual motive — there's no way
  to know that from public data.

## Possible Next Steps (discussed, not yet built)

- A second Streamlit app tracking a `dev` branch, pointed at a separate Turso database
  (e.g. `politicianstockai-dev`), for testing changes before promoting to `main`/prod.

---

## Original Brief

> This is a brand new project. Nothing is created yet. I want to build an AI Agent that
> scans public congressional trades (such as www.capitoltrades.com) and do analysis on
> them. The overall goal is as follows.
> Have the agent check the current trends of trades. I want the agent to check in its
> own common stock patterns. For example: high stock purchases/sells, stocks being
> purchased/sold across numerous politicans, unusual stock activity and anything else.
> I also want the agent to use Google research to do an analysis of the stock and the
> company to make a report of what is likely driving that behavior.
> I'd like to consider the MCP server listed below to interact with the data.
> https://github.com/anguslin/mcp-capitol-trades
> This is mostly for academic purposes. I want the tech stack to be as follows, but its
> negotiable:
> - I want Python to be the primary language
> - I want to use the PydanticAI agent framework
> - Front end shoud use streamlit
> - SQLite can be used for storage if needed
> - Serper should be used for Google searches, i have an API key
> - Github for code repo and CI/CD.
> - I want to host this app somewhere. It can be on Streamlit.io or anywhere else
> - I have an Azure subscription. I'd like to use that if we need to deploy resources
> Keep costs in mind when making decisions.
> Give me a plan on how to move forward and I'll verify it
