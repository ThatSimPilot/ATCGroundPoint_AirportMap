"""
Legacy wrapper script to only run the Steam ingestion part.

Keeps your existing GitHub Actions or local commands working:
  python update_airports_from_steam.py

Uses the shared orchestrator in update_airports.py.
"""

from update_airports import main


if __name__ == "__main__":
    # Steam only, no Discord; AeroDataBox enabled by default
    main(run_steam=True, run_discord=False, use_aerodatabox=True)
