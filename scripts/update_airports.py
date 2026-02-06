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

ICAO_EXLUSIONS = {
    "WANT", "TEST", "DEMO", "SAMPLE", "EXAMPLE", "DUMMY", "FAKE", "WITH", "REAL"
}


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
        subscriptions = int(details.get("subscriptions") or 0)

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
                "subscriptions": subscriptions
            }
            print(
                f"[INFO] Steam candidate {icao} updated to workshop {wid} "
                f"(time_updated={time_updated})."
            )

    # Filter out ICAOs already present in airports.json
    steam_all = steam_by_icao

    steam_new = {
        icao: info
        for icao, info in steam_by_icao.items()
        if icao not in existing_icaos
    }

    print(
        f"[INFO] Steam airports: {len(steam_all)} ICAOs scraped, "
        f"{len(steam_new)} are new (not in airports.json)."
    )
    return steam_all, steam_new



# --------------------------------------------------------------------
# Discord scraping
# --------------------------------------------------------------------

async def _fetch_discord_airports_async(channel_id: int) -> dict[str, dict]:
    """
    Scrape ICAO codes from a Discord forum/text channel's threads.

    Returns:
      { "KJFK": {"icao":"KJFK","source":"discord","discord_thread":url,"author":name,"updated_ts":int_ts}, ... }

    Key robustness features:
      - Uses thread.last_message_id first (fast) to get last activity timestamp
      - Falls back to history(limit=1) with a hard timeout
      - Starter message fetch is optional and timeout-protected
      - Concurrency limited to avoid rate limit stalls
      - Supports forum channels (active + archived threads)
    """
    if discord is None:
        raise RuntimeError("discord.py is not available")

    # Optional: define this at module level instead
    DISCORD_ICAO_EXCLUDE = {
        "WANT",
    }

    result: dict[str, dict] = {}

    # Tune these if you have lots of threads
    CONCURRENCY = 8
    FETCH_TIMEOUT_S = 8

    sem = asyncio.Semaphore(CONCURRENCY)

    intents = discord.Intents.default()
    # Only enable if you actually need to parse starter message content
    # (still works without it via thread titles)
    intents.message_content = True

    done = asyncio.Event()

    def _thread_url(thread: "discord.Thread") -> str:
        g = thread.guild
        if g is None:
            return ""
        return f"https://discord.com/channels/{g.id}/{thread.id}"

    async def _safe_wait_for(coro, timeout_s: int = FETCH_TIMEOUT_S):
        try:
            return await asyncio.wait_for(coro, timeout=timeout_s)
        except Exception:
            return None

    async def _fetch_starter_message(thread: "discord.Thread"):
        # Starter message id for forum threads is the thread id
        return await _safe_wait_for(thread.fetch_message(thread.id))

    async def _fetch_last_message_ts(thread: "discord.Thread") -> int:
        # 1) Fast path: last_message_id -> fetch that message
        try:
            if getattr(thread, "last_message_id", None):
                msg = await _safe_wait_for(thread.fetch_message(thread.last_message_id))
                if msg is not None and getattr(msg, "created_at", None):
                    return int(msg.created_at.timestamp())
        except Exception:
            pass

        # 2) Fallback: history(limit=1) with a hard timeout
        async def _get_hist_ts():
            async for msg in thread.history(limit=1, oldest_first=False):
                if getattr(msg, "created_at", None):
                    return int(msg.created_at.timestamp())
            return None

        ts = await _safe_wait_for(_get_hist_ts())
        if isinstance(ts, int):
            return ts

        # 3) Last resort: thread.created_at
        try:
            if getattr(thread, "created_at", None):
                return int(thread.created_at.timestamp())
        except Exception:
            pass

        return 0

    async def _process_thread(thread: "discord.Thread") -> None:
        async with sem:
            try:
                # 1) Try title first
                icao = extract_icao_from_text(thread.name or "")
                starter = None

                # 2) Fallback to starter message content
                if not icao and intents.message_content:
                    starter = await _fetch_starter_message(thread)
                    if starter is not None:
                        icao = extract_icao_from_text(getattr(starter, "content", "") or "")

                if not icao:
                    return

                icao = icao.upper()
                if icao in DISCORD_ICAO_EXCLUDE:
                    return

                if thread.guild is None:
                    return

                # Author name preference: thread.owner -> starter.author -> Unknown
                author_name = "Unknown"
                owner = getattr(thread, "owner", None)
                if owner is not None and getattr(owner, "name", None):
                    author_name = owner.name
                else:
                    if starter is None and intents.message_content:
                        starter = await _fetch_starter_message(thread)
                    if starter is not None and getattr(starter, "author", None) is not None:
                        author_name = getattr(starter.author, "name", None) or str(starter.author)

                updated_ts = await _fetch_last_message_ts(thread)

                existing = result.get(icao)
                if existing is None or updated_ts > existing.get("updated_ts", 0):
                    result[icao] = {
                        "icao": icao,
                        "source": "discord",
                        "discord_thread": _thread_url(thread),
                        "author": author_name,
                        "updated_ts": updated_ts,
                    }

            except Exception:
                # Swallow per-thread errors so one bad thread doesn't stall the whole scrape
                return

    async def _gather_threads(channel) -> list["discord.Thread"]:
        threads: list["discord.Thread"] = []

        # Forum channel: has active threads in .threads, archived via .archived_threads()
        if hasattr(channel, "threads"):
            try:
                threads.extend(list(channel.threads))
            except Exception:
                pass

            # Archived threads (public)
            try:
                archived_iter = channel.archived_threads(limit=None)
                async for th in archived_iter:
                    threads.append(th)
            except Exception:
                pass

            return threads

        # Text channel: try active threads if present
        if hasattr(channel, "active_threads"):
            try:
                ths = await channel.active_threads()
                if isinstance(ths, (list, tuple)):
                    threads.extend(ths)
            except Exception:
                pass

        return threads

    class _Client(discord.Client):
        async def on_ready(self):
            try:
                channel = self.get_channel(channel_id)
                if channel is None:
                    channel = await self.fetch_channel(channel_id)

                threads = await _gather_threads(channel)

                # Process threads with concurrency limit
                tasks = [asyncio.create_task(_process_thread(th)) for th in threads]
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

            finally:
                done.set()
                await self.close()

    client = _Client(intents=intents)

    # Run client until scrape completes
    await client.start(DISCORD_BOT_TOKEN)
    await done.wait()

    return result


