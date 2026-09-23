const CATEGORY_LABELS = { allowed: "Izinli", staff: "Personel", wanted: "Aranan", blacklist: "Kara Liste" };

function getToken() { return localStorage.getItem("token"); }
function getRole() { return localStorage.getItem("role"); }
function canManageEquipment() { return getRole() === "admin" || !!localStorage.getItem("canManageEquipment"); }

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
      localStorage.setItem("canManageEquipment", data.can_manage_equipment ? "1" : "");
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
  } else {
    document.getElementById("users-tab-btn").style.display = "";
  }

  setupWatchlist();
  setupCameras();
  setupReports();
  setupParkingWidget();
  setupEquipmentTracking();
  setupUsers();
  setupLiveCameraPreview();
  loadLogs();
  loadRecentDetections();
  connectLiveFeed();
}

function switchTab(tab) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
  if (tab === "watchlist") loadWatchlist();
  if (tab === "cameras") loadCameras();
  if (tab === "logs") loadLogs();
  if (tab === "reports") loadReportCameraOptions().then(loadReports);
  if (tab === "equipment") { loadZones(); loadEquipmentStatus(); }
  if (tab === "users") loadUsers();
  if (tab === "live") startLiveCameraPolling(); else stopLiveCameraPolling();
}

// Onceki surum periyodik olarak tek kare cekip <img> gostererek "canli"
// izlenim veriyordu (poll ne kadar siklastirilirsa siklastirilsin, bu
// asla gercek video hissi vermez - her zaman ayrik "zipla" adimlari olur).
// Artik tarayicinin native olarak destekledigi bir MJPEG akisina (<img
// src="/api/cameras/{id}/stream?token=...">) baglaniyoruz; JS tarafinda
// polling/interval yok, tarayici karelari geldikce kendisi gosteriyor.
let liveCameraIds = [];
const liveCameraNames = {}; // cameraId -> ad (modal basligi icin)

async function setupLiveCameraPreview() {
  await loadLiveCameraGrid();
  setupCameraModal();
}

async function loadLiveCameraGrid() {
  const grid = document.getElementById("live-camera-grid");
  const emptyMsg = document.getElementById("live-camera-empty");
  try {
    const cameras = await apiFetch("/api/cameras");
    const usable = cameras.filter((c) => c.rtsp_url);
    liveCameraIds = usable.map((c) => c.id);
    usable.forEach((c) => { liveCameraNames[c.id] = c.name; });

    if (usable.length === 0) {
      grid.innerHTML = "";
      grid.appendChild(emptyMsg);
      emptyMsg.textContent = "Onizlenebilir kamera yok (once RTSP adresli bir kamera ekleyin)";
      return;
    }

    grid.innerHTML = usable
      .map(
        (c) => `<div class="live-camera-tile">
          <div class="live-camera-frame" ondblclick="openCameraModal(${c.id})" title="Buyutmek icin cift tiklayin">
            <img id="live-camera-img-${c.id}" alt="${c.name}" style="display:none;">
            <div id="live-camera-placeholder-${c.id}" class="live-camera-placeholder">Baglaniliyor...</div>
          </div>
          <div class="live-camera-label">${c.name}</div>
        </div>`
      )
      .join("");

    if (document.getElementById("tab-live").classList.contains("active")) startLiveCameraPolling();
  } catch (err) {
    // kamera listesi alinamadiysa sessizce yoksay, mevcut grid yerinde kalir
  }
}

function setupCameraModal() {
  document.getElementById("camera-modal-backdrop").addEventListener("click", closeCameraModal);
  document.getElementById("camera-modal-close").addEventListener("click", closeCameraModal);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeCameraModal();
  });
}

async function openCameraModal(cameraId) {
  const modal = document.getElementById("camera-modal");
  const modalImg = document.getElementById("camera-modal-img");
  document.getElementById("camera-modal-title").textContent = liveCameraNames[cameraId] || "";
  modal.style.display = "flex";

  try {
    const { token } = await apiFetch(`/api/cameras/${cameraId}/stream-token`, { method: "POST" });
    modalImg.src = `/api/cameras/${cameraId}/stream?token=${encodeURIComponent(token)}`;
  } catch (err) {
    closeCameraModal();
    alert("Buyutulmus goruntuye baglanilamadi: " + err.message);
  }
}

