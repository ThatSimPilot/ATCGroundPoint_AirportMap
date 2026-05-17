# ATC Ground Point Airport Map — Project Migration Summary

## Project Overview

This project is a web-based interactive 3D globe and airport tracking system for the game/community project **ATC Ground Point**.

It visualizes airports on a globe and categorizes them into:

* `base`
* `in_dev`
* `released`

The site supports:

* Interactive globe navigation
* Airport filtering/searching
* Steam Workshop integration
* Discord integration
* Automatic airport database generation
* Clustered globe rendering at high zoom levels
* Persistent user filters via localStorage

The stack is intentionally lightweight:

* Vanilla JavaScript
* HTML/CSS
* Bootstrap
* Globe.gl
* Static JSON database
* Python ingestion/update scripts

---

# Core Architecture

## Frontend Files

### `index.html`

Main application shell.

Contains:

* Header
* Sidebar filters
* Airport list
* Globe container
* Airport detail overlay
* Footer
* BuyMeACoffee widget
* Bootstrap + Globe.gl CDN imports

Important DOM IDs:

* `#globe`
* `#airport-list`
* `#airport-details`
* `#search`
* `#sort-by`
* `#sort-dir`
* `#filter-steam-only`
* `#filter-in-view`
* `#filter-continent`
* `#filter-country`

---

### `main.js`

Main application logic.

Responsible for:

* Loading airport data
* Rendering globe
* Clustering
* Filtering
* Sorting
* Search
* LocalStorage persistence
* Airport selection
* Camera movement
* Header rotation text
* Footer timestamps
* Globe resize handling
* Auto-rotation controls

This is the primary frontend logic file.

---

### `style.css`

Custom dark theme styling.

Key areas:

* Sidebar layout
* Globe layout
* Responsive sizing
* Filter chips
* Airport cards
* Overlay cards
* Header/footer styling
* Dark theme polish

The UI is heavily refined and intentionally modern/dense.

---

# Data Model

## Main Dataset Structure

The frontend loads:

```js
fetch("data/airports.json")
```

Expected schema:

```json
{
  "schemaVersion": 1,
  "lastUpdated": "ISO_TIMESTAMP",
  "airports": []
}
```

---

## Airport Object Schema

Example:

```json
{
  "icao": "YMML",
  "name": "Melbourne Airport",
  "lat": -37.6733,
  "lng": 144.8433,

  "status": "base",

  "source": "manual",

  "author": "Blueon",

  "workshopUrl": null,
  "discordThread": null,

  "lastUpdated": "2026-01-13T00:00:00Z",

  "defaultIncluded": true
}
```

---

# Airport Status Meanings

## `base`

Core/default airports.

Characteristics:

* Included by default
* Usually manually curated
* Stored in `baseAirports.json`

Color:

* Gray (`#a0aec0`)

---

## `in_dev`

Airport currently under development.

Usually sourced from:

* Discord
* Developer announcements

Color:

* Orange (`#f6ad55`)

---

## `released`

Released airports.

Usually sourced from:

* Steam Workshop

Color:

* Green (`#48bb78`)

---

# Backend / Data Ingestion System

## Central Orchestrator

### `update_airports.py`

This is the central backend pipeline.

It:

* Loads existing airports
* Merges multiple sources
* Updates metadata
* Writes final `airports.json`

This is the primary backend script.

---

# Wrapper Scripts

## Steam-only updater

### `update_airports_from_steam.py`

Wrapper:

```python
main(run_steam=True, run_discord=False, use_aerodatabox=True)
```

Purpose:

* Run Steam ingestion only

Used for:

* GitHub Actions
* Standalone refreshes

---

## Discord-only updater

### `update_airports_from_discord.py`

Wrapper:

```python
main(run_steam=False, run_discord=True, use_aerodatabox=True)
```

Purpose:

* Run Discord ingestion only

---

## Test mode (no AeroDataBox)

### `update_airports_test_no_API.py`

Wrapper:

```python
main(run_steam=True, run_discord=True, use_aerodatabox=False)
```

Purpose:

* Avoid AeroDataBox API usage
* Testing/dev mode

---

# Source Systems

## 1. Base Airports

Stored in:

* `baseAirports.json`

Manually curated airport seed database.

These airports:

* Always exist
* Are trusted
* Are default included

Fields:

* ICAO
* Coordinates
* Status
* Author
* Metadata

---

## 2. Steam Workshop

Used for:

* Released airports
* Subscription counts
* Workshop links
* Last update timestamps

Expected fields added to airports:

* `steamSubscriptions`
* `workshopUrl`
* `lastUpdated`

Steam airports are identified frontend-side using:

```js
a.source === "steam" || !!a.workshopUrl
```

---

## 3. Discord

Used for:

* In-development airports
* Dev thread links
* Early projects

Expected field:

* `discordThread`

---

## 4. AeroDataBox (Optional)

Used for:

* Airport metadata enrichment
* Country
* Continent
* Coordinates validation

Can be disabled.

---

# Frontend Functional Systems

# Globe System

Uses:

* Globe.gl
* Three.js internally

Features:

* Auto-rotate
* Smooth camera movement
* Marker selection
* Dynamic clustering
* Hover labels
* Click-to-focus

---

