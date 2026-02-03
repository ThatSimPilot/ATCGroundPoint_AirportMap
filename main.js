// main.js

const STATUS_COLORS = {
  base: "#a0aec0",
  in_dev: "#f6ad55",
  released: "#48bb78"
};

let allAirports = [];
let filteredAirports = [];
let globeInstance = null;
let globeResizeObserver = null;
let selectedAirportIcao = null;

const FILTERS_STORAGE_KEY = "atcgp_filters_v1";

// Auto-rotate / interaction pause state
let orbitControls = null;
let autoRotateTimeoutId = null;

// ---------- Data loading ----------

async function loadAirports() {
  try {
    const res = await fetch("data/airports.json", {
      cache: "no-store" // optional but useful to avoid stale browser caching
    });

    if (!res.ok) {
      console.error("Failed to load airports.json", res.status, res.statusText);
      return {
        schemaVersion: 1,
        lastUpdated: null,
        airports: [
          {
            icao: "ERROR",
            name: "Error Loading Airports",
            lat: 0,
            lng: 0,
            status: "unknown",
            defaultIncluded: true
          }
        ]
      };
    }

    const data = await res.json();

    // Defensive normalization:
    const schemaVersion = data.schemaVersion || 1;
    const lastUpdated = data.lastUpdated || null;
    const airports = Array.isArray(data.airports) ? data.airports : [];

    return {
      schemaVersion,
      lastUpdated,
      airports
    };

  } catch (err) {
    console.error("Error fetching airports.json:", err);

    // Same fallback but wrapped in the new structure
    return {
      schemaVersion: 1,
      lastUpdated: null,
      airports: [
        {
          icao: "ERROR",
          name: "Error Loading Airports",
          lat: 0,
          lng: 0,
          status: "unknown",
          defaultIncluded: true
        }
      ]
    };
  }
}

function statusLabel(status) {
  if (status === "base") return "Base";
  if (status === "in_dev") return "In development";
  if (status === "released") return "Released";
  return status || "Unknown";
}

function normalizeIsoTimestamp(value) {
  if (!value) return null;
  const text = String(value).trim();
  const match = text.match(/^(.+?)(\.\d+)?(Z|[+-]\d{2}:\d{2})$/);
  if (!match) return text;
  const base = match[1];
  let fraction = match[2] || "";
  const tz = match[3];

  if (fraction.length > 4) {
    fraction = fraction.slice(0, 4);
  }

  return `${base}${fraction}${tz}`;
}

function formatDatabaseUpdated(value) {
  if (!value) return "Unknown";
  const normalized = normalizeIsoTimestamp(value);
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return String(value);
  return formatWithDayPeriodUpper(date, undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short"
  });
}

function formatDatabaseUpdatedLocal(value) {
  if (!value) return "Unknown";
  const normalized = normalizeIsoTimestamp(value);
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return "Unknown";
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const useEnAu = typeof timeZone === "string" && timeZone.startsWith("Australia/");
  const locale = useEnAu ? "en-AU" : undefined;

  return formatWithDayPeriodUpper(date, locale, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short"
  });
}

function formatWithDayPeriodUpper(date, locale, options) {
  const formatter = new Intl.DateTimeFormat(locale, options);
  const parts = formatter.formatToParts(date);
  const tokens = new Map();

  for (const part of parts) {
    if (!tokens.has(part.type)) {
      tokens.set(part.type, part.value);
    }
  }

  const month = tokens.get("month") || "";
  const day = tokens.get("day") || "";
  const year = tokens.get("year") || "";
  const hour = tokens.get("hour") || "";
  const minute = tokens.get("minute") || "";
  const dayPeriod = tokens.get("dayPeriod")
    ? tokens.get("dayPeriod").toUpperCase()
    : "";
  const timeZoneName = tokens.get("timeZoneName") || "";

  const timeParts = [hour, minute].filter(Boolean);
  const time = timeParts.length ? timeParts.join(":") : "";
  const timeWithPeriod = [time, dayPeriod].filter(Boolean).join(" ");
  const timeWithZone = [timeWithPeriod, timeZoneName].filter(Boolean).join(" ");
  const datePart = [month, day].filter(Boolean).join(" ").trim();
  const dateWithYear = [datePart, year].filter(Boolean).join(", ").trim();

  if (dateWithYear && timeWithZone) {
    return `${dateWithYear}, ${timeWithZone}`;
  }
  return dateWithYear || timeWithZone || "Unknown";
}

function relocateBmcWidget() {
  const container = document.getElementById("bmc-widget-container");
  if (!container) return false;

  const widget =
    document.getElementById("bmc-wbtn") ||
    document.querySelector(".bmc-btn-container");

  if (!widget) return false;

  if (widget.parentElement !== container) {
    container.appendChild(widget);
  }

  return true;
}