function closeCameraModal() {
  const modal = document.getElementById("camera-modal");
  const modalImg = document.getElementById("camera-modal-img");
  modal.style.display = "none";
  modalImg.src = ""; // akisi kapat, gereksiz bant genisligi harcamasin
}

async function startLiveCameraPolling() {
  for (const id of liveCameraIds) {
    connectLiveCameraStream(id);
  }
}

function stopLiveCameraPolling() {
  // Akisi kapatmak icin src'yi temizlemek yeterli - tarayici baglantiyi
  // sonlandirir (sekme degisince gereksiz bant genisligi harcamamak icin).
  liveCameraIds.forEach((id) => {
    const img = document.getElementById(`live-camera-img-${id}`);
    if (img) img.src = "";
  });
}

async function connectLiveCameraStream(cameraId) {
  const img = document.getElementById(`live-camera-img-${cameraId}`);
  const placeholder = document.getElementById(`live-camera-placeholder-${cameraId}`);
  if (!img || !placeholder) return; // grid yeniden olusturulmus olabilir

  try {
    const { token } = await apiFetch(`/api/cameras/${cameraId}/stream-token`, { method: "POST" });
    img.onload = () => {
      img.style.display = "block";
      placeholder.style.display = "none";
    };
    img.onerror = () => {
      img.style.display = "none";
      placeholder.style.display = "block";
      placeholder.textContent = "Baglanti kesildi, yeniden deneniyor...";
      // Akis bir ag kesintisi/kamera yeniden baslatma sonrasi koptuyse,
      // birkac saniye sonra yeni bir token ile yeniden baglan.
      setTimeout(() => {
        if (document.getElementById("tab-live").classList.contains("active")) connectLiveCameraStream(cameraId);
      }, 3000);
    };
    img.src = `/api/cameras/${cameraId}/stream?token=${encodeURIComponent(token)}`;
  } catch (err) {
    placeholder.textContent = "Kameraya baglanilamiyor";
  }
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
const SOURCE_LABELS = { camera: "Kamera", manual: "Manuel" };

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
      loadLiveCameraGrid();
    } catch (err) {
      alert(err.message);
    }
  });

  setupCameraRoiEditor();
}

let currentCamerasCache = [];

async function loadCameras() {
  const cameras = await apiFetch("/api/cameras");
  currentCamerasCache = cameras;
  const tbody = document.querySelector("#camera-table tbody");
  tbody.innerHTML = cameras
    .map((c) => {
      const hasRoi = c.roi_x1 !== null && c.roi_x1 !== undefined;
      return `<tr>
        <td>${c.name}</td>
        <td>${c.location || "-"}</td>
        <td>${c.rtsp_url}</td>
        <td>${c.is_active ? "Aktif" : "Pasif"}</td>
        <td>${DIRECTION_LABELS[c.direction] || c.direction}</td>
        <td>${RELAY_LABELS[c.relay_type] || c.relay_type}</td>
        <td>${hasRoi ? "Tanimli" : "Tum kare"}</td>
        <td>
          <button class="secondary" onclick="openCameraRoiEditor(${c.id})" ${c.rtsp_url ? "" : "disabled"}>Bolgeyi Duzenle</button>
          <button class="secondary" onclick="testRelay(${c.id})">Roleyi Test Et</button>
          <button onclick="deleteCamera(${c.id})">Sil</button>
        </td>
      </tr>`;
    })
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
  loadLiveCameraGrid();
}

let cameraRoiState = null; // { cameraId, img, points: [{x,y}] } (en fazla 2 nokta: sol-ust, sag-alt)

