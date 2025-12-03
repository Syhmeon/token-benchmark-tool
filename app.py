#!/usr/bin/env python3
"""
Token Benchmark Dashboard - Streamlit App

Run with: streamlit run app.py
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from src.storage.json_store import BenchmarkStore

# Canonical allocation bucket order
CANONICAL_BUCKET_ORDER = [
    "Team / Founder",
    "Advisors / Partners",
    "Investors",
    "Public Sales",
    "Airdrop",
    "Community / Rewards",
    "Listing / Liquidity",
    "Ecosystem / R&D",
    "Treasury / Reserve",
    "Unknown / Other"
]

def sort_allocations_canonical(allocations):
    """Sort allocations by canonical bucket order."""
    def get_order(alloc):
        bucket = alloc.bucket
        try:
            return CANONICAL_BUCKET_ORDER.index(bucket)
        except ValueError:
            return len(CANONICAL_BUCKET_ORDER)  # Unknown buckets at end
    return sorted(allocations, key=get_order)

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

st.header("2. INITIAL VALUATION (FDV)")

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
    if hasattr(cex, 'first_candles_1m'):
        if cex.first_candles_1m:
            cex_with_candles = cex
            break
    elif isinstance(cex, dict) and cex.get('first_candles_1m'):
        cex_with_candles = cex
        break

# Check for DEX first candles if no CEX data
dex_candles = None
dex_name = None
if token.dex_stabilization:
    dex = token.dex_stabilization
    if hasattr(dex, 'first_candles_1m') and dex.first_candles_1m:
        dex_candles = dex.first_candles_1m
        dex_name = getattr(dex, 'first_dex', 'DEX')
        dex_time = getattr(dex, 'first_dex_time', '')

if cex_with_candles:
    # CEX data available
    candles = cex_with_candles.first_candles_1m if hasattr(cex_with_candles, 'first_candles_1m') else cex_with_candles.get('first_candles_1m', [])
    exchange_name = cex_with_candles.exchange if hasattr(cex_with_candles, 'exchange') else cex_with_candles.get('exchange', 'Unknown')

    st.markdown(f"**{exchange_name.upper()}/USDT (CEX)** - First 10 minutes after listing:")

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

    max_candle = max(candles, key=lambda x: x['high'])
    st.markdown(f"- **Peak:** ${max_candle['high']:.2f} at minute {max_candle['minute']} ({max_candle['time']})")

    with st.expander("View Candlestick Chart"):
        chart_data = pd.DataFrame(candles)
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=chart_data['minute'],
            open=chart_data['open'],
            high=chart_data['high'],
            low=chart_data['low'],
            close=chart_data['close'],
            name="Price",
            hovertext=[f"Time: {t}" for t in chart_data['time']],
        ))

        # Calculate reasonable y-axis range (exclude extreme outliers for better visibility)
        prices = list(chart_data['open']) + list(chart_data['close'])
        median_price = sorted(prices)[len(prices)//2]
        y_min = min(chart_data['low'].min(), median_price * 0.5)
        y_max = max(chart_data['high'].max(), median_price * 2)

        fig.update_layout(
            title=f"{exchange_name.upper()} (CEX) - First 10 Minutes",
            xaxis_title="Minute",
            yaxis_title="Price (USD)",
            height=450,
            xaxis=dict(
                tickmode='linear',
                tick0=1,
                dtick=1,
                range=[0.5, 10.5]
            ),
            yaxis=dict(
                tickformat="$.2f",
                range=[y_min * 0.9, y_max * 1.1]
            ),
            hovermode='x unified'
        )

        # Add annotation for extreme values if present
        max_high = chart_data['high'].max()
        if max_high > median_price * 3:
            max_idx = chart_data['high'].idxmax()
            fig.add_annotation(
                x=chart_data.loc[max_idx, 'minute'],
                y=max_high,
                text=f"Peak: ${max_high:.2f}",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=1,
                ax=0,
                ay=-30
            )

        st.plotly_chart(fig, use_container_width=True)

elif dex_candles:
    # No CEX data, but DEX data available
    st.warning("⚠️ No CEX minute-level data available. Showing **DEX price discovery** instead (source: Flipside).")

    st.markdown(f"**{dex_name.upper().replace('_', ' ')} (DEX)** - First 10 minutes after listing:")

    candles_data = []
    for candle in dex_candles:
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
    first_candle = dex_candles[0]
    last_candle = dex_candles[-1]
    drop_pct = ((last_candle['close'] - first_candle['open']) / first_candle['open']) * 100
    st.markdown(f"- **{first_candle['time']}:** First DEX trade at ${first_candle['open']:.2f}")
    st.markdown(f"- **Price evolution:** ${first_candle['open']:.2f} → ${last_candle['close']:.2f} ({drop_pct:+.1f}% in 10 min)")

    with st.expander("View Price Chart"):
        chart_data = pd.DataFrame(dex_candles)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_data['minute'],
            y=chart_data['close'],
            mode='lines+markers',
            name="DEX Price",
            line=dict(color='#00CC96', width=2),
            hovertext=[f"Time: {t}<br>Close: ${c:.2f}" for t, c in zip(chart_data['time'], chart_data['close'])]
        ))
        fig.update_layout(
            title=f"{dex_name.upper().replace('_', ' ')} (DEX) - First 10 Minutes",
            xaxis_title="Minute",
            yaxis_title="Price (USD)",
            height=450,
            xaxis=dict(
                tickmode='linear',
                tick0=1,
                dtick=1,
                range=[0.5, 10.5]
            ),
            yaxis=dict(
                tickformat="$.2f"
            ),
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("No minute-by-minute price discovery data available (CEX or DEX)")

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

# 2.6 Price Discovery Chart (Combined CEX/DEX)
st.subheader("Price Discovery - All Sources")

price_chart_data = []
colors = []

# Add CEX OPEN prices
for cex in token.cex_data:
    price_chart_data.append({
        "Source": f"{cex.exchange.upper()} Open",
        "Price": cex.open,
        "Type": "CEX Open"
    })
    colors.append("#EF553B")  # Red for CEX Open

    if cex.vwap_1h:
        price_chart_data.append({
            "Source": f"{cex.exchange.upper()} VWAP",
            "Price": cex.vwap_1h,
            "Type": "CEX VWAP"
        })
        colors.append("#636EFA")  # Blue for VWAP

# Add DEX prices
if token.dex_stabilization:
    for dex_name, price in token.dex_stabilization.dex_prices.items():
        price_chart_data.append({
            "Source": dex_name.replace("_", " ").title(),
            "Price": price,
            "Type": "DEX Stabilized"
        })
        colors.append("#00CC96")  # Green for DEX

    # Add benchmark
    price_chart_data.append({
        "Source": "BENCHMARK",
        "Price": token.benchmark_price,
        "Type": "Benchmark"
    })
    colors.append("#AB63FA")  # Purple for benchmark

if price_chart_data:
    price_df = pd.DataFrame(price_chart_data)

    fig_prices = go.Figure()

    # Color mapping
    color_map = {
        "CEX Open": "#EF553B",
        "CEX VWAP": "#636EFA",
        "DEX Stabilized": "#00CC96",
        "Benchmark": "#AB63FA"
    }

    for price_type in ["CEX Open", "CEX VWAP", "DEX Stabilized", "Benchmark"]:
        df_type = price_df[price_df["Type"] == price_type]
        if not df_type.empty:
            fig_prices.add_trace(go.Bar(
                x=df_type["Source"],
                y=df_type["Price"],
                name=price_type,
                marker_color=color_map[price_type],
                text=[f"${p:.4f}" for p in df_type["Price"]],
                textposition="outside"
            ))

    # Add benchmark line
    fig_prices.add_hline(
        y=token.benchmark_price,
        line_dash="dash",
        line_color="#AB63FA",
        annotation_text=f"Benchmark: ${token.benchmark_price:.4f}"
    )

    fig_prices.update_layout(
        title=f"{token.name} ({token.symbol}) - Price Discovery at TGE",
        xaxis_title="Source",
        yaxis_title="Price (USD)",
        height=450,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig_prices, use_container_width=True)

st.markdown("---")

# 2.7 Sources Comparison Table
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

# 2.8 FDV Benchmark - Recommended Values
st.subheader("FDV Benchmark - Recommended Values")

confidence_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(token.benchmark_confidence, "⚪")

col_bench1, col_bench2, col_bench3 = st.columns(3)

with col_bench1:
    st.metric("Benchmark Price", f"${token.benchmark_price:.4f}")
    st.caption(f"Method: {token.benchmark_method.replace('_', ' ').title()}")

with col_bench2:
    st.metric("FDV at TGE", f"${token.fdv_usd:,.0f}")
    st.caption(f"~${token.fdv_usd/1e9:.2f}B")

with col_bench3:
    st.metric("MCap at TGE", f"${token.mcap_usd:,.0f}")
    st.caption(f"~${token.mcap_usd/1e6:.0f}M")

st.markdown("---")

# Summary box
col_val1, col_val2 = st.columns(2)

with col_val1:
    st.markdown(f"""
    **Valuation Summary:**
    - **Price:** ${token.benchmark_price:.4f}
    - **FDV:** ${token.fdv_usd:,.0f}
    - **MCap TGE:** ${token.mcap_usd:,.0f}
    - **MCap/FDV:** {token.tge_circulating_pct}%
    """)

with col_val2:
    st.markdown(f"""
    **Investment Metrics:**
    - **Total Raised:** ${token.total_raised:,}
    - **FDV/Raised:** {token.fdv_to_raised_ratio:.1f}x
    - **Confidence:** {confidence_emoji} {token.benchmark_confidence}
    """)

# 2.9 Methodology Notes (part of Section 2)
st.markdown("---")
with st.expander("Methodology Notes"):
    for note in token.methodology_notes:
        st.markdown(f"- {note}")

    st.markdown("**Data Sources:**")
    for source in token.sources:
        st.markdown(f"- {source}")

st.markdown("---")

# ============================================================================
# SECTION 3: TOKEN ALLOCATIONS
# ============================================================================

st.header("3. TOKEN ALLOCATIONS")

if token.allocations:
    # Sort allocations by canonical order
    sorted_allocations = sort_allocations_canonical(token.allocations)

    col_alloc1, col_alloc2 = st.columns(2)

    with col_alloc1:
        # Pie chart
        alloc_labels = [a.bucket for a in sorted_allocations]
        alloc_values = [a.percentage for a in sorted_allocations]

        fig_pie = go.Figure(data=[go.Pie(
            labels=alloc_labels,
            values=alloc_values,
            hole=0.3,
            textinfo='label+percent',
            textposition='outside'
        )])
        fig_pie.update_layout(
            title="Token Distribution",
            height=400,
            showlegend=False
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_alloc2:
        # TGE Unlock bar chart
        alloc_tge_data = []
        for a in sorted_allocations:
            alloc_tge_data.append({
                "Bucket": a.bucket,
                "Unlocked at TGE": a.tge_unlock_pct,
                "Locked/Vesting": 100 - a.tge_unlock_pct
            })

        alloc_tge_df = pd.DataFrame(alloc_tge_data)

        fig_tge = go.Figure()
        fig_tge.add_trace(go.Bar(
            x=alloc_tge_df["Bucket"],
            y=alloc_tge_df["Unlocked at TGE"],
            name="Unlocked at TGE",
            marker_color="#00CC96"
        ))
        fig_tge.add_trace(go.Bar(
            x=alloc_tge_df["Bucket"],
            y=alloc_tge_df["Locked/Vesting"],
            name="Locked/Vesting",
            marker_color="#EF553B"
        ))
        fig_tge.update_layout(
            title="TGE Unlock vs Locked",
            barmode="stack",
            xaxis_title="",
            yaxis_title="Percentage",
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02)
        )
        st.plotly_chart(fig_tge, use_container_width=True)

    # Allocation table
    st.subheader("Allocation Details")
    alloc_table = []
    for a in sorted_allocations:
        alloc_table.append({
            "Bucket": a.bucket,
            "Percentage": f"{a.percentage}%",
            "Tokens": f"{a.tokens:,}",
            "TGE Unlock": f"{a.tge_unlock_pct}%",
            "Vesting": a.vesting
        })

    alloc_df = pd.DataFrame(alloc_table)
    st.dataframe(alloc_df, use_container_width=True, hide_index=True)

    # Vesting Timeline Chart - Monthly Unlock Histogram
    st.subheader("Token Release Schedule")

    # Check if we have vesting data
    has_vesting = any(hasattr(a, 'vesting_months') and a.vesting_months > 0 for a in sorted_allocations)

    if has_vesting:
        # Parse listing date for date axis
        try:
            listing_date = datetime.strptime(token.listing_date, "%Y-%m-%d")
        except (ValueError, TypeError):
            listing_date = datetime(2024, 1, 1)  # Fallback

        # Generate monthly unlock schedule
        max_months = max(
            (getattr(a, 'cliff_months', 0) or 0) + (getattr(a, 'vesting_months', 0) or 0)
            for a in sorted_allocations
        )
        max_months = min(max_months, 60)  # Cap at 5 years

        # Calculate monthly unlocks (tokens released each month, not cumulative)
        unlock_data = []

        for month in range(0, max_months + 1):
            month_date = listing_date + relativedelta(months=month)
            month_label = month_date.strftime("%b %Y")

            month_data = {
                "Month": month,
                "Date": month_label,
                "DateFull": month_date
            }

            for a in sorted_allocations:
                tge_pct = a.tge_unlock_pct or 0
                cliff = getattr(a, 'cliff_months', 0) or 0
                vest_duration = getattr(a, 'vesting_months', 0) or 0
                total_tokens = a.tokens or 0

                # Calculate tokens unlocked THIS month (not cumulative)
                tokens_this_month = 0
                remaining_tokens = total_tokens * ((100 - tge_pct) / 100)

                if month == 0:
                    # TGE unlock
                    tokens_this_month = total_tokens * (tge_pct / 100)
                elif vest_duration > 0:
                    # Cliff = waiting period, then linear vesting starts
                    # "12 month cliff, 36 month vest" = nothing months 1-11, linear months 12-36
                    if month < cliff:
                        # During cliff period - nothing unlocks
                        tokens_this_month = 0
                    elif month >= cliff and month <= vest_duration:
                        # Linear vesting period (after cliff)
                        months_of_vesting = vest_duration - cliff
                        if months_of_vesting > 0:
                            monthly_unlock = remaining_tokens / months_of_vesting
                            tokens_this_month = monthly_unlock
                        else:
                            # Edge case: vest_duration == cliff means all unlocks at cliff
                            tokens_this_month = remaining_tokens if month == cliff else 0

                month_data[a.bucket] = round(tokens_this_month)

            unlock_data.append(month_data)

        unlock_df = pd.DataFrame(unlock_data)

        # Create stacked bar chart
        fig_vesting = go.Figure()
        colors = ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3", "#FF6692", "#B6E880"]

        for i, a in enumerate(sorted_allocations):
            if a.bucket in unlock_df.columns:
                y_values = unlock_df[a.bucket]
                # Only add trace if there are non-zero values
                if y_values.sum() > 0:
                    fig_vesting.add_trace(go.Bar(
                        x=unlock_df["Month"],
                        y=y_values,
                        name=a.bucket,
                        marker_color=colors[i % len(colors)],
                        hovertemplate=f"<b>{a.bucket}</b><br>" +
                                      "Month %{x}<br>" +
                                      "Tokens: %{y:,.0f}<br>" +
                                      "<extra></extra>"
                    ))

        # Create date labels for x-axis (every 3 months for readability)
        tickvals = list(range(0, max_months + 1, 3))
        ticktext = [(listing_date + relativedelta(months=m)).strftime("%b '%y") for m in tickvals]

        fig_vesting.update_layout(
            title="Monthly Token Unlocks (Release Schedule)",
            xaxis=dict(
                title="",
                tickmode='array',
                tickvals=tickvals,
                ticktext=[f"{m}<br>{d}" for m, d in zip(tickvals, ticktext)],  # Month + Date
                tickangle=0
            ),
            yaxis=dict(
                title="Tokens Released",
                tickformat=",d"
            ),
            barmode='stack',
            height=500,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5
            ),
            hovermode="x unified"
        )

        # Add annotation for TGE
        fig_vesting.add_annotation(
            x=0,
            y=unlock_df[[a.bucket for a in sorted_allocations if a.bucket in unlock_df.columns]].iloc[0].sum(),
            text="TGE",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-30,
            font=dict(size=10, color="white"),
            bgcolor="#AB63FA"
        )

        st.plotly_chart(fig_vesting, use_container_width=True)

        # Summary stats
        total_tge = sum(a.tokens * (a.tge_unlock_pct / 100) for a in sorted_allocations if a.tokens and a.tge_unlock_pct)
        st.caption(f"📅 TGE: {listing_date.strftime('%d %b %Y')} | TGE Unlock: {total_tge:,.0f} tokens ({total_tge/token.total_supply*100:.1f}% of supply)")

    else:
        st.info("Vesting timeline data not available")

else:
    st.info("No allocation data available")

st.markdown("---")

# ============================================================================
# SECTION 4: HOLDER DISTRIBUTION
# ============================================================================

st.header("4. HOLDER DISTRIBUTION")

if token.holders:
    col_hold1, col_hold2 = st.columns(2)

    with col_hold1:
        st.metric("Total Holders", f"{token.holders.total_holders:,}")
        st.metric("Top 10 Holders", f"{token.holders.top_10_pct}%")

    with col_hold2:
        st.metric("Top 50 Holders", f"{token.holders.top_50_pct}%")
        st.metric("Top 100 Holders", f"{token.holders.top_100_pct}%")

    # Top holders bar chart
    if token.holders.top_holders:
        st.subheader("Top 10 Holders")

        top_holders_df = pd.DataFrame(token.holders.top_holders)

        fig_holders = go.Figure()
        fig_holders.add_trace(go.Bar(
            x=[f"#{h.get('rank', i+1)}" for i, h in enumerate(token.holders.top_holders)],
            y=[h.get('pct', 0) for h in token.holders.top_holders],
            text=[f"{h.get('pct', 0)}%" for h in token.holders.top_holders],
            textposition='outside',
            marker_color='#636EFA',
            hovertext=[h.get('label', 'Unknown') for h in token.holders.top_holders]
        ))

        fig_holders.update_layout(
            title="Top 10 Token Holders by % Supply",
            xaxis_title="Holder Rank",
            yaxis_title="% of Total Supply",
            height=350,
            showlegend=False
        )

        st.plotly_chart(fig_holders, use_container_width=True)

        # Table
        holder_table = []
        for h in token.holders.top_holders:
            holder_table.append({
                "Rank": f"#{h.get('rank', '?')}",
                "% Supply": f"{h.get('pct', 0)}%",
                "Label": h.get('label', 'Unknown')
            })

        st.dataframe(pd.DataFrame(holder_table), use_container_width=True, hide_index=True)

    st.caption(f"Source: {token.holders.source} | Snapshot: {token.holders.snapshot_date}")

    # Display methodology notes if available
    if hasattr(token.holders, 'notes') and token.holders.notes:
        with st.expander("📝 Data Notes"):
            st.markdown(token.holders.notes)
else:
    st.info("Holder distribution data not available")

st.markdown("---")
st.caption(f"Last Updated: {token.last_updated}")
