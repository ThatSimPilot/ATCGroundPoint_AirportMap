// main.js

const STATUS_COLORS = {
  base: "#a0aec0",
  in_dev: "#f6ad55",
  released: "#48bb78"
};

let allAirports = [];
let filteredAirports = [];
let globeInstance = null;

const FILTERS_STORAGE_KEY = "atcgp_filters_v1";

async function loadAirports() {
  try {
    const res = await fetch("data/airports.json");
    if (!res.ok) {
      console.error("Failed to load airports.json", res.status, res.statusText);
      return [];
    }
    return await res.json();
  } catch (err) {
    console.error("Error fetching airports.json:", err);
    // Optional: tiny fallback so you see *something*
    return [
      {
        icao: "YBBN",
        name: "Brisbane Airport",
        lat: -27.3842,
        lng: 153.1175,
        status: "released"
      }
    ];
  }
}

function statusLabel(status) {
  if (status === "base") return "Base";
  if (status === "in_dev") return "In development";
  if (status === "released") return "Released";
  return status || "Unknown";
}

function createGlobe(airports) {
  const container = document.getElementById("globe");
  if (!container) {
    console.error("#globe container not found");
    return;
  }

  globeInstance = new Globe(container, {
    animateIn: true
  })
    .globeImageUrl("//unpkg.com/three-globe/example/img/earth-dark.jpg")
    .backgroundColor("#020617")
    .pointOfView({ lat: 0, lng: 140, altitude: 2.5 })
    .pointsData(airports)
    .pointLat(d => d.lat)
    .pointLng(d => d.lng)
    .pointColor(d => STATUS_COLORS[d.status] || "#e5e7eb")
    .pointAltitude(() => 0.015)
    .pointRadius(() => 0.18)
    .pointLabel(d => {
      let line1 = `${d.icao || "N/A"} – ${d.name || "Unknown"}`;
      let line2 = `Status: ${statusLabel(d.status)}`;
      return `${line1}<br/>${line2}`;
    })
    .onGlobeReady(() => {
      const controls = globeInstance.controls();
      controls.autoRotate = true;
      controls.autoRotateSpeed = 0.5;
    });

  // 🔹 Sync globe size with the Bootstrap layout
  function resizeGlobeToContainer() {
    const width = container.clientWidth;
    const height = container.clientHeight;
    if (!width || !height) return;

    globeInstance.width(width);
    globeInstance.height(height);
  }

  // Initial sizing
  resizeGlobeToContainer();

  // Update when the flex layout / container size changes
  const ro = new ResizeObserver(resizeGlobeToContainer);
  ro.observe(container);
}

function updateGlobePoints(airports) {
  if (!globeInstance) return;

  globeInstance
    .pointsData(airports)
    .pointLat(d => d.lat)
    .pointLng(d => d.lng)
    .pointColor(d => STATUS_COLORS[d.status] || "#e5e7eb");
}

function renderAirportList(airports) {
  const listEl = document.getElementById("airport-list");
  if (!listEl) return;

  listEl.innerHTML = "";

  airports
    .slice()
    .sort((a, b) => (a.icao || "").localeCompare(b.icao || ""))
    .forEach(a => {
      const li = document.createElement("li");
      li.className = "airport-item";

      const left = document.createElement("div");
      const title = document.createElement("div");
      title.textContent = `${a.icao || "N/A"} – ${a.name || "Unknown"}`;

      const meta = document.createElement("div");
      meta.className = "airport-meta";
      meta.textContent = `${a.lat.toFixed(2)}, ${a.lng.toFixed(2)}`;

      left.appendChild(title);
      left.appendChild(meta);

      const pill = document.createElement("span");
      pill.className = `status-pill status-${a.status}`;
      pill.textContent = statusLabel(a.status);

      li.appendChild(left);
      li.appendChild(pill);

      li.addEventListener("click", () => focusOnAirport(a));

      listEl.appendChild(li);
    });
}

