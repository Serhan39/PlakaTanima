const CATEGORY_LABELS = { allowed: "Izinli", staff: "Personel", wanted: "Aranan", blacklist: "Kara Liste" };

function getToken() { return localStorage.getItem("token"); }
function getRole() { return localStorage.getItem("role"); }

function authHeaders(extra = {}) {
  return { Authorization: `Bearer ${getToken()}`, ...extra };
}

async function apiFetch(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...authHeaders(), ...(options.headers || {}) } });
  if (response.status === 401) {
    localStorage.clear();
    window.location.href = "/login.html";
    throw new Error("Oturum sona erdi");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Istek basarisiz");
  }
  return response.status === 204 ? null : response.json();
}

function initLoginPage() {
  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    const errorEl = document.getElementById("login-error");
    errorEl.textContent = "";

    try {
      const body = new URLSearchParams({ username, password });
      const response = await fetch("/api/auth/login", { method: "POST", body });
      if (!response.ok) throw new Error("Kullanici adi veya sifre hatali");
      const data = await response.json();
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("role", data.role);
      window.location.href = "/index.html";
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });
}

function initDashboard() {
  if (!getToken()) {
    window.location.href = "/login.html";
    return;
  }

  document.getElementById("logout-btn").addEventListener("click", () => {
    localStorage.clear();
    window.location.href = "/login.html";
  });

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  if (getRole() !== "admin") {
    document.querySelector('[data-tab="cameras"]').style.display = "none";
  }

  setupWatchlist();
  setupCameras();
  setupReports();
  setupParkingWidget();
  setupEquipmentTracking();
  loadLogs();
  connectLiveFeed();
}

function switchTab(tab) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
  if (tab === "watchlist") loadWatchlist();
  if (tab === "cameras") loadCameras();
  if (tab === "logs") loadLogs();
  if (tab === "reports") loadReportCameraOptions().then(loadReports);
  if (tab === "equipment") { loadZones(); loadGates(); loadEquipmentStatus(); }
}

function setupWatchlist() {
  document.getElementById("watchlist-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const plate = document.getElementById("wl-plate").value;
    const category = document.getElementById("wl-category").value;
    const note = document.getElementById("wl-note").value;
    try {
      await apiFetch("/api/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plate, category, note }),
      });
      event.target.reset();
      loadWatchlist();
    } catch (err) {
      alert(err.message);
    }
  });
  loadWatchlist();
}

async function loadWatchlist() {
  const entries = await apiFetch("/api/watchlist");
  const tbody = document.querySelector("#watchlist-table tbody");
  tbody.innerHTML = entries
    .map(
      (e) => `<tr>
        <td>${e.plate}</td>
        <td>${CATEGORY_LABELS[e.category] || e.category}</td>
        <td>${e.note || "-"}</td>
        <td>${new Date(e.created_at).toLocaleString("tr-TR")}</td>
        <td><button onclick="deleteWatchlistEntry(${e.id})">Sil</button></td>
      </tr>`
    )
    .join("");
}

async function deleteWatchlistEntry(id) {
  if (!confirm("Bu kaydi silmek istediginize emin misiniz?")) return;
  await apiFetch(`/api/watchlist/${id}`, { method: "DELETE" });
  loadWatchlist();
}

const RELAY_LABELS = { none: "Yok", http: "HTTP", tcp: "TCP", modbus_tcp: "Modbus TCP" };
const DIRECTION_LABELS = { none: "-", entry: "Giris", exit: "Cikis" };

function setupCameras() {
  document.getElementById("camera-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("cam-name").value;
    const location = document.getElementById("cam-location").value;
    const rtsp_url = document.getElementById("cam-rtsp").value;
    const direction = document.getElementById("cam-direction").value;
    const relay_type = document.getElementById("relay-type").value;
    const relay_target = document.getElementById("relay-target").value;
    const relay_command = document.getElementById("relay-command").value;
    const relay_pulse_seconds = parseFloat(document.getElementById("relay-pulse").value) || 3.0;
    const open_categories = document.getElementById("relay-categories").value || "allowed,staff";
    try {
      await apiFetch("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, location, rtsp_url, direction, relay_type, relay_target, relay_command, relay_pulse_seconds, open_categories }),
      });
      event.target.reset();
      document.getElementById("relay-config-form").reset();
      loadCameras();
    } catch (err) {
      alert(err.message);
    }
  });
}

