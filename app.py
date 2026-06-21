import asyncio
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from politicianstockai import storage
from politicianstockai.pipeline import run_pipeline
from politicianstockai.research import generate_report

st.set_page_config(page_title="PoliticianStockAI", layout="wide")

storage.init_db()

st.title("PoliticianStockAI")
st.caption(
    "Scans recent congressional stock trading disclosures, flags unusual activity, "
    "and uses AI research to explain what's likely driving it."
)

today = datetime.now(timezone.utc).date().isoformat()
todays_summary = storage.get_summary_for_date(today)

st.subheader("Today's Summary")
if todays_summary is None:
    st.info("No summary yet for today — click 'Refresh / Scan' below.")
else:
    with st.container(border=True):
        st.write(todays_summary.summary)
        if todays_summary.highlighted_tickers:
            st.caption("Worth investigating first:")
            cols = st.columns(len(todays_summary.highlighted_tickers))
            for col, ticker in zip(cols, todays_summary.highlighted_tickers):
                with col:
                    if st.button(ticker, key=f"jump_{ticker}"):
                        st.session_state["selected_ticker"] = ticker
                        st.rerun()
        st.caption(f"Generated at {todays_summary.generated_at}")

with st.expander("Previous summaries"):
    history = storage.get_summary_history()
    past_summaries = [s for s in history if s.date != today]
    if not past_summaries:
        st.caption("No previous summaries yet.")
    else:
        for s in past_summaries:
            st.markdown(f"**{s.date}**")
            st.write(s.summary)

col1, col2 = st.columns([1, 5])
with col1:
    if st.button("Refresh / Scan", type="primary"):
        with st.spinner("Fetching trades, detecting patterns, generating reports..."):
            try:
                asyncio.run(run_pipeline())
                st.success("Refresh complete.")
            except Exception as e:
                st.error(f"Refresh failed: {e}")

flagged = storage.get_latest_flags()

if not flagged:
    st.info("No flagged tickers yet. Click 'Refresh / Scan' to fetch data.")
else:
    flagged_df = pd.DataFrame(
        [
            {
                "Ticker": f.ticker,
                "Score": f.score,
                "Reasons": "; ".join(f.reasons),
                "Window": f"{f.window_start} to {f.window_end}",
                "Flagged At": f.flagged_at,
            }
            for f in flagged
        ]
    ).sort_values("Score", ascending=False)

    st.subheader("Flagged Tickers")
    st.dataframe(flagged_df, use_container_width=True, hide_index=True)
    st.bar_chart(flagged_df.set_index("Ticker")["Score"])

    st.subheader("Ticker Detail")
    ticker_options = flagged_df["Ticker"].tolist()
    preselected = st.session_state.pop("selected_ticker", None)
    default_index = ticker_options.index(preselected) if preselected in ticker_options else 0
    ticker = st.selectbox("Select a ticker", ticker_options, index=default_index)

    if ticker:
        if st.button("Force re-research", help="Bypass the 24h cache and regenerate this report now"):
            selected_flag = next(f for f in flagged if f.ticker == ticker)
            with st.spinner(f"Re-researching {ticker}..."):
                try:
                    new_report = asyncio.run(generate_report(selected_flag))
                    storage.insert_report(new_report)
                    st.success("Report regenerated.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Re-research failed: {e}")

        history = storage.get_report_history(ticker)
        if not history:
            st.warning("No AI report generated yet for this ticker.")
        else:
            report = history[0]
            confidence_color = {"low": "🔴", "medium": "🟡", "high": "🟢"}.get(report.confidence, "")
            st.markdown(f"**Confidence:** {confidence_color} {report.confidence}")
            st.write(report.summary)
            st.markdown("**Likely drivers:**")
            for driver in report.likely_drivers:
                st.markdown(f"- {driver}")
            st.markdown("**Sources:**")
            for source in report.sources:
                st.markdown(f"- [{source}]({source})")
            st.caption(f"Generated at {report.generated_at}")

        trades = [t for t in storage.get_recent_trades(window_days=90) if t.symbol == ticker]
        if trades:
            st.markdown("**Underlying trades:**")
            trades_df = pd.DataFrame([t.model_dump() for t in trades])
            st.dataframe(trades_df, use_container_width=True, hide_index=True)
