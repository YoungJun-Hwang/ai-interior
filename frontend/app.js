import { Scene3D, ROOM_COLORS, footprint } from "./scene3d.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const ROOM_TYPES = {
  living: "거실", kitchen: "주방", dining: "식당", master_bedroom: "안방", bedroom: "침실", kids_room: "아이방",
  study: "서재", dressroom: "드레스룸", bathroom: "욕실", entrance: "현관", balcony: "발코니", utility: "다용도실",
  storage: "창고", hallway: "복도",
};
const PRESETS = {
  single: [{ role: "본인", age: 30 }],
  newlywed: [{ role: "남편", age: 33 }, { role: "아내", age: 31 }],
  kids: [{ role: "아빠", age: 40 }, { role: "엄마", age: 38 }, { role: "아들", age: 10 }, { role: "딸", age: 5 }],
  "three-gen": [{ role: "할머니", age: 74 }, { role: "아빠", age: 45 }, { role: "엄마", age: 43 }, { role: "딸", age: 13 }],
};
const QUICK_REQUESTS = ["냉장고", "세탁기", "건조기", "소파", "TV", "식탁", "침대", "책상", "옷장", "에어컨", "공기청정기", "스타일러"];

const state = {
  floorplan: null,
  planImage: null,     // data URL
  members: [],
  items: [],           // 사용자 제품
  requested: [],
  layout: null,        // {items, placements, summary, warnings, engine}
  selected: null,
};

// ---------- 공통 ----------
function toast(msg, ms = 4000) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
}
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(msg);
  }
  return res.json();
}
async function busy(btn, fn) {
  btn.disabled = true; btn.classList.add("spin");
  try { return await fn(); } catch (e) { toast(e.message, 7000); } finally { btn.disabled = false; btn.classList.remove("spin"); }
}
function fileToDataURL(file) {
  return new Promise((ok, err) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = err; r.readAsDataURL(file); });
}
function setupDrop(label, input, onFile) {
  label.addEventListener("dragover", (e) => { e.preventDefault(); label.classList.add("over"); });
  label.addEventListener("dragleave", () => label.classList.remove("over"));
  label.addEventListener("drop", (e) => {
    e.preventDefault(); label.classList.remove("over");
    if (e.dataTransfer.files[0]) { input.files = e.dataTransfer.files; onFile(e.dataTransfer.files[0]); }
  });
  input.addEventListener("change", () => input.files[0] && onFile(input.files[0]));
}

api("/api/status").then((s) => {
  const b = $("#ai-status");
  b.textContent = s.ai_enabled ? `AI 연결됨 · ${s.model}` : "AI 키 없음 · 규칙 엔진 모드";
  b.className = "badge " + (s.ai_enabled ? "on" : "off");
});

// ---------- 1. 도면 ----------
setupDrop($("#plan-drop"), $("#plan-file"), async (file) => {
  state.planImage = await fileToDataURL(file);
  $("#plan-preview").src = state.planImage; $("#plan-preview").hidden = false; $("#plan-drop-text").hidden = true;
});
$("#btn-analyze").onclick = (e) => busy(e.currentTarget, async () => {
  const file = $("#plan-file").files[0];
  if (!file) throw new Error("먼저 평면도 사진을 선택하세요.");
  const fd = new FormData(); fd.append("image", file); fd.append("hint", $("#plan-hint").value);
  setFloorplan(await api("/api/floorplan/analyze", { method: "POST", body: fd }));
  toast("도면 판독 완료. 치수가 맞는지 표에서 확인해 주세요.");
});
$("#btn-sample").onclick = (e) => busy(e.currentTarget, async () => {
  state.planImage = null;
  setFloorplan(await api("/api/floorplan/sample"));
});
$("#btn-add-room").onclick = () => {
  const fp = state.floorplan;
  fp.rooms.push({ id: "r" + Date.now().toString(36), name: "새 방", type: "bedroom", x: 0, y: fp.total_depth, width: 3000, depth: 3000 });
  fp.total_depth += 3000;
  renderRooms(); onPlanChanged();
};