async function loadCameras() {
  const cameras = await apiFetch("/api/cameras");
  const tbody = document.querySelector("#camera-table tbody");
  tbody.innerHTML = cameras
    .map(
      (c) => `<tr>
        <td>${c.name}</td>
        <td>${c.location || "-"}</td>
        <td>${c.rtsp_url}</td>
        <td>${c.is_active ? "Aktif" : "Pasif"}</td>
        <td>${DIRECTION_LABELS[c.direction] || c.direction}</td>
        <td>${RELAY_LABELS[c.relay_type] || c.relay_type}</td>
        <td>
          <button class="secondary" onclick="testRelay(${c.id})">Roleyi Test Et</button>
          <button onclick="deleteCamera(${c.id})">Sil</button>
        </td>
      </tr>`
    )
    .join("");
}

async function testRelay(id) {
  try {
    const result = await apiFetch(`/api/cameras/${id}/test-relay`, { method: "POST" });
    alert(result.success ? `Basarili: ${result.message}` : `Basarisiz: ${result.message}`);
  } catch (err) {
    alert(err.message);
  }
}

async function deleteCamera(id) {
  if (!confirm("Bu kamerayi silmek istediginize emin misiniz?")) return;
  await apiFetch(`/api/cameras/${id}`, { method: "DELETE" });
  loadCameras();
}

async function loadLogs() {
  const logs = await apiFetch("/api/logs?limit=100");
  const tbody = document.querySelector("#logs-table tbody");
  tbody.innerHTML = logs
    .map(
      (l) => `<tr>
        <td>${l.plate}</td>
        <td>${(l.confidence * 100).toFixed(0)}%</td>
        <td>${l.matched_category ? CATEGORY_LABELS[l.matched_category] : "-"}</td>
        <td>${l.camera_id ?? "-"}</td>
        <td>${new Date(l.detected_at).toLocaleString("tr-TR")}</td>
      </tr>`
    )
    .join("");
}

function setupReports() {
  document.getElementById("report-filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    loadReports();
  });
  document.getElementById("rp-send-daily-btn").addEventListener("click", async () => {
    const resultEl = document.getElementById("rp-send-daily-result");
    resultEl.textContent = "Gonderiliyor...";
    try {
      const result = await apiFetch("/api/reports/send-daily", { method: "POST" });
      resultEl.textContent = result.sent ? "Gonderildi." : "SMTP yapilandirilmamis, gonderilemedi.";
    } catch (err) {
      resultEl.textContent = err.message;
    }
  });

  document.getElementById("rp-export-btn").addEventListener("click", async (event) => {
    event.preventDefault();
    const params = reportQueryParams();
    const response = await fetch(`/api/reports/export.csv?${params.toString()}`, { headers: authHeaders() });
    if (!response.ok) {
      alert("CSV indirilemedi");
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "sertek-alpr-rapor.csv";
    a.click();
    URL.revokeObjectURL(url);
  });
}

async function loadReportCameraOptions() {
  const select = document.getElementById("rp-camera");
  if (select.dataset.loaded) return;
  const cameras = await apiFetch("/api/cameras");
  cameras.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = c.name;
    select.appendChild(opt);
  });
  select.dataset.loaded = "1";
}

function reportQueryParams() {
  const params = new URLSearchParams();
  const from = document.getElementById("rp-from").value;
  const to = document.getElementById("rp-to").value;
  const camera = document.getElementById("rp-camera").value;
  const category = document.getElementById("rp-category").value;
  const plate = document.getElementById("rp-plate").value;
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  if (camera) params.set("camera_id", camera);
  if (category) params.set("category", category);
  if (plate) params.set("plate_query", plate);
  return params;
}