function openCameraRoiEditor(cameraId) {
  const camera = currentCamerasCache.find((c) => c.id === cameraId);
  if (!camera) return;

  document.getElementById("camera-roi-editor-title").textContent = `${camera.name} - Tespit Bolgesi`;
  document.getElementById("camera-roi-editor").style.display = "block";
  document.getElementById("camera-roi-editor").scrollIntoView({ behavior: "smooth", block: "center" });

  cameraRoiState = { cameraId, img: null, points: [] };
  loadCameraRoiPreview();
}

async function loadCameraRoiPreview() {
  if (!cameraRoiState) return;
  const canvas = document.getElementById("camera-roi-canvas");
  try {
    const response = await fetch(`/api/cameras/${cameraRoiState.cameraId}/preview`, { headers: authHeaders() });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      alert(body.detail || "Kameradan onizleme alinamadi");
      return;
    }
    const blob = await response.blob();
    const img = new Image();
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      cameraRoiState.img = img;

      const camera = currentCamerasCache.find((c) => c.id === cameraRoiState.cameraId);
      cameraRoiState.points =
        camera && camera.roi_x1 !== null && camera.roi_x1 !== undefined
          ? [
              { x: camera.roi_x1 * img.width, y: camera.roi_y1 * img.height },
              { x: camera.roi_x2 * img.width, y: camera.roi_y2 * img.height },
            ]
          : [];
      redrawCameraRoiEditor();
    };
    img.src = URL.createObjectURL(blob);
  } catch (err) {
    alert("Onizleme alinamadi: " + err.message);
  }
}

function redrawCameraRoiEditor() {
  if (!cameraRoiState || !cameraRoiState.img) return;
  const canvas = document.getElementById("camera-roi-canvas");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(cameraRoiState.img, 0, 0, canvas.width, canvas.height);

  const [p1, p2] = cameraRoiState.points;
  if (p1 && p2) {
    const x = Math.min(p1.x, p2.x);
    const y = Math.min(p1.y, p2.y);
    const w = Math.abs(p2.x - p1.x);
    const h = Math.abs(p2.y - p1.y);
    ctx.strokeStyle = "#2563eb";
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = "rgba(37, 99, 235, 0.15)";
    ctx.fillRect(x, y, w, h);
  }
  cameraRoiState.points.forEach((p) => {
    ctx.fillStyle = "#2563eb";
    ctx.beginPath();
    ctx.arc(p.x, p.y, 7, 0, Math.PI * 2);
    ctx.fill();
  });
}

function setupCameraRoiEditor() {
  const canvas = document.getElementById("camera-roi-canvas");
  canvas.addEventListener("click", (event) => {
    if (!cameraRoiState || !cameraRoiState.img) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = (event.clientX - rect.left) * scaleX;
    const y = (event.clientY - rect.top) * scaleY;

    if (cameraRoiState.points.length >= 2) {
      cameraRoiState.points = []; // iki nokta tamamlandiysa yeniden basla
    }
    cameraRoiState.points.push({ x, y });
    redrawCameraRoiEditor();
  });

  document.getElementById("camera-roi-refresh-btn").addEventListener("click", () => loadCameraRoiPreview());

  document.getElementById("camera-roi-reset-btn").addEventListener("click", () => {
    if (!cameraRoiState) return;
    cameraRoiState.points = [];
    redrawCameraRoiEditor();
  });

  document.getElementById("camera-roi-cancel-btn").addEventListener("click", () => {
    document.getElementById("camera-roi-editor").style.display = "none";
    cameraRoiState = null;
  });

  document.getElementById("camera-roi-clear-btn").addEventListener("click", async () => {
    if (!cameraRoiState) return;
    try {
      await apiFetch(`/api/cameras/${cameraRoiState.cameraId}/roi`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ roi_x1: null, roi_y1: null, roi_x2: null, roi_y2: null }),
      });
      document.getElementById("camera-roi-editor").style.display = "none";
      cameraRoiState = null;
      loadCameras();
    } catch (err) {
      alert(err.message);
    }
  });

  document.getElementById("camera-roi-save-btn").addEventListener("click", async () => {
    if (!cameraRoiState || cameraRoiState.points.length !== 2) {
      alert("Bolgenin sol-ust ve sag-alt koselerine tiklayin (toplam 2 tiklama)");
      return;
    }
    const canvas = document.getElementById("camera-roi-canvas");
    const [p1, p2] = cameraRoiState.points;
    const x1 = Math.min(p1.x, p2.x) / canvas.width;
    const y1 = Math.min(p1.y, p2.y) / canvas.height;
    const x2 = Math.max(p1.x, p2.x) / canvas.width;
    const y2 = Math.max(p1.y, p2.y) / canvas.height;
    try {
      await apiFetch(`/api/cameras/${cameraRoiState.cameraId}/roi`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ roi_x1: x1, roi_y1: y1, roi_x2: x2, roi_y2: y2 }),
      });
      alert("Tespit bolgesi kaydedildi. Bir sonraki tespitten itibaren gecerli olacak (worker'i yeniden baslatmaya gerek yok).");
      document.getElementById("camera-roi-editor").style.display = "none";
      cameraRoiState = null;
      loadCameras();
    } catch (err) {
      alert(err.message);
    }
  });
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

