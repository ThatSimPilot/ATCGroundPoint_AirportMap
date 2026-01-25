import asyncio
import json
import os
import sys
import re
import time
import shutil
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

import requests

# Optional import for Discord. If it is not installed, Discord step will be skipped.
try:
    import discord
except ImportError:
    discord = None

# --------------------------------------------------------------------
# Paths and config
# --------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

load_dotenv(ROOT / ".env")

AIRPORTS_PATH = DATA_DIR / "airports.json"

CACHE_DIR = ROOT / "cache" / "aerodatabox"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Steam browse URL (most recent, ready-to-use items for appid 3239550)
STEAM_BROWSE_BASE_URL = (
    "https://steamcommunity.com/workshop/browse/"
    "?appid=3239550&browsesort=mostrecent&section=readytouseitems"
)

STEAM_API_URL = (
    "https://api.steampowered.com/ISteamRemoteStorage/"
    "GetPublishedFileDetails/v1/"
)

# AeroDataBox via APIMarket
APIMARKET_BASE_URL = "https://prod.api.market/api/v1/aedbx/aerodatabox"
APIMARKET_API_KEY = os.environ.get("APIMARKET_API_KEY")


# Discord
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
# Forum or text channel where airports are posted. Use channel ID, not the guild ID.
# For your link https://discord.com/channels/1312377412251680858/1401508715756126309
# the channel id is 1401508715756126309
DISCORD_CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID")


# --------------------------------------------------------------------
# Utility helpers
# --------------------------------------------------------------------

def check_json_exists(path: Path = AIRPORTS_PATH):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if path.exists():
        print("[INFO] airports.json exists. Continuing.")
        return
    
    base_path = DATA_DIR / "baseAirports.json"
    if not base_path.exists() and not path.exists():
        print("[ERROR] baseAirports.json does not exist in data/. Cannot create airports.json")
        sys.exit(1)

    print("[ERROR] airports.json does not exist in data/. Creating.")
    shutil.copyfile(base_path, path)
    print("[INFO] Created airports.json from baseAirports.json.")
        

def read_json(path: Path, fallback):
    if not path.exists():
        print(f"[WARN] {path} does not exist, using fallback.")
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] Failed to read {path}: {e}. Using fallback.")
        return fallback


