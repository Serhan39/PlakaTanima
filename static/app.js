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
  loadLogs();
  connectLiveFeed();
}

function switchTab(tab) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
  if (tab === "watchlist") loadWatchlist();
  if (tab === "cameras") loadCameras();
  if (tab === "logs") loadLogs();
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

function setupCameras() {
  document.getElementById("camera-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("cam-name").value;
    const location = document.getElementById("cam-location").value;
    const rtsp_url = document.getElementById("cam-rtsp").value;
    try {
      await apiFetch("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, location, rtsp_url }),
      });
      event.target.reset();
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
        <td><button onclick="deleteCamera(${c.id})">Sil</button></td>
      </tr>`
    )
    .join("");
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
  };
}
