import sqlite3
import time
import pandas as pd
import requests
import json

BASE_URL = "https://api.openf1.org/v1"
DB_NAME = "f1_season_2024.db"


def fetch_json_to_df(endpoint: str, params: dict = None) -> pd.DataFrame:
    """Helper to call OpenF1, respect rate limits (3 req/sec), and return a DataFrame."""
    url = f"{BASE_URL}/{endpoint}"
    response = requests.get(url, params=params)

    # Respect OpenF1 free tier rate limits (3 requests per second)
    time.sleep(0.35)

    if response.status_code == 200:
        data = response.json()
        return pd.DataFrame(data)
    else:
        print(
            f"⚠️ Error {response.status_code} fetching {endpoint} with"
            f" params {params}"
        )
        return pd.DataFrame()


def build_2024_season_database():
    # Connect to SQLite (creates the file if it doesn't exist)
    conn = sqlite3.connect(DB_NAME)
    print(f"📦 Connected to SQLite database: {DB_NAME}")

    # 1. Fetch all 2024 sessions (Filtering for Grand Prix Weekends - Qualifying or Race)
    print("🔍 Fetching 2024 sessions...")
    sessions_df = fetch_json_to_df("sessions", {"year": 2024})

    if sessions_df.empty:
        print("❌ No sessions found. Check API connectivity.")
        return

    # Filter down to Qualifying or Race sessions to keep data scope manageable for v1.0
    target_sessions = sessions_df[
        sessions_df["session_name"].isin(["Qualifying", "Race"])
    ]
    print(f"✅ Found {len(target_sessions)} target sessions (Quali/Race) for 2024.")

    # Save sessions metadata to SQLite
    target_sessions.to_sql("dim_sessions", conn, if_exists="replace", index=False)

    all_laps = []
    all_drivers = []

    # 2. Loop through each session to grab drivers and lap times
    for index, session in target_sessions.iterrows():
        session_key = session["session_key"]
        location = session["location"]
        session_type = session["session_name"]

        print(
            f"➡️ Processing Session: {session['year']} {location} - {session_type}"
            f" (Key: {session_key})"
        )

        # Fetch drivers for this session
        drivers_df = fetch_json_to_df("drivers", {"session_key": session_key})
        if not drivers_df.empty:
            drivers_df["session_key"] = session_key
            all_drivers.append(drivers_df)

        # Fetch laps for this session (OpenF1 allows fetching session-level laps without driver filters on some calls, or per driver)
        laps_df = fetch_json_to_df("laps", {"session_key": session_key})
        if not laps_df.empty:
            laps_df["session_key"] = session_key
            all_laps.append(laps_df)

    # 3. Consolidate and write to SQLite tables
    if all_drivers:
        master_drivers_df = pd.concat(all_drivers, ignore_index=True)
        master_drivers_df.to_sql("dim_drivers", conn, if_exists="replace", index=False)
        print(f"💾 Saved {len(master_drivers_df)} driver records to 'dim_drivers'.")

    if all_laps:
        master_laps_df = pd.concat(all_laps, ignore_index=True)

        # -------------------------------------------------------------
        # FIX: Convert nested list columns to JSON strings for SQLite
        # -------------------------------------------------------------
        list_columns = [
            "segments_sector_1",
            "segments_sector_2",
            "segments_sector_3",
        ]

        for col in list_columns:
            if col in master_laps_df.columns:
                # Convert Python lists to JSON strings (or empty string if NaN)
                master_laps_df[col] = master_laps_df[col].apply(
                    lambda x: json.dumps(x) if isinstance(x, list) else None
                )

        # Write clean DataFrame to SQLite
        master_laps_df.to_sql("fact_laps", conn, if_exists="replace", index=False)
        print(f"💾 Saved {len(master_laps_df)} lap records to 'fact_laps'.")

    conn.close()
    print("🎉 v1.0 Database Ingestion Complete!")


if __name__ == "__main__":
    build_2024_season_database()
