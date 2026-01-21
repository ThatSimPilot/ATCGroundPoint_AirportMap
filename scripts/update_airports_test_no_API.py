from update_airports import main


if __name__ == "__main__":
    # Steam only, no Discord; AeroDataBox enabled by default
    main(run_steam=True, run_discord=True, use_aerodatabox=False)