def write_json(path: Path, data):
    text = json.dumps(data, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def to_iso_timestamp(unix_seconds):
    if not unix_seconds:
        return None
    return datetime.fromtimestamp(unix_seconds, tz=timezone.utc).isoformat()


def extract_icao_from_text(text: str) -> str | None:
    """
    Try to find a 4-letter ICAO code in text.
    Returns the first valid 4-letter uppercase token.
    """
    if not text:
        return None
    
    text = text.upper()
    matches = re.findall(r"\b([A-Z]{4})\b", text)
    blacklist = {"ATCG", "MSFS"}  # add more if needed

    for code in matches:
        if code not in blacklist:
            return code
    return None


# --------------------------------------------------------------------
# Airports.json state handling
# --------------------------------------------------------------------

def load_airports_state():
    """
    Load airports.json and split into:
      - schema_version
      - base_airports (status == 'base')
      - non_base_airports
      - existing_icaos (uppercase set)
    """
    airports_data = read_json(
        AIRPORTS_PATH,
        {"schemaVersion": 1, "lastUpdated": None, "airports": []},
    )

    schema_version = airports_data.get("schemaVersion", 1)
    all_airports = airports_data.get("airports") or []
    if not isinstance(all_airports, list):
        all_airports = []

    base_airports = [
        a for a in all_airports
        if (a.get("status") == "base") and a.get("icao")
    ]
    non_base_airports = [
        a for a in all_airports
        if (a.get("status") != "base") and a.get("icao")
    ]

    existing_icaos = {
        (a.get("icao") or "").upper()
        for a in all_airports
        if a.get("icao")
    }

    print(
        f"[INFO] Loaded {len(base_airports)} base + "
        f"{len(non_base_airports)} non-base airports "
        f"(unique ICAOs: {len(existing_icaos)})."
    )

    return schema_version, base_airports, non_base_airports, existing_icaos


# --------------------------------------------------------------------
# Steam scraping
# --------------------------------------------------------------------

def fetch_workshop_ids_from_browse(max_pages=None):
    """
    Scrape the Steam browse pages for workshop IDs.

    If max_pages is None, continue until a page has no items,
    with a safety cap.
    """
    ids: list[str] = []
    seen: set[str] = set()

    page = 1
    safety_cap = 50

    while True:
        if max_pages is not None and page > max_pages:
            break
        if page > safety_cap:
            print(f"[WARN] Reached safety page cap {safety_cap}.")
            break

        url = f"{STEAM_BROWSE_BASE_URL}&p={page}"
        print(f"[INFO] Fetching Steam browse page: {url}")
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        html = resp.text

        found = re.findall(r"filedetails/\?id=(\d+)", html)
        if not found:
            print(f"[INFO] No workshop items on page {page}, stopping.")
            break

        new_count = 0
        for wid in found:
            if wid not in seen:
                seen.add(wid)
                ids.append(wid)
                new_count += 1

        print(
            f"[INFO] Page {page}: found {len(found)} ids, "
            f"{new_count} new (total {len(ids)})."
        )

        page += 1
        time.sleep(1.0)

    return ids


def fetch_workshop_details(workshop_id: str) -> dict:
    payload = {
        "itemcount": 1,
        "publishedfileids[0]": workshop_id,
    }

    print(f"[INFO] Fetching Steam details for {workshop_id}...")
    resp = requests.post(STEAM_API_URL, data=payload, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    details_list = (
        data.get("response", {}).get("publishedfiledetails", []) or []
    )
    if not details_list:
        raise RuntimeError(f"No details returned for workshop {workshop_id}")

    return details_list[0]


def fetch_steam_airports(existing_icaos: set[str]) -> dict[str, dict]:
    """
    Step 1 - Fetch airports from Steam Workshop, keeping only NEWER
    workshop item for each ICAO (by time_updated).

    Returns:
      dict[icao] -> dict with metadata (no lat/lng yet)
    """
    steam_by_icao: dict[str, dict] = {}
    workshop_ids = fetch_workshop_ids_from_browse(max_pages=None)
    print(f"[INFO] Total workshop IDs fetched: {len(workshop_ids)}")

    for wid in workshop_ids:
        try:
            details = fetch_workshop_details(wid)
        except Exception as e:
            print(f"[ERROR] Steam details failed for {wid}: {e}")
            continue

        title = details.get("title") or ""
        creator = details.get("creator") or "Unknown"
        time_updated = details.get("time_updated") or 0

        icao = extract_icao_from_text(title)
        if not icao:
            print(f"[WARN] Could not parse ICAO from title '{title}', skipping.")
            continue
        icao = icao.upper()

        # If ICAO already in airports.json, we will skip it later,
        # but still track the newest workshop item for logging.
        current = steam_by_icao.get(icao)
        if current is None or time_updated > current["time_updated"]:
            workshop_url = (
                f"https://steamcommunity.com/sharedfiles/filedetails/?id={wid}"
            )
            steam_by_icao[icao] = {
                "icao": icao,
                "title": title,
                "creator": creator,
                "time_updated": time_updated,
                "workshop_url": workshop_url,
            }
            print(
                f"[INFO] Steam candidate {icao} updated to workshop {wid} "
                f"(time_updated={time_updated})."
            )

    # Filter out ICAOs already present in airports.json
    new_steam = {
        icao: info
        for icao, info in steam_by_icao.items()
        if icao not in existing_icaos
    }

    print(
        f"[INFO] Steam airports: {len(steam_by_icao)} ICAOs scraped, "
        f"{len(new_steam)} are new (not in airports.json)."
    )
    return new_steam


# --------------------------------------------------------------------
# Discord scraping
# --------------------------------------------------------------------

async def _fetch_discord_airports_async(channel_id: int) -> dict[str, dict]:
    """
    Fetch ICAOs from a Discord forum or text channel.

    For forum channels:
      - each thread (active + archived) is treated as one airport
      - ICAO is taken from thread name or starter message

    For simple text channels:
      - ICAO is taken from message content

    Returns:
      dict[icao] -> dict with minimal metadata
    """
    if discord is None:
        print("[INFO] discord.py is not installed, skipping Discord fetch.")
        return {}

    if not DISCORD_BOT_TOKEN:
        print("[INFO] DISCORD_BOT_TOKEN not set, skipping Discord fetch.")
        return {}

    intents = discord.Intents.default()
    # If you rely only on thread titles, this is not strictly required.
    # Enable in dev portal if you want message content as well.
    intents.message_content = True

    client = discord.Client(intents=intents)
    result: dict[str, dict] = {}

    async def handle_thread(thread: "discord.Thread") -> None:
        """Extract ICAO from a single thread (title, then starter message)."""
        icao = extract_icao_from_text(thread.name or "")

        if icao is None and intents.message_content:
            # fallback to starter message content if allowed
            try:
                starter = await thread.fetch_message(thread.id)
                icao = extract_icao_from_text(starter.content or "")
            except Exception:
                icao = None

        if not icao:
            return

        icao = icao.upper()

        if thread.guild is None:
            return

        url = f"https://discord.com/channels/{thread.guild.id}/{thread.id}"

        existing = result.get(icao)
        created_ts = int(thread.created_at.timestamp())
        if existing is None or created_ts > existing["created_ts"]:
            result[icao] = {
                "icao": icao,
                "source": "discord",
                "discord_thread": url,
                "author": str(getattr(thread, "owner", None) or "Unknown"),
                "created_ts": created_ts,
            }
            print(f"[INFO] Discord candidate {icao} from thread {thread.id}")

    @client.event
    async def on_ready():
        print(f"[INFO] Logged in as {client.user} (id={client.user.id})")

        ch = client.get_channel(channel_id)
        if ch is None:
            print(f"[ERROR] Cannot find channel with id {channel_id}.")
            await client.close()
            return

        print(f"[INFO] Discord channel: {ch} (type={type(ch)})")

        # Forum channel: active + archived threads
        if isinstance(ch, discord.ForumChannel):
            # Active threads
            threads = list(getattr(ch, "threads", []))
            print(f"[INFO] Forum active threads: {len(threads)}")
            for thread in threads:
                await handle_thread(thread)

            # Archived threads
            try:
                archived_count = 0
                async for thread in ch.archived_threads(limit=None):
                    archived_count += 1
                    await handle_thread(thread)
                print(f"[INFO] Forum archived threads processed: {archived_count}")
            except AttributeError:
                print("[WARN] ForumChannel.archived_threads not available on this discord.py version.")
        else:
            # Plain text channel: scan message history
            async for message in ch.history(limit=None, oldest_first=True):
                if message.author.bot:
                    continue
                if message.guild is None:
                    continue

                icao = extract_icao_from_text(message.content or "")
                if not icao:
                    continue

                icao = icao.upper()
                url = (
                    f"https://discord.com/channels/"
                    f"{message.guild.id}/{message.channel.id}/{message.id}"
                )
                created_ts = int(message.created_at.timestamp())
                existing = result.get(icao)
                if existing is None or created_ts > existing["created_ts"]:
                    result[icao] = {
                        "icao": icao,
                        "source": "discord",
                        "discord_thread": url,
                        "author": str(message.author),
                        "created_ts": created_ts,
                    }
                    print(
                        f"[INFO] Discord candidate {icao} from message {message.id}"
                    )

        print(f"[INFO] Discord airports scraped: {len(result)} ICAOs.")
        await client.close()

    await client.start(DISCORD_BOT_TOKEN)
    return result


def fetch_discord_airports(existing_icaos: set[str],
                           steam_icaos: set[str]) -> dict[str, dict]:
    """
    Step 2 - Fetch airports from Discord.

    Only airports that are:
      - not already in airports.json
      - not present in Steam results (Steam wins)
    are returned.

    Returns:
      dict[icao] -> dict with minimal Discord metadata
    """
    if not DISCORD_CHANNEL_ID:
        print("[INFO] DISCORD_CHANNEL_ID not set, skipping Discord fetch.")
        return {}

    try:
        channel_id = int(DISCORD_CHANNEL_ID)
    except ValueError:
        print(
            f"[ERROR] DISCORD_CHANNEL_ID={DISCORD_CHANNEL_ID} is not a valid int."
        )
        return {}

    if discord is None or not DISCORD_BOT_TOKEN:
        print("[INFO] Discord library or token missing, skipping Discord fetch.")
        return {}

    print(f"[INFO] Fetching airports from Discord channel {channel_id}...")
    discord_data = asyncio.run(_fetch_discord_airports_async(channel_id))

    # Filter out ICAOs that are already present in airports.json or in Steam
    filtered = {
        icao: info
        for icao, info in discord_data.items()
        if icao not in existing_icaos and icao not in steam_icaos
    }

    print(
        f"[INFO] Discord airports: {len(discord_data)} ICAOs scraped, "
        f"{len(filtered)} are new (not in airports.json or Steam)."
    )
    return filtered


def cache_path_for_icao(icao: str) -> Path:
    """Return the cache file path for a given ICAO."""
    icao = icao.upper()
    return CACHE_DIR / f"{icao}.json"


def load_cached_airport(icao: str) -> dict | None:
    """Load cached AeroDataBox response for an ICAO if present."""
    path = cache_path_for_icao(icao)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] Failed to read cache for {icao}: {e}")
        return None


def save_cached_airport(icao: str, data: dict) -> None:
    """Save AeroDataBox response for an ICAO to cache."""
    path = cache_path_for_icao(icao)
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Failed to write cache for {icao}: {e}")

# --------------------------------------------------------------------
# AeroDataBox lookup
# --------------------------------------------------------------------

def fetch_airport_from_aerodatabox(icao: str) -> dict:
    if not APIMARKET_API_KEY:
        raise RuntimeError(
            "APIMARKET_API_KEY is not set. Cannot call AeroDataBox."
        )

    # Try cache first
    cached = load_cached_airport(icao)
    if cached is not None:
        print(f"[INFO] Using cached AeroDataBox data for {icao}.")
        return cached

    url = f"{APIMARKET_BASE_URL}/airports/icao/{icao}?withRunways=false&withTime=false"
    headers = {
        "accept": "application/json",
        "x-api-market-key": APIMARKET_API_KEY,
    }

    print(f"[INFO] Calling AeroDataBox for {icao}...")
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    # Save to cache for future runs
    save_cached_airport(icao, data)

    return data


# --------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------

def main(run_steam=True, run_discord=True, use_aerodatabox=True):
    check_json_exists()
    """
    Master pipeline:

    1. Load airports.json, identify base and existing ICAOs.
    2. Fetch Steam airports (keep newest per ICAO).
    3. Fetch Discord airports (ICAOs not present in Steam or JSON).
    4. AeroDataBox lookup for new ICAOs only (Steam and Discord).
    5. Append new airports below base airports, with all non-base
       sorted alphabetically by ICAO.
    """
    (
        schema_version,
        base_airports,
        non_base_airports,
        existing_icaos,
    ) = load_airports_state()

    # Step 1 - Steam
    if run_steam == True:
        steam_new = fetch_steam_airports(existing_icaos)
        steam_icaos = set(steam_new.keys())
        print(f"Steam Scraped. Found {len(steam_icaos)} new ICAOs.")
    else:
        print("Steam Skipped.")
        steam_new = {}
        steam_icaos = set()

    # Step 2 - Discord (Steam wins on conflicts)
    if run_discord == True:
        discord_new = fetch_discord_airports(existing_icaos, steam_icaos)
        print(f"Discord Scraped. Found {len(discord_new)} new ICAOs.")
    else:
        print("Discord Skipped.")
        discord_new = {}
  
    # Step 3 - all new ICAOs that we need to call AeroDataBox for
    new_all: dict[str, dict] = {}
    for icao, info in steam_new.items():
        info = dict(info)
        info["source"] = "steam"
        new_all[icao] = info

    for icao, info in discord_new.items():
        info = dict(info)
        info["source"] = "discord"
        new_all[icao] = info

    print(
        f"[INFO] Total new ICAOs requiring AeroDataBox lookup: {len(new_all)}"
    )

    new_airports: list[dict] = []

    for icao, info in sorted(new_all.items(), key=lambda kv: kv[0]):
        if use_aerodatabox == False:
            print(
                f"[WARN] Skipping AeroDataBox for {icao} because "
                "use_aerodatabox=False."
            )
            continue

        try:
            adb = fetch_airport_from_aerodatabox(icao)
        except Exception as e:
            print(f"[ERROR] AeroDataBox failed for {icao}: {e}")
            continue

        full_name = (
            adb.get("fullName")
            or adb.get("name")
        )
        short_name = adb.get("shortName")
        municipality = adb.get("municipalityName")
        name = full_name or short_name or municipality or f"{icao} Airport"
        if "airport" not in name.lower():
            name = f"{name} Airport"

        location = adb.get("location") or {}
        lat = location.get("lat")
        lng = location.get("lon") or location.get("lng")
        if lat is None or lng is None:
            print(f"[WARN] No lat/lng from AeroDataBox for {icao}, skipping.")
            continue

        now_iso = datetime.now(timezone.utc).isoformat()

        if info["source"] == "steam":
            status = "released"
            author = info.get("creator", "Unknown")
            workshop_url = info.get("workshop_url")
            discord_thread = None
            last_updated = to_iso_timestamp(info.get("time_updated")) or now_iso
        else:
            status = "in_dev"
            author = info.get("author", "Unknown")
            workshop_url = None
            discord_thread = info.get("discord_thread")
            last_updated = now_iso

        airport_entry = {
            "icao": icao,
            "name": name,
            "lat": float(lat),
            "lng": float(lng),
            "status": status,
            "source": info["source"],
            "author": author,
            "workshopUrl": workshop_url,
            "discordThread": discord_thread,
            "lastUpdated": last_updated,
            "defaultIncluded": False,
            "featured": False,
        }

        new_airports.append(airport_entry)
        existing_icaos.add(icao)
        print(
            f"[INFO] Added new {info['source']} airport: {icao} - {name}"
        )

        # Protect API rate limits a bit
        time.sleep(0.5)

    # Step 4 - merge and sort non-base airports
    combined_non_base = non_base_airports + new_airports
    combined_non_base.sort(
        key=lambda a: (a.get("icao") or "").upper()
    )

    merged_airports = base_airports + combined_non_base

    now_iso = datetime.now(timezone.utc).isoformat()
    updated_data = {
        "schemaVersion": schema_version,
        "lastUpdated": now_iso,
        "airports": merged_airports,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_json(AIRPORTS_PATH, updated_data)

    print(
        f"[INFO] Updated {AIRPORTS_PATH} with {len(merged_airports)} airports. "
        f"lastUpdated={now_iso}"
    )

     # Cleanup pycache
    pycache_dir = ROOT / "scripts" / "__pycache__"
    if pycache_dir.exists() and pycache_dir.is_dir():
        try:
            shutil.rmtree(pycache_dir)
            print(f"[INFO] Removed {pycache_dir}")
        except Exception as e:
            print(f"[WARN] Failed to remove {pycache_dir}: {e}")


if "--dry-detect" in sys.argv:
    check_json_exists()
    schema_version, base_airports, non_base_airports, existing_icaos = load_airports_state()
    steam_new = fetch_steam_airports(existing_icaos)
    discord_new = fetch_discord_airports(existing_icaos, set(steam_new.keys()))
    new_count = len(steam_new) + len(discord_new)
    print(f"Dry-detect new ICAOs: {new_count}")
    for source, icaos in (("STEAM", steam_new), ("DISCORD", discord_new)):
        for icao in sorted(icaos.keys()):
            print(f" - [{source}] {icao}")
    sys.exit(0)

if __name__ == "__main__":
    main(use_aerodatabox=True)
