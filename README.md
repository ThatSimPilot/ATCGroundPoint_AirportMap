# ATC Ground Point – Airport Globe Viewer

An interactive 3D globe visualizing airports that support **ATC Ground Point** with status, metadata, clickable UI, filtering, search, and workshop/discord links.  
Runs as a static website using **globe.gl**, **Bootstrap**, and a JSON data store.  
Published via GitHub Pages.
https://thatsimpilot.github.io/ATCGroundPoint_AirportMap/

<a href="https://www.buymeacoffee.com/thatsimpilot" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

---

## ✈ Purpose

The goal of this project is to provide a simple and visually intuitive way to:

- See which airports currently support ATC Ground Point
- Track airports under development or base-supported
- View metadata including status, author, and availability
- Filter and search airports by ICAO, status, or name
- Access workshop and Discord links directly from the UI

The site works offline and requires no backend.

---

## 🗂 Data Format

Airport data is stored in `data/airports.json` and fetched at runtime.

Top-level structure:

```json
{
  "schemaVersion": 1,
  "lastUpdated": "YYYY-MM-DDTHH:mm:ssZ",
  "airports": [ ... ]
}
Each airport includes:
{
  "icao": "XXXX",
  "name": "Full Airport Name",
  "lat": 0,
  "lng": 0,
  "status": "base | in_dev | released",
  "author": "AuthorName",
  "source": "manual | steam | discord",
  "workshopUrl": "...",
  "discordThread": "...",
  "defaultIncluded": true,
  "lastUpdated": "YYYY-MM-DDTHH:mm:ssZ"
}
```
This structure is designed for future automation via Steam/Discord ingestion.

## 🧩 Features
- 3D interactive globe
- Dark UI with sidebar layout
- Hover tooltips
- Click to focus + display details
- Auto-rotating globe (with pause/resume behavior)
- Status-based filtering
- ICAO + Name search
- LocalStorage persistence for filters/search
- Responsive layout

## 🛠 Tech Stack
- HTML/CSS/JavaScript
- Bootstrap 5.3
- globe.gl (three.js)
- LocalStorage
- Static JSON data
- GitHub Pages

## 🚀 Deployment
This project is served via GitHub Pages.

## 📦 Future Roadmap
Planned enhancements:
- Contributor/author attribution
- Region/country filtering
- Status evolution history
- Global stats
- Additional UI polish

