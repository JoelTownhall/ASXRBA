"""ASX Rate Tracker - Streamlit web application.

Displays interactive charts of ASX interest rate futures data,
tracking market expectations for RBA cash rate movements.
"""

from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# --- Page config -----------------------------------------------------------

st.set_page_config(
    page_title="ASX Rate Tracker",
    page_icon="📈",
    layout="wide",
)

# --- Constants -------------------------------------------------------------

COMBINED_CSV = "./ASX-COMBINED/ASX-COMBINED.csv"
DAILY_DIR = "./ASX_DAILY_DATA/"
COOL_LOW = "#00d4ff"
COOL_HIGH = "#9b00ff"


# --- Data loading ----------------------------------------------------------

@st.cache_data(ttl=3600)
def load_combined() -> pd.DataFrame:
    """Load and return the combined ASX data (rows=dates, cols=forecast months)."""
    df = pd.read_csv(COMBINED_CSV, index_col=0)
    df.index = pd.PeriodIndex(df.index, freq="D")
    df.columns = pd.PeriodIndex(df.columns, freq="M")
    return df


@st.cache_data(ttl=3600)
def load_rba_ocr() -> tuple[pd.Series | None, pd.Series | None]:
    """Attempt to fetch RBA official cash rate (daily and monthly).
    Returns (None, None) if network is unavailable."""
    try:
        import readabs as ra
        daily = ra.read_rba_ocr(monthly=False).astype(float)
        monthly = ra.read_rba_ocr(monthly=True).astype(float)
        return daily, monthly
    except Exception:
        return None, None


def make_color_scale(n: int, low: str = COOL_LOW, high: str = COOL_HIGH) -> list[str]:
    """Generate n colours interpolated between low and high hex colours."""

    def hex_to_rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    r0, g0, b0 = hex_to_rgb(low)
    r1, g1, b1 = hex_to_rgb(high)
    colors = []
    for i in range(n):
        t = i / max(n - 1, 1)
        r = int(r0 + t * (r1 - r0))
        g = int(g0 + t * (g1 - g0))
        b = int(b0 + t * (b1 - b0))
        colors.append(f"#{r:02x}{g:02x}{b:02x}")
    return colors


# --- Chart builders --------------------------------------------------------

def chart_anticipated(df: pd.DataFrame, rba_monthly: pd.Series | None, start_date: str) -> go.Figure:
    """Fanned line chart of daily ASX rate tracker forecasts."""
    start_d = pd.Period(start_date, freq="D")
    start_m = pd.Period(start_date[:7], freq="M")

    data = df.loc[start_d:].T.loc[start_m:]  # rows=forecast month, cols=scrape date
    if data.empty:
        st.warning("No data available for the selected date range.")
        return go.Figure()

    colors = make_color_scale(len(data.columns))
    fig = go.Figure()

    # Fan of daily forecasts
    for i, col in enumerate(data.columns):
        series = data[col].dropna()
        if series.empty:
            continue
        x = [str(p) for p in series.index]
        fig.add_trace(go.Scatter(
            x=x,
            y=series.values,
            mode="lines",
            line={"color": colors[i], "width": 0.8},
            opacity=0.5,
            name=str(col),
            showlegend=False,
            hovertemplate=f"Date: {col}<br>Month: %{{x}}<br>Rate: %{{y:.3f}}%<extra></extra>",
        ))

    # Latest forecast highlighted
    final_col = data.columns[-1]
    final = data[final_col].dropna()
    fig.add_trace(go.Scatter(
        x=[str(p) for p in final.index],
        y=final.values,
        mode="lines",
        line={"color": "#660066", "width": 3},
        name=f"ASX at {final_col}",
    ))

    # RBA actual rate
    if rba_monthly is not None:
        rba = rba_monthly[start_m:].dropna()
        x_rba = [str(p) for p in rba.index]
        fig.add_trace(go.Scatter(
            x=x_rba,
            y=rba.values,
            mode="lines",
            line={"color": "#dd0000", "width": 3, "shape": "hv"},
            name="RBA Official Cash Rate",
        ))

    fig.update_layout(
        title="Market Anticipated RBA Policy Rates",
        xaxis_title="Forecast Month",
        yaxis_title="Policy Rate (% / year)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        hovermode="x unified",
    )
    return fig