async function loadSnapshotInto(imgEl, logId) {
  try {
    const response = await fetch(`/api/logs/${logId}/snapshot`, { headers: authHeaders() });
    if (!response.ok) return;
    const blob = await response.blob();
    imgEl.src = URL.createObjectURL(blob);
  } catch (err) {
    // fotograf yuklenemezse sessizce yoksay
  }
}

function renderDetectionItem(d) {
  const item = document.createElement("div");
  item.className = `detection-item ${d.matched_category || ""}`;
  const main = document.createElement("div");
  main.className = "detection-item-main";
  if (d.has_snapshot) {
    const thumb = document.createElement("img");
    thumb.className = "detection-thumb";
    loadSnapshotInto(thumb, d.id);
    main.appendChild(thumb);
  }
  const text = document.createElement("div");
  text.innerHTML = `<strong>${d.plate}</strong><br><span>${CATEGORY_LABELS[d.matched_category] || "Kayitsiz"} - %${Math.round(d.confidence * 100)}</span>`;
  main.appendChild(text);
  item.appendChild(main);
  return item;
}

function updateLastVehicleCard(d) {
  const photo = document.getElementById("last-vehicle-photo");
  const placeholder = document.getElementById("last-vehicle-placeholder");
  const info = document.getElementById("last-vehicle-info");
  info.textContent = `${d.plate} - ${CATEGORY_LABELS[d.matched_category] || "Kayitsiz"} - %${Math.round(d.confidence * 100)}`;
  if (d.has_snapshot) {
    loadSnapshotInto(photo, d.id).then(() => {
      photo.style.display = "block";
      placeholder.style.display = "none";
    });
  } else {
    photo.style.display = "none";
    placeholder.style.display = "block";
    placeholder.textContent = "Bu gecis icin fotograf kaydedilmedi";
  }
}

async function loadRecentDetections() {
  const feedEl = document.getElementById("live-feed");
  try {
    const logs = await apiFetch("/api/logs?limit=10");
    feedEl.innerHTML = "";
    logs.forEach((d) => feedEl.appendChild(renderDetectionItem(d)));
    if (logs.length > 0) updateLastVehicleCard(logs[0]);
  } catch (err) {
    // yoksay
  }
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
    const detections = data.detections || [];
    detections.forEach((d) => {
      feedEl.prepend(renderDetectionItem(d));
      while (feedEl.children.length > 10) feedEl.removeChild(feedEl.lastChild);
    });
    if (detections.length > 0) {
      updateLastVehicleCard(detections[detections.length - 1]);
      loadParkingStatus();
    }
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

const ROLE_LABELS = { admin: "Yonetici", operator: "Operator", viewer: "Izleyici" };

function setupUsers() {
  if (getRole() !== "admin") return;

  document.getElementById("user-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const username = document.getElementById("user-username").value;
    const password = document.getElementById("user-password").value;
    const role = document.getElementById("user-role").value;
    const can_manage_equipment = document.getElementById("user-can-manage-equipment").checked;
    try {
      await apiFetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, role, can_manage_equipment }),
      });
      event.target.reset();
      loadUsers();
    } catch (err) {
      alert(err.message);
    }
  });
}