# Clustering System

Uses:

* H3 spatial clustering

Dynamic resolution based on zoom altitude.

Important constants:

```js
const CLUSTER_ALTITUDE_ON = 1.55;
const CLUSTER_ALTITUDE_OFF = 1.35;
```

Behavior:

* High altitude → clusters enabled
* Low altitude → individual markers

Clusters:

* Aggregate airport counts
* Show dominant status color
* Click to zoom further in

---

# Filtering System

Filter state persisted in:

```js
localStorage["atcgp_filters_v1"]
```

Default state:

```js
{
  statuses: {
    base: true,
    in_dev: true,
    released: true
  },

  steamOnly: false,
  inView: false,
  continent: "",
  country: "",

  search: "",

  sortBy: "icao",
  sortDir: "down"
}
```

---

# Sorting

Supported sorts:

* ICAO
* Airport name
* Steam subscriptions
* Last updated

Special directional logic exists:

```js
DOWN_MEANS
```

This maps:

* Down arrow
* Asc/desc meaning
* Context-aware sorting

---

# In-View Filtering

Filter:

* Only airports currently visible in globe viewport

Expensive operation.

Automatically re-applies during zoom changes.

---

# Search System

Searches:

* ICAO
* Airport name

Case-insensitive substring search.

---

# Airport Details Overlay

Displays:

* ICAO
* Name
* Status
* Coordinates
* External link

External link priority:

1. Steam workshop
2. Discord thread

---

# Header Rotation System

The header subheading alternates every:

```js
HEADER_ROTATE_MS = 5000
```

Between:

* Static description
* Dynamic filter summary

Animated fade transitions.

---

# Footer Timestamp System

Shows:

* Relative timestamp
* Local timestamp on hover

Includes:

* Timezone-aware formatting
* Australian locale handling

---

# UI / UX Design Goals

The UI is intentionally:

* Dense
* Modern
* Dark-themed
* Dashboard-like
* Smoothly animated
* Minimal scrolling

Key design goals:

* No page scroll
* Globe fills available space
* Sidebar fixed width
* Responsive resizing
* Dense information display

---

# Current Frontend Libraries

## Included via CDN

### Bootstrap

Version:

* 5.3.x

### Bootstrap Icons

### Globe.gl

### H3

Likely loaded elsewhere in truncated code.

---

# Important Functions in `main.js`

## Data

* `loadAirports()`

---

## Globe

* `createGlobe()`
* `updateGlobePoints()`
* `focusOnAirport()`

---

## Clustering

* `buildClusters()`
* `refreshMarkersForCurrentMode()`
* `updateClusterModeForAltitude()`

---

## Filtering

* `applyFilters()`
* `sortAirports()`
* `syncFilterUiFromState()`

---

## UI

* `renderAirportList()`
* `showAirportDetails()`
* `updateHeaderSubheading()`

---

## Persistence

* `loadFilterState()`
* `saveFilterState()`

---

# Deployment Model

Appears intended for:

* Static hosting
* GitHub Pages or similar

Frontend is fully static.

Backend scripts generate:

* `data/airports.json`

Typical pipeline:

1. Run Python updater(s)
2. Generate airport database
3. Commit/publish JSON
4. Frontend auto-loads latest data

---

# Current Technical Direction

The project is evolving toward:

## A live community airport ecosystem map

Potential future directions implied by architecture:

* More metadata enrichment
* Better clustering
* Real-time updates
* More source integrations
* User submissions
* Region analytics
* Airport popularity metrics

---

# Known Design Decisions

## Intentional Choices

### Vanilla JS over frameworks

Chosen for:

* Simplicity
* Lightweight deployment
* Easy hosting
* Performance

---

### Static JSON datastore

Chosen for:

* GitHub Pages compatibility
* No backend hosting
* Simplicity

---

### Globe-first UI

The globe is the centerpiece.

Sidebar is secondary navigation.

---

# Key Missing Context (Not Visible in Uploaded Snippets)

The following likely exist in truncated sections or external systems:

* Full `update_airports.py`
* Steam scraping logic
* Discord scraping/parsing
* AeroDataBox integration details
* H3 script loading
* Country/continent population logic
* `isAirportInCurrentView()`
* Exact deployment pipeline
* GitHub Actions workflows

---

# Critical Migration Notes for Another LLM

## The most important files are:

1. `main.js`
2. `update_airports.py`
3. `airports.json`
4. `baseAirports.json`

---

## Core mental model

This is NOT:

* A flight simulator
* A nav system
* A game engine

It IS:

* A community airport project tracker
* A visualization/map application
* A static-data-driven globe UI

---

## Main architectural split

### Backend

Python ingestion pipeline:

* Steam
* Discord
* Base airports
* Metadata enrichment

Outputs:

* Unified JSON database

### Frontend

Static JS app:

* Visualizes JSON
* Provides filtering/search
* Globe interaction

---

# Recommended Immediate Actions for New LLM

1. Fully inspect `update_airports.py`
2. Inspect complete `main.js`
3. Identify deployment structure
4. Identify JSON output location
5. Verify H3 loading/import
6. Map complete airport schema
7. Determine Steam scraping method
8. Determine Discord ingestion method
9. Determine how continent/country metadata is populated
