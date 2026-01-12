// main.js

const STATUS_COLORS = {
  base: "#a0aec0",
  in_dev: "#f6ad55",
  released: "#48bb78"
};

let allAirports = [];
let filteredAirports = [];
let globeInstance = null;

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

  // Globe is provided globally by the CDN script
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

function applyFilters() {
  const showBase = document.getElementById("filter-base").checked;
  const showInDev = document.getElementById("filter-in-dev").checked;
  const showReleased = document.getElementById("filter-released").checked;
  const searchValue = document
    .getElementById("search")
    .value.trim()
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
}

async function init() {
  allAirports = await loadAirports();
  filteredAirports = allAirports.slice();

  createGlobe(allAirports);
  renderAirportList(allAirports);

  document
    .getElementById("filter-base")
    .addEventListener("change", applyFilters);
  document
    .getElementById("filter-in-dev")
    .addEventListener("change", applyFilters);
  document
    .getElementById("filter-released")
    .addEventListener("change", applyFilters);
  document.getElementById("search").addEventListener("input", applyFilters);
}

// Make sure DOM is ready
window.addEventListener("load", init);