async function loadUsers() {
  const users = await apiFetch("/api/users");
  const tbody = document.querySelector("#user-table tbody");
  tbody.innerHTML = users
    .map(
      (u) => `<tr>
        <td>${u.username}</td>
        <td>${ROLE_LABELS[u.role] || u.role}</td>
        <td>${u.can_manage_equipment ? "Var" : "-"}</td>
        <td>${new Date(u.created_at).toLocaleString("tr-TR")}</td>
        <td><button onclick="deleteUser(${u.id})">Sil</button></td>
      </tr>`
    )
    .join("");
}

async function deleteUser(id) {
  if (!confirm("Bu kullaniciyi silmek istediginize emin misiniz?")) return;
  try {
    await apiFetch(`/api/users/${id}`, { method: "DELETE" });
    loadUsers();
  } catch (err) {
    alert(err.message);
  }
}

async function setupEquipmentTracking() {
  const toggleWrap = document.getElementById("equipment-toggle-wrap");
  const toggle = document.getElementById("equipment-toggle");
  const tabBtn = document.getElementById("equipment-tab-btn");

  if (canManageEquipment()) {
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

  if (getRole() === "admin" || getRole() === "operator") {
    document.getElementById("eq-manual-crossing-wrap").style.display = "block";
    document.getElementById("eq-manual-crossing-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const gate_id = parseInt(document.getElementById("eq-manual-gate").value, 10);
      const code = document.getElementById("eq-manual-code").value;
      const direction = document.getElementById("eq-manual-direction").value;
      if (!gate_id) {
        alert("Once bir kapi ekleyin");
        return;
      }
      try {
        await apiFetch("/api/equipment/crossings/manual", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ gate_id, code, direction }),
        });
        document.getElementById("eq-manual-code").value = "";
        loadEquipmentStatus();
        loadEquipmentLogs();
      } catch (err) {
        alert(err.message);
      }
    });
  }

  document.getElementById("eq-log-filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    loadEquipmentLogs();
  });

  document.getElementById("eq-time-report-form").addEventListener("submit", (event) => {
    event.preventDefault();
    loadEquipmentTimeReport();
  });

  setupGateLineEditor();
  loadZones();
  loadEquipmentLogs();
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

  const filterSelect = document.getElementById("eq-log-zone");
  const filterCurrent = filterSelect.value;
  filterSelect.innerHTML =
    `<option value="">Tum Alanlar</option>` + zones.map((z) => `<option value="${z.id}">${z.name}</option>`).join("");
  filterSelect.value = filterCurrent;

  loadGates();
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

let currentGatesCache = [];
let currentZonesCache = [];