def chart_end_of_month(df: pd.DataFrame, rba_monthly: pd.Series | None, from_month: str) -> go.Figure:
    """End-of-month ASX forecasts vs RBA actual rate."""
    start_m = pd.Period(from_month, freq="M")

    asx = df.copy()
    asx.index = pd.PeriodIndex(asx.index, freq="M")
    # Keep last row per calendar month
    asx = asx[~asx.index.duplicated(keep="last")]
    asx = asx.loc[start_m:].T  # rows=forecast month, cols=scrape month

    if asx.empty:
        return go.Figure()

    colors = make_color_scale(len(asx.columns))
    fig = go.Figure()

    for i, col in enumerate(asx.columns):
        series = asx[col].dropna()
        fig.add_trace(go.Scatter(
            x=[str(p) for p in series.index],
            y=series.values,
            mode="lines",
            line={"color": colors[i], "width": 1},
            name=str(col),
            showlegend=False,
            hovertemplate=f"End of {col}<br>Month: %{{x}}<br>Rate: %{{y:.3f}}%<extra></extra>",
        ))

    if rba_monthly is not None:
        rba = rba_monthly[from_month:].dropna()
        fig.add_trace(go.Scatter(
            x=[str(p) for p in rba.index],
            y=rba.values,
            mode="lines",
            line={"color": "darkred", "width": 2.5, "shape": "hv"},
            name="RBA Official Cash Rate",
        ))

    fig.update_layout(
        title=f"End-of-Month Market Anticipated RBA Policy Rates (from {from_month})",
        xaxis_title="Forecast Month",
        yaxis_title="Policy Rate (% / year)",
        hovermode="x unified",
    )
    return fig


def chart_endpoint(df: pd.DataFrame, rba_daily: pd.Series | None) -> go.Figure:
    """18-month endpoint forecast vs actual RBA rate."""
    endpoint = df.T.ffill().iloc[-1]
    # shift index forward by ~18 months
    endpoint.index = endpoint.index + 18
    endpoint = endpoint.dropna()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[str(p) for p in endpoint.index],
        y=endpoint.values,
        mode="lines",
        line={"color": "#0066cc", "width": 2},
        name="ASX Rate Tracker 18-month endpoint forecast",
    ))

    if rba_daily is not None:
        rba = rba_daily["2022-01-01":].dropna()
        fig.add_trace(go.Scatter(
            x=[str(p.date()) if hasattr(p, "date") else str(p) for p in rba.index],
            y=rba.values,
            mode="lines",
            line={"color": "red", "width": 2, "shape": "hv"},
            name="RBA Cash Rate",
        ))

    fig.update_layout(
        title="Market 18-Month Endpoint Forecast vs RBA Cash Rate",
        xaxis_title="Date",
        yaxis_title="Policy Rate (% / year)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        hovermode="x unified",
    )
    return fig


def chart_next_cut(df: pd.DataFrame, rba_daily: pd.Series | None, start: str) -> go.Figure:
    """When does the market fully anticipate the next 25bp cut?"""
    if rba_daily is None:
        fig = go.Figure()
        fig.add_annotation(text="RBA data unavailable (network error)", showarrow=False, font={"size": 16})
        return fig

    start_p = pd.Period(start, freq="M")
    df_cuts = df.loc[start:].dropna(how="all", axis=1)
    if df_cuts.empty:
        return go.Figure()

    when = df_cuts.apply(lambda x: x + 0.25 < rba_daily.reindex(x.index, method="ffill"), axis=0)
    whence = when.T.idxmax().where(when.T.any(), other=None)
    once = pd.Series(
        [(c - start_p).n if c is not None else np.nan for c in whence],
        index=whence.index,
        name="Months to Cut",
    )

    labels = [str(p) for p in pd.period_range(start=start, periods=int(once.max()) + 2, freq="M")]
    has_cut = once.dropna()
    no_cut = once[once.isna()]

    fig = go.Figure()
    if not has_cut.empty:
        fig.add_trace(go.Scatter(
            x=[str(p) for p in has_cut.index],
            y=has_cut.values,
            mode="lines+markers",
            marker={"size": 4},
            line={"width": 2},
            name="First fully anticipated cut",
            hovertemplate="Date: %{x}<br>Month: %{customdata}<extra></extra>",
            customdata=[labels[int(v)] if int(v) < len(labels) else "" for v in has_cut.values],
        ))
    if not no_cut.empty:
        fig.add_trace(go.Scatter(
            x=[str(p) for p in no_cut.index],
            y=[has_cut.min() if not has_cut.empty else 0] * len(no_cut),
            mode="markers",
            marker={"color": "red", "size": 4},
            name="No fully anticipated cut",
        ))

    fig.update_layout(
        title="Next Fully Anticipated RBA Rate Cut",
        xaxis_title="Scrape Date",
        yaxis={"tickmode": "array", "tickvals": list(range(len(labels))), "ticktext": labels},
        yaxis_title="Month of first anticipated cut",
        hovermode="x unified",
    )
    return fig