function focusOnAirport(airport) {
  if (!globeInstance) return;

  globeInstance.pointOfView(
    { lat: airport.lat, lng: airport.lng, altitude: 1.5 },
    1000
  );

  const controls = globeInstance.controls();
  const previousAutoRotate = controls.autoRotate;
  controls.autoRotate = false;
  setTimeout(() => {
    controls.autoRotate = previousAutoRotate;
  }, 5000);

  const link = airport.workshopUrl || airport.discordThread;
  if (link && confirm("Open airport page in a new tab?")) {
    window.open(link, "_blank");
  }
}

/* ---------- LocalStorage helpers ---------- */

function loadFilterState() {
  try {
    const raw = localStorage.getItem(FILTERS_STORAGE_KEY);
    if (!raw) return;

    const data = JSON.parse(raw);

    const filterBase = document.getElementById("filter-base");
    const filterInDev = document.getElementById("filter-in-dev");
    const filterReleased = document.getElementById("filter-released");
    const searchInput = document.getElementById("search");

    if (filterBase && typeof data.base === "boolean") {
      filterBase.checked = data.base;
    }
    if (filterInDev && typeof data.inDev === "boolean") {
      filterInDev.checked = data.inDev;
    }
    if (filterReleased && typeof data.released === "boolean") {
      filterReleased.checked = data.released;
    }
    if (searchInput && typeof data.search === "string") {
      searchInput.value = data.search;
    }
  } catch (e) {
    console.warn("Could not load filter state from localStorage:", e);
  }
}

function saveFilterState() {
  try {
    const filterBase = document.getElementById("filter-base");
    const filterInDev = document.getElementById("filter-in-dev");
    const filterReleased = document.getElementById("filter-released");
    const searchInput = document.getElementById("search");

    const data = {
      base: filterBase ? filterBase.checked : true,
      inDev: filterInDev ? filterInDev.checked : true,
      released: filterReleased ? filterReleased.checked : true,
      search: searchInput ? searchInput.value : ""
    };

    localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(data));
  } catch (e) {
    console.warn("Could not save filter state to localStorage:", e);
  }
}

/* ---------- Filtering ---------- */

function applyFilters() {
  const filterBase = document.getElementById("filter-base");
  const filterInDev = document.getElementById("filter-in-dev");
  const filterReleased = document.getElementById("filter-released");
  const searchInput = document.getElementById("search");

  const showBase = filterBase ? filterBase.checked : true;
  const showInDev = filterInDev ? filterInDev.checked : true;
  const showReleased = filterReleased ? filterReleased.checked : true;
  const searchValue = (searchInput ? searchInput.value : "")
    .trim()
    .toLowerCase();

  filteredAirports = allAirports.filter(a => {
    if (a.status === "base" && !showBase) return false;
    if (a.status === "in_dev" && !showInDev) return false;
    if (a.status === "released" && !showReleased) return false;

    if (searchValue) {
      const text = `${a.icao || ""} ${a.name || ""}`.toLowerCase();
      if (!text.includes(searchValue)) return false;
    }

    return true;
  });

  updateGlobePoints(filteredAirports);
  renderAirportList(filteredAirports);

  // Persist current settings
  saveFilterState();
}

/* ---------- Init ---------- */

async function init() {
  allAirports = await loadAirports();
  filteredAirports = allAirports.slice();

  createGlobe(allAirports);
  renderAirportList(allAirports);

  // Restore saved filters & search before wiring listeners
  loadFilterState();

  const filterBase = document.getElementById("filter-base");
  const filterInDev = document.getElementById("filter-in-dev");
  const filterReleased = document.getElementById("filter-released");
  const searchInput = document.getElementById("search");

  filterBase && filterBase.addEventListener("change", applyFilters);
  filterInDev && filterInDev.addEventListener("change", applyFilters);
  filterReleased &&
    filterReleased.addEventListener("change", applyFilters);
  searchInput && searchInput.addEventListener("input", applyFilters);

  // Apply filters once with restored state
  applyFilters();
}

// Single load handler
window.addEventListener("load", init);