function setFloorplan(fp) {
  state.floorplan = fp; state.layout = null; state.selected = null;
  $("#rooms-box").hidden = false; $("#rooms-box").open = true;
  $("#plan-meta").textContent = `${fp.name} · ${(fp.total_width / 1000).toFixed(1)}×${(fp.total_depth / 1000).toFixed(1)}m · 신뢰도 ${({ high: "높음", medium: "보통", low: "낮음" })[fp.confidence]}`;
  $("#plan-note").textContent = fp.scale_note || "";
  $("#result").hidden = true;
  renderRooms(); onPlanChanged();
}
function renderRooms() {
  const body = $("#rooms-body"); body.innerHTML = "";
  state.floorplan.rooms.forEach((r, i) => {
    const tr = document.createElement("tr");
    const opts = Object.entries(ROOM_TYPES).map(([k, v]) => `<option value="${k}" ${k === r.type ? "selected" : ""}>${v}</option>`).join("");
    tr.innerHTML = `<td><input data-k="name" value="${esc(r.name)}"></td><td><select data-k="type">${opts}</select></td>` +
      ["x", "y", "width", "depth"].map((k) => `<td><input data-k="${k}" type="number" step="50" value="${Math.round(r[k])}"></td>`).join("") +
      `<td><button title="삭제">×</button></td>`;
    tr.querySelectorAll("[data-k]").forEach((el) => el.addEventListener("change", () => {
      const k = el.dataset.k; r[k] = ["name", "type"].includes(k) ? el.value : Number(el.value);
      fitBounds(); onPlanChanged();
    }));
    tr.querySelector("button").onclick = () => { state.floorplan.rooms.splice(i, 1); renderRooms(); onPlanChanged(); };
    body.appendChild(tr);
  });
  const sel = $("#furn-room");
  sel.innerHTML = `<option value="">배치할 방: 자동</option>` + state.floorplan.rooms.map((r) => `<option value="${esc(r.id)}">${esc(r.name)}</option>`).join("");
}
function fitBounds() {
  const fp = state.floorplan;
  fp.total_width = Math.max(...fp.rooms.map((r) => r.x + r.width));
  fp.total_depth = Math.max(...fp.rooms.map((r) => r.y + r.depth));
}
function onPlanChanged() {
  $("#empty").hidden = !!state.floorplan;
  draw2D();
  scene.build(state.floorplan, state.layout, labelsOn());
}

// ---------- 2. 가족 ----------
function renderMembers() {
  $("#members").innerHTML = "";
  state.members.forEach((m, i) => {
    const c = document.createElement("span"); c.className = "chip";
    c.innerHTML = `${esc(m.role)}${m.age != null ? ` · ${m.age}세` : ""} <button>×</button>`;
    c.querySelector("button").onclick = () => { state.members.splice(i, 1); renderMembers(); };
    $("#members").appendChild(c);
  });
}
$("#family-presets").onclick = (e) => {
  const p = e.target.dataset.preset; if (!p) return;
  state.members = PRESETS[p].map((m) => ({ ...m })); renderMembers();
};
$("#btn-add-member").onclick = () => {
  const role = $("#member-role").value.trim(); if (!role) return;
  const age = $("#member-age").value === "" ? null : Number($("#member-age").value);
  state.members.push({ role, age }); $("#member-role").value = ""; $("#member-age").value = ""; renderMembers();
};