def chart_next_hike(df: pd.DataFrame, rba_daily: pd.Series | None, start: str) -> go.Figure:
    """When does the market fully anticipate the next 25bp hike?"""
    if rba_daily is None:
        fig = go.Figure()
        fig.add_annotation(text="RBA data unavailable (network error)", showarrow=False, font={"size": 16})
        return fig

    start_p = pd.Period(start, freq="M")
    df_hikes = df.loc[start:].dropna(how="all", axis=1)
    if df_hikes.empty:
        return go.Figure()

    when = df_hikes.apply(lambda x: x - 0.25 > rba_daily.reindex(x.index, method="ffill"), axis=0)
    whence = when.T.idxmax().where(when.T.any(), other=None)
    once = pd.Series(
        [(c - start_p).n if c is not None else np.nan for c in whence],
        index=whence.index,
        name="Months to Hike",
    )

    labels = [str(p) for p in pd.period_range(start=start, periods=max(int(once.max()) + 2, 5) if not once.dropna().empty else 5, freq="M")]
    has_hike = once.dropna()
    no_hike = once[once.isna()]

    fig = go.Figure()
    if not has_hike.empty:
        fig.add_trace(go.Scatter(
            x=[str(p) for p in has_hike.index],
            y=has_hike.values,
            mode="lines+markers",
            marker={"size": 6},
            line={"width": 2},
            name="First fully anticipated hike",
            hovertemplate="Date: %{x}<br>Month: %{customdata}<extra></extra>",
            customdata=[labels[int(v)] if int(v) < len(labels) else "" for v in has_hike.values],
        ))
    if not no_hike.empty:
        baseline = int(has_hike.min()) if not has_hike.empty else 0
        fig.add_trace(go.Scatter(
            x=[str(p) for p in no_hike.index],
            y=[baseline] * len(no_hike),
            mode="markers",
            marker={"color": "green", "size": 6},
            name="No fully anticipated hike",
        ))

    fig.update_layout(
        title="Next Fully Anticipated RBA Rate Hike",
        xaxis_title="Scrape Date",
        yaxis={"tickmode": "array", "tickvals": list(range(len(labels))), "ticktext": labels},
        yaxis_title="Month of first anticipated hike",
        hovermode="x unified",
    )
    return fig


# --- App layout ------------------------------------------------------------

def main() -> None:
    """Main Streamlit app."""
    st.title("ASX Rate Tracker")
    st.caption("Market expectations for RBA cash rate movements, derived from ASX interest rate futures.")

    # Load data
    if not Path(COMBINED_CSV).exists():
        st.error(f"Combined data file not found: `{COMBINED_CSV}`")
        st.info("Run `python asx_daily_data_capture.py` to capture daily data, then re-run the notebook to build the combined CSV.")
        return

    df = load_combined()

    with st.spinner("Fetching RBA official cash rate data..."):
        rba_daily, rba_monthly = load_rba_ocr()

    if rba_daily is None:
        st.warning("⚠️ RBA data unavailable (network error). Charts that require the official cash rate will show a placeholder.")

    # Sidebar controls
    with st.sidebar:
        st.header("Controls")
        data_min = str(df.index.min())
        data_max = str(df.index.max())
        st.caption(f"Data: {data_min} → {data_max}")

        anticipated_start = st.date_input(
            "Anticipated rates: show from",
            value=pd.Timestamp("2025-06-01"),
            min_value=pd.Timestamp(data_min),
            max_value=pd.Timestamp(data_max),
        )

        eom_from = st.selectbox(
            "End-of-month view: from month",
            options=["2022-04", "2024-12", "2025-06"],
            index=1,
        )

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Anticipated Rates",
        "End-of-Month View",
        "18M Endpoint",
        "Next Cut",
        "Next Hike",
    ])

    with tab1:
        st.plotly_chart(
            chart_anticipated(df, rba_monthly, str(anticipated_start)),
            width="stretch",
        )
        st.caption(
            "Each line shows the market-implied cash rate path for each day the data was captured. "
            "Coloured from cyan (earliest) to purple (latest). The bold purple line is the most recent forecast."
        )

    with tab2:
        st.plotly_chart(
            chart_end_of_month(df, rba_monthly, eom_from),
            width="stretch",
        )
        st.caption("End-of-month snapshots of the market-implied rate path, plotted against the actual RBA cash rate.")

    with tab3:
        st.plotly_chart(chart_endpoint(df, rba_daily), width="stretch")
        st.caption(
            "The furthest-forward implied rate from each day's ASX data, shifted 18 months forward in time, "
            "plotted against the actual RBA cash rate."
        )

    with tab4:
        cut_start = st.selectbox(
            "Cut chart: show from",
            options=["2025-01", "2025-06", "2024-12"],
            index=0,
            key="cut_start",
        )
        st.plotly_chart(chart_next_cut(df, rba_daily, cut_start), width="stretch")
        st.caption("The first month in which the market fully prices in a 25bp cut from the prevailing RBA cash rate.")

    with tab5:
        hike_start = st.selectbox(
            "Hike chart: show from",
            options=["2025-06", "2025-01", "2024-12"],
            index=0,
            key="hike_start",
        )
        st.plotly_chart(chart_next_hike(df, rba_daily, hike_start), width="stretch")
        st.caption("The first month in which the market fully prices in a 25bp hike above the prevailing RBA cash rate.")

    # Data table expander
    with st.expander("Raw combined data"):
        display_df = df.copy()
        display_df.index = display_df.index.astype(str)
        display_df.columns = display_df.columns.astype(str)
        st.dataframe(display_df.tail(30), width="stretch")
        st.caption(f"Showing last 30 rows of {len(df)} total. Rows = scrape dates, columns = forecast months.")


main()