async function loadGates() {
  const [gates, zones] = await Promise.all([apiFetch("/api/equipment/gates"), apiFetch("/api/equipment/zones")]);
  currentGatesCache = gates;
  currentZonesCache = zones;
  const zoneNames = Object.fromEntries(zones.map((z) => [z.id, z.name]));
  const tbody = document.querySelector("#gate-table tbody");
  tbody.innerHTML = gates
    .map(
      (g) => `<tr>
        <td>${g.name}</td>
        <td>${zoneNames[g.zone_id] || "-"}</td>
        <td>${DIRECTION_LABELS[g.direction] || g.direction}</td>
        <td>${g.rtsp_url || "-"}</td>
        <td>
          <button class="secondary" onclick="openGateLineEditor(${g.id})" ${g.rtsp_url ? "" : "disabled"}>Cizgiyi Duzenle</button>
          <button onclick="deleteGate(${g.id})">Sil</button>
        </td>
      </tr>`
    )
    .join("");

  const filterSelect = document.getElementById("eq-log-gate");
  const filterCurrent = filterSelect.value;
  filterSelect.innerHTML =
    `<option value="">Tum Kapilar</option>` + gates.map((g) => `<option value="${g.id}">${g.name}</option>`).join("");
  filterSelect.value = filterCurrent;

  const manualGateSelect = document.getElementById("eq-manual-gate");
  const manualCurrent = manualGateSelect.value;
  manualGateSelect.innerHTML = gates.map((g) => `<option value="${g.id}">${g.name}</option>`).join("");
  if (manualCurrent) manualGateSelect.value = manualCurrent;
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

let lineEditorState = null; // { gateId, img, points: [{x,y,kind}] }

function openGateLineEditor(gateId) {
  const gate = currentGatesCache.find((g) => g.id === gateId);
  if (!gate) return;
  const zone = currentZonesCache.find((z) => z.id === gate.zone_id);

  document.getElementById("gate-line-editor-title").textContent = `${gate.name} - Gecis Cizgisi`;
  document.getElementById("gate-line-zone-name").textContent = zone ? zone.name : "?";
  document.getElementById("gate-line-editor").style.display = "block";
  document.getElementById("gate-line-editor").scrollIntoView({ behavior: "smooth", block: "center" });

  lineEditorState = { gateId, img: null, points: [] };
  loadGateLinePreview();
}

async function loadGateLinePreview() {
  if (!lineEditorState) return;
  const canvas = document.getElementById("gate-line-canvas");
  try {
    const response = await fetch(`/api/equipment/gates/${lineEditorState.gateId}/preview`, { headers: authHeaders() });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      alert(body.detail || "Kameradan onizleme alinamadi");
      return;
    }
    const blob = await response.blob();
    const img = new Image();
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      lineEditorState.img = img;

      const gate = currentGatesCache.find((g) => g.id === lineEditorState.gateId);
      lineEditorState.points = gate
        ? [
            { x: gate.line_x1 * img.width, y: gate.line_y1 * img.height, kind: "line" },
            { x: gate.line_x2 * img.width, y: gate.line_y2 * img.height, kind: "line" },
            { x: gate.inside_x * img.width, y: gate.inside_y * img.height, kind: "inside" },
          ]
        : [];
      redrawLineEditor();
    };
    img.src = URL.createObjectURL(blob);
  } catch (err) {
    alert("Onizleme alinamadi: " + err.message);
  }
}

function redrawLineEditor() {
  if (!lineEditorState || !lineEditorState.img) return;
  const canvas = document.getElementById("gate-line-canvas");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(lineEditorState.img, 0, 0, canvas.width, canvas.height);

  const linePoints = lineEditorState.points.filter((p) => p.kind === "line");
  const insidePoint = lineEditorState.points.find((p) => p.kind === "inside");

  if (linePoints.length === 2) {
    ctx.strokeStyle = "#dc2626";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(linePoints[0].x, linePoints[0].y);
    ctx.lineTo(linePoints[1].x, linePoints[1].y);
    ctx.stroke();
  }
  linePoints.forEach((p) => {
    ctx.fillStyle = "#dc2626";
    ctx.beginPath();
    ctx.arc(p.x, p.y, 7, 0, Math.PI * 2);
    ctx.fill();
  });
  if (insidePoint) {
    ctx.fillStyle = "#16a34a";
    ctx.beginPath();
    ctx.arc(insidePoint.x, insidePoint.y, 9, 0, Math.PI * 2);
    ctx.fill();
  }
}