// ---------- 3. 가구 ----------
setupDrop($(".thumb-drop"), $("#furn-file"), async (file) => {
  $("#furn-preview").src = await fileToDataURL(file); $("#furn-preview").hidden = false; $("#furn-drop-text").hidden = true;
});
$("#btn-add-furn").onclick = (e) => busy(e.currentTarget, async () => {
  const fd = new FormData();
  const file = $("#furn-file").files[0];
  if (file) fd.append("image", file);
  fd.append("name", $("#furn-name").value.trim());
  for (const [k, id] of [["width", "#furn-w"], ["depth", "#furn-d"], ["height", "#furn-h"]]) if ($(id).value) fd.append(k, $(id).value);
  fd.append("preferred_room", $("#furn-room").value);
  if (!file && !$("#furn-name").value.trim()) throw new Error("제품 사진이나 이름을 입력하세요.");
  const item = await api("/api/furniture/analyze", { method: "POST", body: fd });
  state.items.push(item); renderItems();
  for (const id of ["#furn-name", "#furn-w", "#furn-d", "#furn-h"]) $(id).value = "";
  $("#furn-file").value = ""; $("#furn-preview").hidden = true; $("#furn-drop-text").hidden = false;
  toast(`'${item.name}' 등록: ${item.width}×${item.depth}×${item.height}mm${item.note ? " · " + item.note : ""}`);
});
function renderItems() {
  const ul = $("#furn-list"); ul.innerHTML = "";
  state.items.forEach((it, i) => {
    const li = document.createElement("li");
    li.innerHTML = `${it.image ? `<img src="${esc(it.image)}">` : `<div class="sw" style="background:${esc(it.color)}"></div>`}
      <div><div>${esc(it.name)}</div><div class="meta">${esc(it.category)} · ${it.width}×${it.depth}×${it.height}mm</div></div>
      <button>×</button>`;
    li.querySelector("button").onclick = () => { state.items.splice(i, 1); renderItems(); };
    ul.appendChild(li);
  });
}
function renderRequests() {
  const box = $("#request-chips"); box.innerHTML = "";
  for (const q of QUICK_REQUESTS) {
    const b = document.createElement("button"); b.textContent = (state.requested.includes(q) ? "✓ " : "+ ") + q;
    if (state.requested.includes(q)) b.classList.add("primary");
    b.onclick = () => { toggleRequest(q); };
    box.appendChild(b);
  }
  for (const q of state.requested.filter((q) => !QUICK_REQUESTS.includes(q))) {
    const c = document.createElement("span"); c.className = "chip"; c.innerHTML = `${esc(q)} <button>×</button>`;
    c.querySelector("button").onclick = () => toggleRequest(q);
    box.appendChild(c);
  }
}
function toggleRequest(q) {
  const i = state.requested.indexOf(q);
  i >= 0 ? state.requested.splice(i, 1) : state.requested.push(q);
  renderRequests();
}
$("#btn-add-request").onclick = () => {
  $("#request-input").value.split(",").map((s) => s.trim()).filter(Boolean).forEach((q) => state.requested.includes(q) || state.requested.push(q));
  $("#request-input").value = ""; renderRequests();
};
renderRequests();