async function loadReports() {
  const params = reportQueryParams();

  const summary = await apiFetch(`/api/reports/summary?${params.toString()}`);
  const summaryEl = document.getElementById("report-summary");
  const categoryCards = Object.entries(summary.by_category)
    .map(([key, count]) => `<div class="report-card"><div class="value">${count}</div><div class="label">${CATEGORY_LABELS[key] || key}</div></div>`)
    .join("");
  summaryEl.innerHTML = `<div class="report-card"><div class="value">${summary.total}</div><div class="label">Toplam Tespit</div></div>${categoryCards}`;

  const logs = await apiFetch(`/api/reports/logs?${params.toString()}`);
  const tbody = document.querySelector("#report-table tbody");
  tbody.innerHTML = logs
    .map(
      (l) => `<tr>
        <td>${l.plate}</td>
        <td>${(l.confidence * 100).toFixed(0)}%</td>
        <td>${l.matched_category ? CATEGORY_LABELS[l.matched_category] : "-"}</td>
        <td>${l.camera_id ?? "-"}</td>
        <td>${new Date(l.detected_at).toLocaleString("tr-TR")}</td>
      </tr>`
    )
    .join("");
}

function connectLiveFeed() {
  const statusEl = document.getElementById("live-status");
  const feedEl = document.getElementById("live-feed");
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${proto}://${window.location.host}/ws/alerts`);

  socket.onopen = () => {
    statusEl.textContent = "Bagli";
    statusEl.classList.add("online");
  };
  socket.onclose = () => {
    statusEl.textContent = "Baglanti kesildi";
    statusEl.classList.remove("online");
  };
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    (data.detections || []).forEach((d) => {
      const item = document.createElement("div");
      item.className = `detection-item ${d.matched_category || ""}`;
      item.innerHTML = `<strong>${d.plate}</strong><span>${CATEGORY_LABELS[d.matched_category] || "Kayitsiz"} - %${Math.round(d.confidence * 100)}</span>`;
      feedEl.prepend(item);
      while (feedEl.children.length > 30) feedEl.removeChild(feedEl.lastChild);
    });
    if ((data.detections || []).length > 0) loadParkingStatus();
  };
}

function setupParkingWidget() {
  document.getElementById("parking-capacity-btn").addEventListener("click", async () => {
    const current = document.getElementById("parking-capacity").textContent;
    const input = prompt("Otopark kapasitesi (toplam arac sayisi):", current === "-" ? "" : current);
    if (input === null) return;
    const capacity = parseInt(input, 10);
    if (Number.isNaN(capacity) || capacity < 0) {
      alert("Gecerli bir sayi girin");
      return;
    }
    try {
      await apiFetch("/api/parking/capacity", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ capacity }),
      });
      loadParkingStatus();
    } catch (err) {
      alert(err.message);
    }
  });

  if (getRole() !== "admin") {
    document.getElementById("parking-capacity-btn").style.display = "none";
  }

  loadParkingStatus();
  setInterval(loadParkingStatus, 15000);
}

async function loadParkingStatus() {
  try {
    const status = await apiFetch("/api/parking/status");
    document.getElementById("parking-inside").textContent = status.inside;
    document.getElementById("parking-capacity").textContent = status.capacity;
    document.getElementById("parking-percent").textContent = `%${status.occupancy_percent} dolu`;
    const fill = document.getElementById("parking-bar-fill");
    fill.style.width = `${Math.min(status.occupancy_percent, 100)}%`;
    fill.classList.toggle("full", status.occupancy_percent >= 90);
  } catch (err) {
    // canli akis sekmesindeyken sessizce yoksay, oturum sona ermisse apiFetch zaten yonlendirir
  }
}