function setupGateLineEditor() {
  const canvas = document.getElementById("gate-line-canvas");
  canvas.addEventListener("click", (event) => {
    if (!lineEditorState || !lineEditorState.img) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = (event.clientX - rect.left) * scaleX;
    const y = (event.clientY - rect.top) * scaleY;

    const linePoints = lineEditorState.points.filter((p) => p.kind === "line");
    if (linePoints.length < 2) {
      // ilk iki tiklama: cizginin iki ucu
      lineEditorState.points = [...linePoints, { x, y, kind: "line" }];
    } else {
      // ucuncu ve sonraki tiklamalar: "icerisi" tarafini gunceller
      lineEditorState.points = [...linePoints, { x, y, kind: "inside" }];
    }
    redrawLineEditor();
  });

  document.getElementById("gate-line-refresh-btn").addEventListener("click", () => loadGateLinePreview());

  document.getElementById("gate-line-reset-btn").addEventListener("click", () => {
    if (!lineEditorState) return;
    lineEditorState.points = [];
    redrawLineEditor();
  });

  document.getElementById("gate-line-cancel-btn").addEventListener("click", () => {
    document.getElementById("gate-line-editor").style.display = "none";
    lineEditorState = null;
  });

  document.getElementById("gate-line-save-btn").addEventListener("click", async () => {
    if (!lineEditorState) return;
    const linePoints = lineEditorState.points.filter((p) => p.kind === "line");
    const insidePoint = lineEditorState.points.find((p) => p.kind === "inside");
    if (linePoints.length !== 2 || !insidePoint) {
      alert("Once cizginin iki ucuna, sonra icerisi tarafina tiklayin (toplam 3 tiklama)");
      return;
    }
    const canvas = document.getElementById("gate-line-canvas");
    try {
      await apiFetch(`/api/equipment/gates/${lineEditorState.gateId}/line`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          line_x1: linePoints[0].x / canvas.width,
          line_y1: linePoints[0].y / canvas.height,
          line_x2: linePoints[1].x / canvas.width,
          line_y2: linePoints[1].y / canvas.height,
          inside_x: insidePoint.x / canvas.width,
          inside_y: insidePoint.y / canvas.height,
        }),
      });
      alert("Cizgi kaydedildi. Etkili olmasi icin equipment-worker servisini yeniden baslatin (docker compose restart equipment-worker).");
      document.getElementById("gate-line-editor").style.display = "none";
      lineEditorState = null;
      loadGates();
    } catch (err) {
      alert(err.message);
    }
  });
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

function formatDuration(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.round((totalSeconds % 3600) / 60);
  if (hours > 0) return `${hours}s ${minutes}dk`;
  return `${minutes}dk`;
}

function equipmentLogQueryParams() {
  const params = new URLSearchParams();
  const from = document.getElementById("eq-log-from").value;
  const to = document.getElementById("eq-log-to").value;
  const zone = document.getElementById("eq-log-zone").value;
  const gate = document.getElementById("eq-log-gate").value;
  const plate = document.getElementById("eq-log-plate").value;
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  if (zone) params.set("zone_id", zone);
  if (gate) params.set("gate_id", gate);
  if (plate) params.set("plate_query", plate);
  return params;
}

async function loadEquipmentLogs() {
  const params = equipmentLogQueryParams();
  const rows = await apiFetch(`/api/equipment/logs?${params.toString()}`);
  const tbody = document.querySelector("#equipment-logs-table tbody");
  tbody.innerHTML = rows
    .map(
      (r) => `<tr>
        <td>${r.plate}</td>
        <td>${r.zone_name}</td>
        <td>${r.gate_name}</td>
        <td>${DIRECTION_LABELS[r.direction] || r.direction}</td>
        <td>${SOURCE_LABELS[r.source] || r.source}</td>
        <td>${new Date(r.created_at).toLocaleString("tr-TR")}</td>
      </tr>`
    )
    .join("");
}

async function loadEquipmentTimeReport() {
  const params = new URLSearchParams();
  const from = document.getElementById("eq-tr-from").value;
  const to = document.getElementById("eq-tr-to").value;
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);

  const entries = await apiFetch(`/api/equipment/time-report?${params.toString()}`);
  const tbody = document.querySelector("#equipment-time-report-table tbody");
  const rows = [];
  entries.forEach((entry) => {
    entry.breakdown.forEach((b, index) => {
      rows.push(`<tr>
        <td>${index === 0 ? entry.plate : ""}</td>
        <td>${b.zone_name}</td>
        <td>${formatDuration(b.duration_seconds)}</td>
      </tr>`);
    });
  });
  tbody.innerHTML = rows.join("") || `<tr><td colspan="3">Secilen aralikta kayit yok</td></tr>`;
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
    if ((data.events || []).length > 0) {
      loadEquipmentStatus();
      loadEquipmentLogs();
    }
  };
}
