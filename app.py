#!/usr/bin/env python3
"""
Token Benchmark Dashboard - Streamlit App

Run with: streamlit run app.py
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from src.storage.json_store import BenchmarkStore

# Page config
st.set_page_config(
    page_title="Token Benchmark Tool",
    page_icon="📊",
    layout="wide"
)

# Load data - clear cache on reload
@st.cache_data(ttl=60)
def load_benchmarks():
    store = BenchmarkStore()
    return {symbol: store.load(symbol) for symbol in store.list_all()}

benchmarks = load_benchmarks()

# Sidebar - Token selection
st.sidebar.title("Token Benchmark Tool")
st.sidebar.markdown("---")

if not benchmarks:
    st.error("No tokens in database. Add tokens first.")
    st.stop()

selected_symbol = st.sidebar.selectbox(
    "Select Token",
    options=list(benchmarks.keys()),
    format_func=lambda x: f"{x} - {benchmarks[x].name}"
)

token = benchmarks[selected_symbol]

# Helper function to create clickable links
def make_link(text, url):
    return f"[{text}]({url})"

# URLs for sources
COINGECKO_URL = f"https://www.coingecko.com/en/coins/{token.coingecko_id}"
CRYPTORANK_URL = "https://cryptorank.io"
MESSARI_URL = "https://messari.io"

# ============================================================================
# SECTION 1: TOKEN PRESENTATION
# ============================================================================

st.header("1. TOKEN PRESENTATION")

# 1.1 Header with description
st.subheader(f"{token.name} ({token.symbol})")
if token.description:
    st.markdown(f"*{token.description}*")

st.markdown("---")

# 1.2 General Information & Supply in two columns
col1, col2 = st.columns(2)

with col1:
    st.markdown("### General Information")
    general_info = pd.DataFrame({
        "Field": ["Name", "Symbol", "Blockchain", "Categories"],
        "Value": [
            token.name,
            token.symbol,
            token.blockchain,
            ", ".join(token.categories),
        ]
    })
    st.dataframe(general_info, use_container_width=True, hide_index=True)

    # CoinGecko link
    st.markdown(f"**CoinGecko:** [{token.coingecko_id}]({COINGECKO_URL})")

with col2:
    st.markdown("### Supply Data")
    supply_data = pd.DataFrame({
        "Field": [
            "Total Supply",
            "Max Supply",
            "Circulating at TGE"
        ],
        "Value": [
            f"{token.total_supply:,} {token.symbol}",
            f"{token.max_supply:,} {token.symbol}" if token.max_supply else "Unlimited",
            f"{token.tge_circulating_tokens:,} {token.symbol} ({token.tge_circulating_pct}%)"
        ]
    })
    st.dataframe(supply_data, use_container_width=True, hide_index=True)
    # Sources below table as clickable links
    st.markdown(f"**Sources:** [CoinGecko]({COINGECKO_URL}) · [CryptoRank]({CRYPTORANK_URL})")

st.markdown("---")

# 1.3 Fundraising Section
st.subheader("Fundraising")

if token.fundraising_rounds:
    rounds_data = []
    sources_used = set()
    for r in token.fundraising_rounds:
        rounds_data.append({
            "Round": r.name,
            "Date": r.date,
            "Amount": f"${r.amount:,}",
            "Lead Investors": ", ".join(r.lead_investors) if r.lead_investors else "-"
        })
        if r.source:
            sources_used.add(r.source)
    # Add total row
    rounds_data.append({
        "Round": "TOTAL",
        "Date": "-",
        "Amount": f"${token.total_raised:,}",
        "Lead Investors": "-"
    })

    rounds_df = pd.DataFrame(rounds_data)
    st.dataframe(rounds_df, use_container_width=True, hide_index=True)

    # Sources below table
    sources_links = []
    for src in sources_used:
        if src == "CryptoRank":
            sources_links.append(f"[CryptoRank]({CRYPTORANK_URL})")
        elif src == "Messari":
            sources_links.append(f"[Messari]({MESSARI_URL})")
    if sources_links:
        st.markdown(f"**Source:** {' · '.join(sources_links)}")

    # Notable Investors below
    if token.investors:
        st.markdown(f"**Notable Investors:** {', '.join(token.investors)}")
else:
    st.info("No fundraising data available")

st.markdown("---")

# ============================================================================
# SECTION 2: INITIAL VALUATION
# ============================================================================

st.header("2. INITIAL VALUATION")

# 2.1 Introduction
st.markdown("""
### What is FDV (Fully Diluted Valuation)?

**FDV** represents the total market capitalization if all tokens were in circulation.

**Formula:** `FDV = Total Supply x Token Price`