// ---------- Resize Globe Helper ----------

function syncGlobeToContainerSize() {
  if (!globeInstance) return;
  const container = document.getElementById("globe");
  if (!container) return;

  const rect = container.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;

  if (!width || !height) return;

  globeInstance.width(width);
  globeInstance.height(height);
}

function setupGlobeResizeHandling() {
  const container = document.getElementById("globe");
  if (!container || !globeInstance) return;

  // Initial sync
  syncGlobeToContainerSize();

  // Clean up any existing observer
  if (globeResizeObserver) {
    globeResizeObserver.disconnect();
  }

  // Use ResizeObserver so it reacts to any layout change,
  // including sidebars, devtools, etc.
  globeResizeObserver = new ResizeObserver(() => {
    syncGlobeToContainerSize();
  });
  globeResizeObserver.observe(container);

  // Fallback: also listen for window resize
  window.addEventListener("resize", syncGlobeToContainerSize);
}

// ---------- Auto-rotate interaction helpers ----------

function setupAutoRotateInteraction(controls) {
  orbitControls = controls;
  if (!controls || typeof controls.addEventListener !== "function") return;

  const handleUserInteraction = () => {
    // Pause and schedule resume in 5s
    pauseAutoRotate();
  };

  // "start" and "end" are triggered by user input,
  // but NOT by autoRotate animation
  controls.addEventListener("start", handleUserInteraction);
  controls.addEventListener("end", handleUserInteraction);
}

function pauseAutoRotate(delay = 5000) {
  if (!orbitControls) return;

  orbitControls.autoRotate = false;

  if (autoRotateTimeoutId) {
    clearTimeout(autoRotateTimeoutId);
  }

  autoRotateTimeoutId = setTimeout(() => {
    orbitControls.autoRotate = true;
  }, delay);
}

// ---------- Globe ----------

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
      const icao = d.icao || "N/A";
      const name = d.name || "Unknown";
      const status = statusLabel(d.status);
      return `${icao} – ${name}<br/>Status: ${status}`;
    })
    // Make markers behave like list clicks
    .onPointClick(point => {
      if (point) {
        focusOnAirport(point);
      }
    })
     .onGlobeReady(() => {
      const controls = globeInstance.controls();
      if (controls) {
        controls.autoRotate = true;
        controls.autoRotateSpeed = 0.5;

        // Hook pause/resume on user interaction
        setupAutoRotateInteraction(controls);
      }

      // Sync size and keep globe centered within its section
      setupGlobeResizeHandling();
    });

}

function updateGlobePoints(airports) {
  if (!globeInstance) return;

  globeInstance
    .pointsData(airports)
    .pointLat(d => d.lat)
    .pointLng(d => d.lng)
    .pointColor(d => STATUS_COLORS[d.status] || "#e5e7eb");
}

function setSelectedAirport(icao, { scroll = false } = {}) {
  selectedAirportIcao = (icao || "").toUpperCase() || null;
  updateSelectedAirportInList({ scroll });
}

function updateSelectedAirportInList({ scroll = false } = {}) {
  const listEl = document.getElementById("airport-list");
  if (!listEl) return;

  const items = listEl.querySelectorAll(".airport-item");
  items.forEach(el => {
    const elIcao = (el.dataset.icao || "").toUpperCase();
    el.classList.toggle("is-selected", !!selectedAirportIcao && elIcao === selectedAirportIcao);
  });

  if (scroll && selectedAirportIcao) {
    const active = listEl.querySelector(`.airport-item[data-icao="${selectedAirportIcao}"]`);
    if (active) active.scrollIntoView({
      block: "center",
      behavior: "smooth"
    });
  }
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
      li.dataset.icao = (a.icao || "").toUpperCase();

      const left = document.createElement("div");
      const title = document.createElement("div");
      title.className = "airport-title";
      const name = document.createElement("div");
      name.className = "airport-name";
      title.textContent = a.icao || "N/A";
      name.textContent = a.name || "Unknown";

      const meta = document.createElement("div");
      meta.className = "airport-meta";
      if (typeof a.lat === "number" && typeof a.lng === "number") {
        meta.textContent = `${a.lat.toFixed(2)}, ${a.lng.toFixed(2)}`;
      } else {
        meta.textContent = "";
      }

      left.appendChild(title);
      left.appendChild(name);
      left.appendChild(meta);

      const dot = document.createElement("span");
      dot.className = `legend-dot legend-${a.status}`;

      li.appendChild(left);
      li.appendChild(dot);

      if (selectedAirportIcao && (a.icao || "").toUpperCase() === selectedAirportIcao) {
        li.classList.add("is-selected");
      }

      // List click behaves like marker click
      li.addEventListener("click", () => {
        setSelectedAirport(a.icao); // no scroll
        focusOnAirport(a);
      });

      listEl.appendChild(li);
    });
    updateSelectedAirportInList();
}

