# Politician Stock Trade Analyzer

An AI agent that scans public congressional stock trading disclosures (via the
[Financial Modeling Prep](https://site.financialmodelingprep.com/) Senate/House disclosure
APIs), flags notable trading patterns (high volume, cross-politician overlap, cross-chamber
overlap, buy/sell skew, unusual volume spikes), and uses web research (Serper + OpenAI) to
explain what's likely driving the activity. Results are shown in a Streamlit dashboard.

**Note on dates**: each trade has a *transaction date* (when it actually happened) and a
*disclosure date* (when it was publicly filed). By law, members of Congress can file up to
45 days after a trade, so a scan run on any given day may surface trades from weeks
earlier — the app never assumes the underlying trades happened "today," only that they were
recently disclosed.

## Prerequisites

- Python 3.12 (pinned via `runtime.txt`; required for `libsql` prebuilt wheels)
- An OpenAI API key
- A [Serper](https://serper.dev) API key
- A [Financial Modeling Prep](https://site.financialmodelingprep.com/) API key (free tier works)
- A [Turso](https://turso.tech) database (free tier works) for persistent storage

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
cp .env.example .env   # then fill in OPENAI_API_KEY, SERPER_API_KEY, FMP_API_KEY,
                        # TURSO_DATABASE_URL, TURSO_AUTH_TOKEN
```

## Smoke test the data source

```bash
python scripts/smoke_test_fmp.py
```

Confirms the FMP API key works and returns real Senate/House trade disclosures. Note: the
free tier only supports the "latest" endpoints (most recent ~100 disclosures per chamber,
no pagination) — the app's SQLite cache accumulates history across repeated refreshes.

## Run the dashboard

```bash
streamlit run app.py
```

Click "Refresh / Scan" to fetch trades, run pattern detection, and generate AI research
reports for newly flagged tickers (reports are cached for 24h to avoid redundant OpenAI/Serper
spend).

## Run tests / lint

```bash
pytest tests/
ruff check .
```

## Deployment

Hosted on [Streamlit Community Cloud](https://streamlit.io/cloud) (free): connect this
GitHub repo, point at `app.py`, and set `OPENAI_API_KEY`, `SERPER_API_KEY`, `FMP_API_KEY`,
`TURSO_DATABASE_URL`, and `TURSO_AUTH_TOKEN` under the app's Secrets (see
`.streamlit/secrets.toml.example`). No Docker/Node.js needed — the data source is a plain
REST API. Deploys automatically via a GitHub webhook on every push to `main`.

Storage is a remote Turso (libSQL) database, so trades, flags, and AI reports persist
across redeploys and restarts. Local `sqlite3` is used as a fallback when no
`TURSO_DATABASE_URL` is set (e.g. for the test suite).