The **initial listing price** is the first price at which the token trades on secondary markets (CEX/DEX)
after the Token Generation Event (TGE).
""")

st.markdown("---")

# 2.2 Listing Date & Time (General Info First)
st.subheader("Listing Information")

col_date1, col_date2 = st.columns(2)
with col_date1:
    st.metric("Listing Date", token.listing_date)
with col_date2:
    if token.cex_data:
        first_cex = token.cex_data[0]
        time_str = first_cex.first_candle_time.split()[1] if first_cex.first_candle_time else "-"
        st.metric("First Trade Time (UTC)", time_str)

st.markdown("---")

# 2.3 CEX Data Summary with explanations
st.subheader("CEX Data Summary")

st.markdown("""
**Understanding the metrics:**
- **H/L Ratio** (High/Low Ratio): The ratio between the highest and lowest price in the first candle.
  A ratio > 5x indicates a "TGE candle" with extreme volatility typical of initial listing.
- **Flag**: Status indicator for the data quality (SUSPECT = unreliable data, TGE candle = high volatility expected)
""")

if token.cex_data:
    cex_summary = []
    for cex in token.cex_data:
        status = "✅ OK" if cex.first_candle_time else "❌ No data"
        hl_status = "🔴" if cex.hl_ratio > 30 else "🟡" if cex.hl_ratio > 5 else "🟢"
        cex_summary.append({
            "Exchange": cex.exchange.upper(),
            "Status": status,
            "First Candle (UTC)": cex.first_candle_time,
            "OPEN": f"${cex.open:.4f}",
            "HIGH": f"${cex.high:.4f}",
            "LOW": f"${cex.low:.4f}",
            "H/L Ratio": f"{hl_status} {cex.hl_ratio:.1f}x",
            "VWAP 1h": f"${cex.vwap_1h:.4f}" if cex.vwap_1h else "-",
            "Flag": cex.flag
        })

    cex_df = pd.DataFrame(cex_summary)
    st.dataframe(cex_df, use_container_width=True, hide_index=True)
    st.markdown("**Source:** [CCXT](https://github.com/ccxt/ccxt)")
else:
    st.info("No CEX data available")

st.markdown("---")

# 2.4 Price Discovery - First 10 Minutes
st.subheader("Price Discovery - First 10 Minutes")

# Find CEX with first candles data - handle both dict and object access
cex_with_candles = None
for cex in token.cex_data:
    # Check if it's a dict or object
    if hasattr(cex, 'first_candles_1m'):
        if cex.first_candles_1m:
            cex_with_candles = cex
            break
    elif isinstance(cex, dict) and cex.get('first_candles_1m'):
        cex_with_candles = cex
        break

if cex_with_candles:
    candles = cex_with_candles.first_candles_1m if hasattr(cex_with_candles, 'first_candles_1m') else cex_with_candles.get('first_candles_1m', [])
    exchange_name = cex_with_candles.exchange if hasattr(cex_with_candles, 'exchange') else cex_with_candles.get('exchange', 'Unknown')

    st.markdown(f"**{exchange_name.upper()}/USDT** - First 10 minutes after listing:")

    candles_data = []
    for candle in candles:
        candles_data.append({
            "Minute": candle["minute"],
            "Time (UTC)": candle["time"],
            "OPEN": f"${candle['open']:.2f}",
            "HIGH": f"${candle['high']:.2f}",
            "LOW": f"${candle['low']:.2f}",
            "CLOSE": f"${candle['close']:.2f}"
        })

    candles_df = pd.DataFrame(candles_data)
    st.dataframe(candles_df, use_container_width=True, hide_index=True)

    # Key observations
    st.markdown("**Key Observations:**")
    first_candle = candles[0]
    multiplier = first_candle['close'] / first_candle['open'] if first_candle['open'] > 0 else 0
    st.markdown(f"- **{first_candle['time']}:** OPEN ${first_candle['open']:.2f} → CLOSE ${first_candle['close']:.2f} ({multiplier:.0f}x in same minute!)")

    # Find max price
    max_candle = max(candles, key=lambda x: x['high'])
    st.markdown(f"- **Peak:** ${max_candle['high']:.2f} at minute {max_candle['minute']} ({max_candle['time']})")

    # Candlestick Chart
    with st.expander("View Candlestick Chart"):
        chart_data = pd.DataFrame(candles)

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=chart_data['time'],
            open=chart_data['open'],
            high=chart_data['high'],
            low=chart_data['low'],
            close=chart_data['close'],
            name="Price"
        ))
        fig.update_layout(
            title=f"{exchange_name.upper()} - First 10 Minutes",
            xaxis_title="Time (UTC)",
            yaxis_title="Price (USD)",
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No minute-by-minute price discovery data available")

st.markdown("---")

# 2.5 DEX Prices at Stabilization
st.subheader("DEX Prices at Stabilization")

if token.dex_stabilization:
    dex = token.dex_stabilization

    col_dex1, col_dex2 = st.columns(2)
    with col_dex1:
        st.metric("Stabilization Time", dex.stabilization_hour)
    with col_dex2:
        st.metric("Total Swaps", f"{dex.total_swaps:,}")

    dex_prices_data = []
    for dex_name, price in dex.dex_prices.items():
        dex_prices_data.append({
            "DEX": dex_name.replace("_", " ").title(),
            "Price": f"${price:.4f}"
        })

    # Add consensus row
    dex_prices_data.append({
        "DEX": "DEX CONSENSUS",
        "Price": f"${dex.reference_price:.4f} (spread: {dex.spread_pct:.2f}%)"
    })

    dex_df = pd.DataFrame(dex_prices_data)
    st.dataframe(dex_df, use_container_width=True, hide_index=True)
    st.markdown("**Source:** [Flipside Crypto](https://flipsidecrypto.xyz)")
else:
    st.info("No DEX stabilization data available")

st.markdown("---")

# ============================================================================
# SECTION 3: BENCHMARK SUMMARY
# ============================================================================

st.header("3. BENCHMARK SUMMARY")

# 3.1 Sources Comparison Table
st.subheader("Sources Comparison")

sources_data = []

# Add CEX sources
for cex in token.cex_data:
    # OPEN price
    reliability = "🔴 LOW" if cex.hl_ratio > 30 else "🟡 MEDIUM" if cex.hl_ratio > 5 else "🟢 HIGH"
    sources_data.append({
        "Source": f"{cex.exchange.upper()} OPEN",
        "Price": f"${cex.open:.4f}",
        "Reliability": reliability,
        "Note": "Test trade / TGE candle" if cex.hl_ratio > 30 else "TGE volatility"
    })

    # VWAP if available
    if cex.vwap_1h:
        vwap_reliability = "🟡 MEDIUM"
        note = "Suspect wicks" if "SUSPECT" in cex.flag else "Delayed" if "delay" in cex.flag.lower() else "Volume weighted avg"
        sources_data.append({
            "Source": f"{cex.exchange.upper()} VWAP 1h",
            "Price": f"${cex.vwap_1h:.4f}",
            "Reliability": vwap_reliability,
            "Note": note
        })

# Add DEX source
if token.dex_stabilization:
    sources_data.append({
        "Source": "DEX Stabilization",
        "Price": f"${token.dex_stabilization.reference_price:.4f}",
        "Reliability": f"🟢 {token.dex_stabilization.confidence}",
        "Note": f"{len(token.dex_stabilization.dex_prices)} DEX, spread {token.dex_stabilization.spread_pct:.2f}%"
    })

sources_df = pd.DataFrame(sources_data)
st.dataframe(sources_df, use_container_width=True, hide_index=True)
st.markdown("**Data sources:** [CCXT](https://github.com/ccxt/ccxt) (CEX) · [Flipside Crypto](https://flipsidecrypto.xyz) (DEX)")

st.markdown("---")

# 3.2 Final Benchmark Recommendation
st.subheader("FDV Benchmark - Recommended Values")

confidence_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(token.benchmark_confidence, "⚪")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Benchmark Price", f"${token.benchmark_price:.4f}")
    st.caption(f"Method: {token.benchmark_method.replace('_', ' ').title()}")

with col2:
    st.metric("FDV at TGE", f"${token.fdv_usd:,.0f}")
    st.caption(f"~${token.fdv_usd/1e9:.2f}B")

with col3:
    st.metric("MCap at TGE", f"${token.mcap_usd:,.0f}")
    st.caption(f"~${token.mcap_usd/1e6:.0f}M")

st.markdown("---")

# Summary box
col_sum1, col_sum2 = st.columns(2)

with col_sum1:
    st.markdown(f"""
    **Valuation Summary:**
    - **Price:** ${token.benchmark_price:.4f}
    - **FDV:** ${token.fdv_usd:,.0f}
    - **MCap TGE:** ${token.mcap_usd:,.0f}
    - **MCap/FDV:** {token.tge_circulating_pct}%
    """)

with col_sum2:
    st.markdown(f"""
    **Investment Metrics:**
    - **Total Raised:** ${token.total_raised:,}
    - **FDV/Raised:** {token.fdv_to_raised_ratio:.1f}x
    - **Confidence:** {confidence_emoji} {token.benchmark_confidence}
    """)

st.markdown("---")

# Footer - Methodology Notes
with st.expander("Methodology Notes"):
    for note in token.methodology_notes:
        st.markdown(f"- {note}")

    st.markdown("**Data Sources:**")
    for source in token.sources:
        st.markdown(f"- {source}")

st.caption(f"Last Updated: {token.last_updated}")