def fetch_discord_airports(existing_icaos: set[str],
                           steam_icaos: set[str]) -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Returns (discord_all, discord_new)

    discord_new is filtered to:
      - not already in airports.json
      - not present in Steam results (Steam wins)
    """
    if not DISCORD_CHANNEL_ID:
        print("[INFO] DISCORD_CHANNEL_ID not set, skipping Discord fetch.")
        return {}, {}

    try:
        channel_id = int(DISCORD_CHANNEL_ID)
    except ValueError:
        print(f"[ERROR] DISCORD_CHANNEL_ID={DISCORD_CHANNEL_ID} is not a valid int.")
        return {}, {}

    if discord is None or not DISCORD_BOT_TOKEN:
        print("[INFO] Discord library or token missing, skipping Discord fetch.")
        return {}, {}

    print(f"[INFO] Fetching airports from Discord channel {channel_id}...")
    discord_all = asyncio.run(_fetch_discord_airports_async(channel_id))

    discord_new = {
        icao: info
        for icao, info in discord_all.items()
        if icao not in existing_icaos and icao not in steam_icaos
    }

    print(
        f"[INFO] Discord airports: {len(discord_all)} ICAOs scraped, "
        f"{len(discord_new)} are new (not in airports.json or Steam)."
    )
    return discord_all, discord_new



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
        steam_all, steam_new = fetch_steam_airports(existing_icaos)
        steam_icaos = set(steam_new.keys())
        print(f"Steam Scraped. Found {len(steam_icaos)} new ICAOs.")
    else:
        print("Steam Skipped.")
        steam_new = {}
        steam_icaos = set()

    # Step 2 - Discord (Steam wins on conflicts)
    if run_discord == True:
        discord_all, discord_new = fetch_discord_airports(existing_icaos, steam_icaos)
        print(f"Discord Scraped. Found {len(discord_new)} new ICAOs.")
    else:
        print("Discord Skipped.")
        discord_new = {}
        discord_all = {}

    # Update existing Discord airports' lastUpdated based on latest thread activity
    if run_discord:
        updated_existing = 0

        for a in non_base_airports:
            if a.get("source") == "discord" and a.get("icao"):
                icao = a["icao"].upper()
                info = discord_all.get(icao)

                if info and info.get("updated_ts"):
                    new_iso = to_iso_timestamp(info["updated_ts"])
                    if new_iso and new_iso != a.get("lastUpdated"):
                        a["lastUpdated"] = new_iso
                        updated_existing += 1

        if updated_existing:
            print(f"[INFO] Updated lastUpdated for {updated_existing} existing Discord airports.")
  
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

        country = adb.get("country") or {}
        continent = adb.get("continent") or {}

        country_code = country.get("code")
        country_name = country.get("name")
        continent_code = continent.get("code")
        continent_name = continent.get("name")

        now_iso = datetime.now(timezone.utc).isoformat()

        if info["source"] == "steam":
            status = "released"
            author = info.get("creator", "Unknown")
            workshop_url = info.get("workshop_url")
            discord_thread = None
            last_updated = to_iso_timestamp(info.get("time_updated")) or now_iso
            subscriptions = int(info.get("subscriptions") or 0)
        else:
            status = "in_dev"
            author = info.get("author", "Unknown")
            workshop_url = None
            discord_thread = info.get("discord_thread")
            last_updated = to_iso_timestamp(info.get("updated_ts")) or now_iso
            subscriptions = 0

        airport_entry = {
            "icao": icao,
            "name": name,
            "lat": float(lat),
            "lng": float(lng),
            "country": {"code": country_code, "name": country_name},
            "continent": {"code": continent_code, "name": continent_name},
            "status": status,
            "source": info["source"],
            "author": author,
            "workshopUrl": workshop_url,
            "discordThread": discord_thread,
            "lastUpdated": last_updated,
            "defaultIncluded": False,
            "featured": False,
            "steamSubscriptions": subscriptions,
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

    steam_all, steam_new = fetch_steam_airports(existing_icaos)
    discord_all, discord_new = fetch_discord_airports(existing_icaos, set(steam_new.keys()))

    new_count = len(steam_new) + len(discord_new)
    print(f"Dry-detect new ICAOs: {new_count}")

    for source, icaos in (("STEAM", steam_new), ("DISCORD", discord_new)):
        for icao in sorted(icaos.keys()):
            print(f" - [{source}] {icao}")

    sys.exit(0)

if __name__ == "__main__":
    main(use_aerodatabox=True)