async function setupEquipmentTracking() {
  const toggleWrap = document.getElementById("equipment-toggle-wrap");
  const toggle = document.getElementById("equipment-toggle");
  const tabBtn = document.getElementById("equipment-tab-btn");

  if (getRole() === "admin") {
    toggleWrap.style.display = "flex";
    toggle.addEventListener("change", async () => {
      try {
        await apiFetch("/api/equipment/feature-status", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: toggle.checked }),
        });
        tabBtn.style.display = toggle.checked ? "" : "none";
        if (!toggle.checked && document.getElementById("tab-equipment").classList.contains("active")) {
          switchTab("live");
        }
      } catch (err) {
        alert(err.message);
        toggle.checked = !toggle.checked;
      }
    });
  }

  try {
    const status = await apiFetch("/api/equipment/feature-status");
    tabBtn.style.display = status.enabled ? "" : "none";
    if (toggle) toggle.checked = status.enabled;
  } catch (err) {
    // sessizce yoksay
  }

  document.getElementById("zone-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("zone-name").value;
    try {
      await apiFetch("/api/equipment/zones", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      event.target.reset();
      loadZones();
    } catch (err) {
      alert(err.message);
    }
  });

  document.getElementById("gate-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("gate-name").value;
    const rtsp_url = document.getElementById("gate-rtsp").value;
    const zone_id = parseInt(document.getElementById("gate-zone").value, 10);
    const direction = document.getElementById("gate-direction").value;
    if (!zone_id) {
      alert("Once bir alan ekleyin");
      return;
    }
    try {
      await apiFetch("/api/equipment/gates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, rtsp_url, zone_id, direction }),
      });
      event.target.reset();
      loadGates();
    } catch (err) {
      alert(err.message);
    }
  });

  loadZones();
  connectEquipmentLiveFeed();
}

async function loadZones() {
  const zones = await apiFetch("/api/equipment/zones");
  const tbody = document.querySelector("#zone-table tbody");
  tbody.innerHTML = zones
    .map((z) => `<tr><td>${z.name}</td><td><button onclick="deleteZone(${z.id})">Sil</button></td></tr>`)
    .join("");

  const select = document.getElementById("gate-zone");
  const currentValue = select.value;
  select.innerHTML = zones.map((z) => `<option value="${z.id}">${z.name}</option>`).join("");
  if (currentValue) select.value = currentValue;
}

async function deleteZone(id) {
  if (!confirm("Bu alani silmek istediginize emin misiniz?")) return;
  try {
    await apiFetch(`/api/equipment/zones/${id}`, { method: "DELETE" });
    loadZones();
  } catch (err) {
    alert(err.message);
  }
}

async function loadGates() {
  const [gates, zones] = await Promise.all([apiFetch("/api/equipment/gates"), apiFetch("/api/equipment/zones")]);
  const zoneNames = Object.fromEntries(zones.map((z) => [z.id, z.name]));
  const tbody = document.querySelector("#gate-table tbody");
  tbody.innerHTML = gates
    .map(
      (g) => `<tr>
        <td>${g.name}</td>
        <td>${zoneNames[g.zone_id] || "-"}</td>
        <td>${DIRECTION_LABELS[g.direction] || g.direction}</td>
        <td>${g.rtsp_url || "-"}</td>
        <td><button onclick="deleteGate(${g.id})">Sil</button></td>
      </tr>`
    )
    .join("");
}

async function deleteGate(id) {
  if (!confirm("Bu kapiyi silmek istediginize emin misiniz?")) return;
  try {
    await apiFetch(`/api/equipment/gates/${id}`, { method: "DELETE" });
    loadGates();
  } catch (err) {
    alert(err.message);
  }
}

async function loadEquipmentStatus() {
  const rows = await apiFetch("/api/equipment/status");
  const tbody = document.querySelector("#equipment-status-table tbody");
  tbody.innerHTML = rows
    .map(
      (r) => `<tr>
        <td>${r.plate}</td>
        <td>${r.zone_name}</td>
        <td>${new Date(r.updated_at).toLocaleString("tr-TR")}</td>
      </tr>`
    )
    .join("");
}

function connectEquipmentLiveFeed() {
  const statusEl = document.getElementById("equipment-live-status");
  const feedEl = document.getElementById("equipment-live-feed");
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${proto}://${window.location.host}/ws/equipment`);

  socket.onopen = () => {
    statusEl.textContent = "Bagli";
    statusEl.classList.add("online");
  };
  socket.onclose = () => {
    statusEl.textContent = "Baglanti kesildi";
    statusEl.classList.remove("online");
  };
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    (data.events || []).forEach((e) => {
      const item = document.createElement("div");
      item.className = `detection-item ${e.direction === "exit" ? "exit" : "entry"}`;
      item.innerHTML = `<strong>${e.message}</strong><span>%${Math.round(e.confidence * 100)}</span>`;
      feedEl.prepend(item);
      while (feedEl.children.length > 30) feedEl.removeChild(feedEl.lastChild);
    });
    if ((data.events || []).length > 0) loadEquipmentStatus();
  };
}