function focusOnAirport(airport) {
  if (!globeInstance || !airport) return;

  setSelectedAirport(airport.icao, { scroll: true });

  globeInstance.pointOfView(
    {
      lat: airport.lat,
      lng: airport.lng,
      altitude: 0.9 // zoom in when focusing
    },
    1250 // easing duration (ms)
  );

  // Pause autorotate a bit longer after focus
  pauseAutoRotate(6000);

  showAirportDetails(airport);
}

function showAirportDetails(airport) {
  const details = document.getElementById("airport-details");
  if (!details || !airport) return;

  const icaoEl = document.getElementById("airport-details-icao");
  const nameEl = document.getElementById("airport-details-name");
  const statusEl = document.getElementById("airport-details-status");
  const coordsEl = document.getElementById("airport-details-coords");
  const linkEl = document.getElementById("airport-details-link");

  if (icaoEl) icaoEl.textContent = airport.icao || "N/A";
  if (nameEl) nameEl.textContent = airport.name || "Unknown";

  if (statusEl) {
    const statusText = statusLabel(airport.status);
    statusEl.textContent = statusText || "Unknown";

    statusEl.className = "badge rounded-pill";
    if (airport.status === "base") {
      statusEl.classList.add("bg-secondary");
    } else if (airport.status === "in_dev") {
      statusEl.classList.add("bg-warning", "text-dark");
    } else if (airport.status === "released") {
      statusEl.classList.add("bg-success");
    }
  }

  if (coordsEl) {
    if (typeof airport.lat === "number" && typeof airport.lng === "number") {
      coordsEl.textContent = `${airport.lat.toFixed(2)}, ${airport.lng.toFixed(
        2
      )}`;
    } else {
      coordsEl.textContent = "";
    }
  }

  if (linkEl) {
    const link = airport.workshopUrl || airport.discordThread || null;
    if (link) {
      linkEl.href = link;
      linkEl.classList.remove("disabled");
      linkEl.textContent = "Open airport page";
    } else {
      linkEl.href = "#";
      linkEl.classList.add("disabled");
      linkEl.textContent = "No external link";
    }
  }

  details.classList.remove("d-none");
}

// ---------- LocalStorage helpers ----------

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

// ---------- Filtering ----------

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

  if (selectedAirportIcao) {
    const stillVisible = filteredAirports.some(
      a => (a.icao || "").toUpperCase() === selectedAirportIcao
    );
  if (!stillVisible) selectedAirportIcao = null;
  }
  updateSelectedAirportInList();

  saveFilterState();
}

// ---------- Init ----------

async function init() {
  // Load full data object
  const data = await loadAirports();
  const airports = Array.isArray(data.airports) ? data.airports : [];

  // Store globally
  allAirports = airports;
  filteredAirports = airports.slice();

  // Create globe + initial list
  createGlobe(filteredAirports);
  renderAirportList(filteredAirports);

  const dbUpdatedUtcEl = document.getElementById("database-updated-utc");
  const dbUpdatedLocalEl = document.getElementById("database-updated-local");
  const localLabel = formatDatabaseUpdatedLocal(data.lastUpdated);

  if (dbUpdatedUtcEl) {
    dbUpdatedUtcEl.textContent = formatDatabaseUpdated(data.lastUpdated);
  }

  if (dbUpdatedLocalEl) {
    dbUpdatedLocalEl.textContent = localLabel;
  }

  // Restore filters from localStorage, then apply them
  loadFilterState();

  const filterBase = document.getElementById("filter-base");
  const filterInDev = document.getElementById("filter-in-dev");
  const filterReleased = document.getElementById("filter-released");
  const searchInput = document.getElementById("search");

  if (filterBase) filterBase.addEventListener("change", applyFilters);
  if (filterInDev) filterInDev.addEventListener("change", applyFilters);
  if (filterReleased) filterReleased.addEventListener("change", applyFilters);
  if (searchInput) searchInput.addEventListener("input", applyFilters);

  applyFilters();

  let attempts = 0;
  const widgetTimer = setInterval(() => {
    attempts += 1;
    if (relocateBmcWidget() || attempts >= 20) {
      clearInterval(widgetTimer);
    }
  }, 250);
}

window.addEventListener("load", init);