// ---------- 4. 배치 ----------
$("#btn-layout").onclick = (e) => busy(e.currentTarget, async () => {
  if (!state.floorplan) throw new Error("먼저 도면을 준비하세요.");
  const body = {
    floorplan: state.floorplan, items: state.items, requested: state.requested, household: state.members,
    requirements: $("#requirements").value, style: $("#style").value, floorplan_image: state.planImage,
  };
  state.layout = await api(`/api/layout?engine=${$("#engine").value}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  state.selected = null;
  $("#result").hidden = false;
  $("#summary").textContent = (state.layout.engine === "ai" ? "🤖 AI 배치 · " : "📐 규칙 엔진 배치 · ") + state.layout.summary;
  $("#warnings").innerHTML = state.layout.warnings.map((w) => `<li>${esc(w)}</li>`).join("");
  onPlanChanged();
});

// ---------- 2D 배치도 ----------
const cv = $("#plan-canvas");
const ctx = cv.getContext("2d");
let view = { s: 0.05, ox: 40, oy: 40 };
let drag = null;

function itemsById() { return Object.fromEntries((state.layout?.items || []).map((i) => [i.id, i])); }

function draw2D() {
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  cv.width = w * dpr; cv.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const fp = state.floorplan; if (!fp) return;
  const pad = 50;
  const s = Math.min((w - pad * 2) / fp.total_width, (h - pad * 2) / fp.total_depth);
  view = { s, ox: (w - fp.total_width * s) / 2, oy: (h - fp.total_depth * s) / 2 };
  const X = (x) => view.ox + x * s, Y = (y) => view.oy + y * s;

  for (const r of fp.rooms) {
    ctx.fillStyle = ROOM_COLORS[r.type] || "#eee";
    ctx.fillRect(X(r.x), Y(r.y), r.width * s, r.depth * s);
  }
  ctx.strokeStyle = "#3b352f"; ctx.lineWidth = 3;
  for (const r of fp.rooms) ctx.strokeRect(X(r.x), Y(r.y), r.width * s, r.depth * s);
  for (const o of fp.openings) {
    ctx.lineWidth = 5;
    ctx.strokeStyle = o.kind === "window" ? "#7fb3d5" : o.kind === "opening" ? (ROOM_COLORS.hallway) : "#fff";
    ctx.beginPath(); ctx.moveTo(X(o.x1), Y(o.y1)); ctx.lineTo(X(o.x2), Y(o.y2)); ctx.stroke();
    if (o.kind === "door") {
      ctx.lineWidth = 1; ctx.strokeStyle = "#c08a5a";
      ctx.beginPath(); ctx.moveTo(X(o.x1), Y(o.y1)); ctx.lineTo(X(o.x2), Y(o.y2)); ctx.stroke();
    }
  }
  // 방 이름
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  for (const r of fp.rooms) {
    ctx.fillStyle = "rgba(60,52,45,.55)"; ctx.font = "600 13px sans-serif";
    ctx.fillText(r.name, X(r.x + r.width / 2), Y(r.y) + 14);
    ctx.font = "11px sans-serif";
    ctx.fillText(`${(r.width / 1000).toFixed(1)}×${(r.depth / 1000).toFixed(1)}m`, X(r.x + r.width / 2), Y(r.y) + 28);
  }
  // 가구
  if (!state.layout) return;
  const byId = itemsById();
  const rects = state.layout.placements.map((p) => {
    const it = byId[p.item_id]; const [fw, fd] = footprint(it, p.rotation);
    return { p, it, x1: p.x - fw / 2, y1: p.y - fd / 2, x2: p.x + fw / 2, y2: p.y + fd / 2 };
  });
  // 겹쳐도 되는 조합: 거실장 위 TV, 세탁기 위 건조기, 식탁/책상 아래로 넣은 의자, 러그
  const STACK = ["tv|tv_stand", "dryer|washing_machine", "chair|dining_table", "chair|kitchen_island", "chair|desk", "office_chair|desk"];
  const stack = (a, b) => [a, b].includes("rug") || STACK.includes(`${a}|${b}`) || STACK.includes(`${b}|${a}`);
  const order = [...rects].sort((a, b) => (a.it.category === "rug" ? -1 : 0) - (b.it.category === "rug" ? -1 : 0));
  for (const r of order) {
    const clash = rects.some((o) => o !== r && !stack(o.it.category, r.it.category) &&
      r.x1 < o.x2 - 30 && o.x1 < r.x2 - 30 && r.y1 < o.y2 - 30 && o.y1 < r.y2 - 30);
    ctx.globalAlpha = r.it.category === "rug" ? 0.45 : 0.92;
    ctx.fillStyle = r.it.color;
    ctx.fillRect(X(r.x1), Y(r.y1), (r.x2 - r.x1) * s, (r.y2 - r.y1) * s);
    ctx.globalAlpha = 1;
    ctx.lineWidth = state.selected === r.p.item_id ? 3 : 1;
    ctx.strokeStyle = clash ? "#d0342c" : state.selected === r.p.item_id ? "#b5663d" : "rgba(0,0,0,.45)";
    ctx.strokeRect(X(r.x1), Y(r.y1), (r.x2 - r.x1) * s, (r.y2 - r.y1) * s);
    // 정면 표시
    const f = { 0: [0, 1], 90: [1, 0], 180: [0, -1], 270: [-1, 0] }[r.p.rotation];
    const [fw, fd] = [(r.x2 - r.x1) / 2, (r.y2 - r.y1) / 2];
    ctx.strokeStyle = "rgba(255,255,255,.9)"; ctx.lineWidth = 2; ctx.beginPath();
    if (f[1]) { ctx.moveTo(X(r.p.x - fw * .6), Y(r.p.y + f[1] * fd) - f[1] * 3); ctx.lineTo(X(r.p.x + fw * .6), Y(r.p.y + f[1] * fd) - f[1] * 3); }
    else { ctx.moveTo(X(r.p.x + f[0] * fw) - f[0] * 3, Y(r.p.y - fd * .6)); ctx.lineTo(X(r.p.x + f[0] * fw) - f[0] * 3, Y(r.p.y + fd * .6)); }
    ctx.stroke();
  }
  ctx.font = "11px sans-serif"; ctx.fillStyle = "#1f1b17";
  for (const r of rects) {
    if (r.it.category === "rug" || r.it.category === "tv" || r.it.category === "dryer") continue;
    if ((r.x2 - r.x1) * s < 34) continue;
    const label = r.it.name.length > 8 ? r.it.name.slice(0, 8) + "…" : r.it.name;
    ctx.fillStyle = "rgba(255,255,255,.8)";
    const tw = ctx.measureText(label).width + 6;
    ctx.fillRect(X(r.p.x) - tw / 2, Y(r.p.y) - 8, tw, 16);
    ctx.fillStyle = "#1f1b17"; ctx.fillText(label, X(r.p.x), Y(r.p.y));
  }
}

function hit(mx, my) {
  if (!state.layout) return null;
  const byId = itemsById();
  const x = (mx - view.ox) / view.s, y = (my - view.oy) / view.s;
  const ps = [...state.layout.placements].reverse().sort((a, b) => (byId[a.item_id].category === "rug") - (byId[b.item_id].category === "rug"));
  return ps.find((p) => {
    const [fw, fd] = footprint(byId[p.item_id], p.rotation);
    return Math.abs(x - p.x) <= fw / 2 && Math.abs(y - p.y) <= fd / 2;
  }) || null;
}
cv.addEventListener("mousedown", (e) => {
  const p = hit(e.offsetX, e.offsetY);
  state.selected = p?.item_id || null;
  if (p) drag = { p, dx: (e.offsetX - view.ox) / view.s - p.x, dy: (e.offsetY - view.oy) / view.s - p.y };
  draw2D();
});
cv.addEventListener("mousemove", (e) => {
  cv.style.cursor = hit(e.offsetX, e.offsetY) ? "move" : "default";
  if (!drag) return;
  const snap = (v) => Math.round(v / 50) * 50;
  drag.p.x = snap((e.offsetX - view.ox) / view.s - drag.dx);
  drag.p.y = snap((e.offsetY - view.oy) / view.s - drag.dy);
  const room = state.floorplan.rooms.find((r) => drag.p.x >= r.x && drag.p.x <= r.x + r.width && drag.p.y >= r.y && drag.p.y <= r.y + r.depth);
  if (room) drag.p.room_id = room.id;
  draw2D();
});
window.addEventListener("mouseup", () => { if (drag) { drag = null; scene.build(state.floorplan, state.layout, labelsOn()); } });
window.addEventListener("keydown", (e) => {
  if (!state.selected || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
  const pl = state.layout.placements;
  if (e.key === "r" || e.key === "R") { const p = pl.find((p) => p.item_id === state.selected); p.rotation = (p.rotation + 90) % 360; }
  else if (e.key === "Delete" || e.key === "Backspace") { state.layout.placements = pl.filter((p) => p.item_id !== state.selected); state.selected = null; }
  else return;
  onPlanChanged();
});
window.addEventListener("resize", draw2D);

// ---------- 탭 / 3D / 영상 ----------
const scene = new Scene3D($("#three-wrap"));
const labelsOn = () => $("#opt-labels").checked;
$("#opt-labels").onchange = () => scene.build(state.floorplan, state.layout, labelsOn());

document.querySelectorAll(".tabs button").forEach((b) => b.onclick = () => {
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  for (const id of ["plan2d", "view3d"]) $("#tab-" + id).hidden = id !== b.dataset.tab;
  if (b.dataset.tab === "view3d") scene.resize(); else draw2D();
});

function tourMeta() {
  const byId = itemsById();
  return { title: state.floorplan?.name || "우리 집", summary: state.layout?.summary || "", byId,
    members: state.members.map((m) => m.role).join(" · ") };
}
$("#btn-play").onclick = () => {
  if (!state.floorplan) return toast("먼저 도면을 준비하세요.");
  scene.play(tourMeta());
};
let lastWebm = null;
$("#btn-record").onclick = (e) => busy(e.currentTarget, async () => {
  if (!state.layout) throw new Error("먼저 배치를 만들어 주세요.");
  $("#rec-status").textContent = "녹화 중… 끝날 때까지 이 탭을 열어 두세요.";
  const blob = await scene.record(tourMeta(), (p) => ($("#rec-status").textContent = `녹화 중… ${Math.round(p * 100)}%`));
  lastWebm = blob;
  const url = URL.createObjectURL(blob);
  $("#video").src = url; $("#dl-webm").href = url; $("#video-out").hidden = false;
  $("#rec-status").textContent = `완료 · ${(blob.size / 1024 / 1024).toFixed(1)}MB`;
});
$("#btn-mp4").onclick = (e) => busy(e.currentTarget, async () => {
  if (!lastWebm) return;
  const fd = new FormData(); fd.append("video", lastWebm, "interior.webm");
  const res = await fetch("/api/video/convert", { method: "POST", body: fd });
  if (!res.ok) throw new Error((await res.json()).detail || "변환 실패");
  const a = document.createElement("a"); a.href = URL.createObjectURL(await res.blob()); a.download = "interior.mp4"; a.click();
});

// 테스트/디버깅용
window.__app = { state, scene, setFloorplan };
