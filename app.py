import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st

# Page Configuration
st.set_page_config(page_title="F1 Virtual Race Engineer", page_icon="🏎️", layout="wide")

DB_NAME = "f1_season_2024.db"


@st.cache_data
def load_data(query: str) -> pd.DataFrame:
    """Helper to query SQLite database and return a DataFrame."""
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(
            f"Database connection error: {e}. Make sure you ran your ingestion script"
            " first!"
        )
        return pd.DataFrame()


st.title("🏎️ Virtual Race Engineer: Driver Lap Comparison")
st.markdown(
    "Analyze and compare driver performance across the **2024 F1 Season** using"
    " local SQLite data."
)

# 1. Load Sessions
sessions_df = load_data(
    "SELECT DISTINCT session_key, location, session_name FROM dim_sessions"
)

if sessions_df.empty:
    st.warning(
        "⚠️ No session data found in `f1_season_2024.db`. Run your data ingestion"
        " script first."
    )
    st.stop()

# Create a clean label for dropdown
sessions_df["display_label"] = (
    sessions_df["location"] + " - " + sessions_df["session_name"]
)
session_options = sessions_df["display_label"].tolist()

# Session Selector Widget
selected_session_label = st.selectbox("Select Grand Prix & Session", session_options)

# Extract chosen session_key
selected_row = sessions_df[sessions_df["display_label"] == selected_session_label].iloc[
    0
]
session_key = selected_row["session_key"]

# 2. Load Drivers for the Selected Session
drivers_df = load_data(
    f"SELECT DISTINCT driver_number, full_name, team_name FROM dim_drivers"
    f" WHERE session_key = {session_key}"
)

if drivers_df.empty:
    st.warning("No drivers found for this session.")
    st.stop()

drivers_df["display_driver"] = (
    drivers_df["driver_number"].astype(str)
    + " - "
    + drivers_df["full_name"]
    + " ("
    + drivers_df["team_name"]
    + ")"
)
driver_options = drivers_df["display_driver"].tolist()

# Driver Comparison Columns
col1, col2 = st.columns(2)
with col1:
    driver_a_choice = st.selectbox("Select Driver A", driver_options, index=0)
with col2:
    driver_b_choice = st.selectbox(
        "Select Driver B",
        driver_options,
        index=min(1, len(driver_options) - 1),
    )

# Extract driver numbers
driver_a_num = int(driver_a_choice.split(" - ")[0])
driver_b_num = int(driver_b_choice.split(" - ")[0])

# 3. Query Laps Data for Selected Drivers
query_laps = f"""
    SELECT driver_number, lap_number, lap_duration, is_pit_out_lap
    FROM fact_laps
    WHERE session_key = {session_key} 
      AND driver_number IN ({driver_a_num}, {driver_b_num})
      AND lap_duration IS NOT NULL
    ORDER BY lap_number
"""
laps_df = load_data(query_laps)

if laps_df.empty:
    st.info("No lap duration data recorded for these drivers in this session.")
else:
    # Filter out pit-out laps to focus purely on racing/push laps
    clean_laps = laps_df[laps_df["is_pit_out_lap"] == 0].copy()

    # Map driver numbers to names for cleaner legends
    num_to_name = dict(zip(drivers_df["driver_number"], drivers_df["full_name"]))
    clean_laps["driver_name"] = clean_laps["driver_number"].map(num_to_name)

    st.markdown("---")
    st.subheader(f"📈 Lap Time Progression ({selected_session_label})")

    # Plotly Interactive Line Chart
    fig = px.line(
        clean_laps,
        x="lap_number",
        y="lap_duration",
        color="driver_name",
        markers=True,
        labels={
            "lap_number": "Lap Number",
            "lap_duration": "Lap Time (Seconds)",
            "driver_name": "Driver",
        },
    )

    fig.update_layout(
        xaxis_title="Lap Number",
        yaxis_title="Lap Duration (s)",
        legend_title="Driver",
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)

    # 4. Quick Summary Metrics Block
    st.markdown("### ⚡ Fastest Lap Summary")
    fastest_laps = (
        clean_laps.groupby(["driver_number", "driver_name"])["lap_duration"]
        .min()
        .reset_index()
    )

    metric_cols = st.columns(2)
    for idx, row in fastest_laps.iterrows():
        with metric_cols[idx]:
            st.metric(
                label=f"{row['driver_name']} (Driver #{row['driver_number']})",
                value=f"{row['lap_duration']:.3f} seconds",
            )
