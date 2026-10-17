import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js";

export const ROOM_COLORS = {
  living: "#efe4d2", kitchen: "#e8e6e1", dining: "#ece3d4", master_bedroom: "#eadfce", bedroom: "#ebe2d3",
  kids_room: "#f0e3cf", study: "#e9dfcf", dressroom: "#ece4d8", bathroom: "#dfe7ea", entrance: "#e2ddd6",
  balcony: "#dcdcd8", utility: "#dedbd5", storage: "#e1ddd6", hallway: "#ebe3d6",
};
const WOOD = new Set(["living", "dining", "master_bedroom", "bedroom", "kids_room", "study", "dressroom", "hallway"]);
const M = 0.001; // mm → m

export function footprint(item, rot) {
  return rot === 90 || rot === 270 ? [item.depth, item.width] : [item.width, item.depth];
}

const ease = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));
const easeOutBack = (t) => { const c = 1.4; t = Math.min(1, Math.max(0, t)); return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2; };

// ---------- 재질 ----------
function woodTexture(base = "#c9a77c") {
  const c = document.createElement("canvas"); c.width = 512; c.height = 512;
  const g = c.getContext("2d");
  g.fillStyle = base; g.fillRect(0, 0, 512, 512);
  const plankH = 64;
  for (let y = 0; y < 512; y += plankH) {
    const off = (y / plankH) % 2 ? 180 : 0;
    for (let x = -off; x < 512; x += 360) {
      const l = 0.9 + Math.random() * 0.2;
      g.fillStyle = `rgba(${l > 1 ? 255 : 0},${l > 1 ? 240 : 0},${l > 1 ? 220 : 0},${Math.abs(l - 1) * 0.6})`;
      g.fillRect(x, y, 360, plankH);
      g.strokeStyle = "rgba(80,50,20,.25)"; g.strokeRect(x + .5, y + .5, 360, plankH);
    }
    for (let i = 0; i < 6; i++) {
      g.strokeStyle = "rgba(90,60,30,.08)"; g.beginPath();
      const yy = y + Math.random() * plankH; g.moveTo(0, yy); g.bezierCurveTo(170, yy + 6, 340, yy - 6, 512, yy); g.stroke();
    }
  }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
function tileTexture(base = "#e7e6e2") {
  const c = document.createElement("canvas"); c.width = 256; c.height = 256;
  const g = c.getContext("2d"); g.fillStyle = base; g.fillRect(0, 0, 256, 256);
  g.strokeStyle = "rgba(0,0,0,.12)"; g.lineWidth = 2;
  for (let i = 0; i <= 256; i += 128) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, 256); g.moveTo(0, i); g.lineTo(256, i); g.stroke(); }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
function labelSprite(text, scale = 1) {
  const c = document.createElement("canvas"); const g = c.getContext("2d");
  g.font = "600 44px sans-serif"; const w = g.measureText(text).width + 40;
  c.width = w; c.height = 72;
  g.font = "600 44px sans-serif"; g.fillStyle = "rgba(255,255,255,.88)";
  g.beginPath(); g.roundRect(0, 0, w, 72, 30); g.fill();
  g.fillStyle = "#2a241e"; g.textBaseline = "middle"; g.fillText(text, 20, 38);
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
  s.scale.set((w / 72) * 0.28 * scale, 0.28 * scale, 1); s.renderOrder = 10;
  return s;
}

// ---------- 가구 모델 (로컬 좌표: 폭=X, 깊이=Z, 정면=+Z, 단위 m) ----------
function mat(color, opts = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.75, metalness: 0, ...opts });
}
function box(w, h, d, material, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(Math.max(w, 0.005), Math.max(h, 0.005), Math.max(d, 0.005)), material);
  m.position.set(x, y + h / 2, z); m.castShadow = true; m.receiveShadow = true;
  return m;
}
function legs(g, w, d, h, material, t = 0.04, inset = 0.04) {
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(box(t, h, t, material, sx * (w / 2 - inset), 0, sz * (d / 2 - inset)));
}
function shade(hex, k) { const c = new THREE.Color(hex); c.offsetHSL(0, 0, k); return c; }

function buildFurniture(item) {
  const g = new THREE.Group();
  const w = item.width * M, d = item.depth * M, h = item.height * M;
  const base = mat(item.color);
  const dark = mat(shade(item.color, -0.15));
  const light = mat(shade(item.color, 0.12));
  const white = mat("#f7f5f0");
  const metal = mat(item.color, { metalness: 0.35, roughness: 0.35 });
  switch (item.category) {
    case "bed": case "crib": {
      const frameH = item.category === "crib" ? 0.35 : Math.min(0.35, h * 0.35);
      g.add(box(w, frameH, d, base));
      g.add(box(w - 0.06, 0.22, d - 0.1, white, 0, frameH, 0.03));
      g.add(box(w, h, 0.08, dark, 0, 0, -d / 2 + 0.04));
      const pw = Math.min(0.6, (w - 0.2) / 2);
      for (const sx of w > 1.3 ? [-1, 1] : [0]) g.add(box(pw, 0.12, 0.38, mat("#ffffff"), sx * (pw / 2 + 0.05), frameH + 0.22, -d / 2 + 0.32));
      g.add(box(w - 0.04, 0.05, d * 0.55, mat(shade(item.color, 0.25)), 0, frameH + 0.22, d * 0.2));
      if (item.category === "crib") for (let i = -4; i <= 4; i++) {
        g.add(box(0.02, 0.5, 0.02, base, (i / 4.4) * (w / 2), frameH, d / 2 - 0.02));
        g.add(box(0.02, 0.5, 0.02, base, (i / 4.4) * (w / 2), frameH, -d / 2 + 0.02));
      }
      break;
    }
    case "sofa": case "armchair": {
      const seatH = 0.42, arm = Math.min(0.2, w * 0.12), backD = Math.min(0.25, d * 0.3);
      g.add(box(w, seatH - 0.1, d, dark, 0, 0.1));
      legs(g, w, d, 0.1, mat("#3a2f26"), 0.04);
      const n = Math.max(1, Math.round((w - 2 * arm) / 0.75));
      const cw = (w - 2 * arm) / n;
      for (let i = 0; i < n; i++) {
        const x = -w / 2 + arm + cw * (i + 0.5);
        g.add(box(cw - 0.02, 0.14, d - backD - 0.02, base, x, seatH, backD / 2));
        g.add(box(cw - 0.02, h - seatH - 0.04, 0.18, light, x, seatH, -d / 2 + backD + 0.05));
      }
      g.add(box(w, h - 0.1, backD, dark, 0, 0.1, -d / 2 + backD / 2));
      for (const sx of [-1, 1]) g.add(box(arm, 0.62 - 0.1, d, dark, sx * (w / 2 - arm / 2), 0.1));
      break;
    }
    case "dining_table": case "desk": case "coffee_table": case "side_table": {
      const top = item.category === "side_table" ? 0.03 : 0.04;
      g.add(box(w, top, d, base, 0, h - top));
      if (item.category === "side_table") g.add(box(w - 0.04, h - top - 0.1, d - 0.04, dark, 0, 0.1));
      legs(g, w, d, h - top, dark, item.category === "coffee_table" ? 0.05 : 0.045);
      if (item.category === "desk") g.add(box(0.4, 0.5, d - 0.06, light, w / 2 - 0.22, 0.12));
      break;
    }
    case "kitchen_island": {
      g.add(box(w, h - 0.04, d - 0.08, base, 0, 0, -0.04));
      g.add(box(w + 0.04, 0.04, d, white, 0, h - 0.04));
      break;
    }
    case "chair": case "office_chair": {
      const seat = 0.45;
      if (item.category === "office_chair") {
        g.add(box(0.06, seat - 0.05, 0.06, mat("#222"), 0, 0.05));
        g.add(box(w * 0.9, 0.05, 0.08, mat("#222"))); g.add(box(0.08, 0.05, d * 0.9, mat("#222")));
      } else legs(g, w * 0.9, d * 0.9, seat, dark, 0.035);
      g.add(box(w * 0.9, 0.06, d * 0.85, base, 0, seat));
      g.add(box(w * 0.9, h - seat - 0.06, 0.05, base, 0, seat + 0.06, -d / 2 + 0.08));
      break;
    }
    case "wardrobe": case "shoe_cabinet": case "storage_cabinet": case "dresser": case "tv_stand": {
      g.add(box(w, h, d, base));
      const doors = Math.max(1, Math.round(w / (item.category === "tv_stand" ? 0.6 : 0.45)));
      for (let i = 0; i < doors; i++) {
        const x = -w / 2 + (w / doors) * (i + 0.5);
        g.add(box(w / doors - 0.01, h - 0.04, 0.01, light, x, 0.02, d / 2 + 0.005));
        g.add(box(0.015, Math.min(0.25, h * 0.3), 0.02, mat("#8c8c8c", { metalness: .6 }), x + (i % 2 ? -1 : 1) * (w / doors / 2 - 0.04), h * 0.45, d / 2 + 0.015));
      }
      if (item.category === "dresser") g.add(box(w * 0.6, 0.6, 0.02, mat("#cfe3ea", { metalness: .8, roughness: .1 }), 0, h, -d / 2 + 0.05));
      break;
    }
    case "bookshelf": {
      g.add(box(w, h, 0.02, dark, 0, 0, -d / 2 + 0.01));
      for (const sx of [-1, 1]) g.add(box(0.02, h, d, base, sx * (w / 2 - 0.01)));
      const shelves = Math.max(2, Math.round(h / 0.35));
      for (let i = 0; i <= shelves; i++) {
        const y = (h - 0.02) * (i / shelves);
        g.add(box(w, 0.02, d, base, 0, y));
        if (i < shelves) for (let b = 0; b < 6; b++) {
          const bw = 0.03 + Math.random() * 0.04, bh = 0.18 + Math.random() * 0.1;
          g.add(box(bw, bh, d * 0.7, mat(["#8a5a44", "#46617a", "#c4a25a", "#6d7d5c", "#a33"][b % 5]),
            -w / 2 + 0.06 + b * (w - 0.1) / 6, y + 0.02, 0));
        }
      }
      break;
    }
    case "refrigerator": case "kimchi_fridge": case "styler": {
      g.add(box(w, h, d, metal));
      const split = item.category === "refrigerator" ? [[-w / 4, w / 2 - 0.01, 0, h]] :
        item.category === "kimchi_fridge" ? [[0, w - 0.01, 0, h * 0.45], [0, w - 0.01, h * 0.47, h * 0.53]] : [[0, w - 0.01, 0, h]];
      if (item.category === "refrigerator") split.push([w / 4, w / 2 - 0.01, 0, h]);
      for (const [x, ww, y0, hh] of split) g.add(box(ww, hh - 0.02, 0.01, mat(shade(item.color, 0.05), { metalness: .3, roughness: .3 }), x, y0 + 0.01, d / 2 + 0.005));
      break;
    }
    case "washing_machine": case "dryer": {
      g.add(box(w, h, d, white));
      const door = new THREE.Mesh(new THREE.CylinderGeometry(w * 0.3, w * 0.3, 0.03, 32), mat("#5d6770", { metalness: .5, roughness: .2 }));
      door.rotation.x = Math.PI / 2; door.position.set(0, h * 0.45, d / 2 + 0.015); g.add(door);
      g.add(box(w - 0.04, 0.1, 0.01, mat("#ddd"), 0, h - 0.13, d / 2 + 0.005));
      break;
    }
    case "tv": {
      g.add(box(w, h, Math.min(d, 0.05), mat("#111", { roughness: .3 })));
      g.add(box(w - 0.03, h - 0.03, 0.005, mat("#1d2a3a", { roughness: .1, metalness: .2, emissive: "#0c1724" }), 0, 0.015, Math.min(d, 0.05) / 2 + 0.003));
      break;
    }
    case "air_conditioner": case "air_purifier": {
      g.add(box(w, h, d, white));
      g.add(box(w * 0.8, h * 0.15, 0.01, mat("#cfd6db"), 0, h * 0.7, d / 2 + 0.005));
      break;
    }
    case "plant": {
      const pot = new THREE.Mesh(new THREE.CylinderGeometry(w * 0.32, w * 0.25, h * 0.3, 20), mat("#d8cbb8"));
      pot.position.y = h * 0.15; pot.castShadow = true; g.add(pot);
      for (let i = 0; i < 5; i++) {
        const leaf = new THREE.Mesh(new THREE.SphereGeometry(w * (0.28 + Math.random() * 0.12), 12, 10), mat(shade("#4f7a4a", (Math.random() - .5) * .1)));
        leaf.position.set((Math.random() - .5) * w * 0.4, h * (0.5 + i * 0.1), (Math.random() - .5) * d * 0.4);
        leaf.castShadow = true; g.add(leaf);
      }
      break;
    }
    case "lamp": {
      g.add(box(w * 0.6, 0.03, d * 0.6, dark));
      g.add(box(0.03, h - 0.3, 0.03, dark, 0, 0.03));
      const s = new THREE.Mesh(new THREE.CylinderGeometry(w * 0.3, w * 0.45, 0.3, 24, 1, true), mat("#f4e8c8", { emissive: "#6b5a2a", side: THREE.DoubleSide }));
      s.position.y = h - 0.15; g.add(s);
      break;
    }
    case "rug": {
      const r = new THREE.Mesh(new THREE.BoxGeometry(w, 0.012, d), base); r.position.y = 0.006; r.receiveShadow = true; g.add(r);
      break;
    }
    case "piano": {
      g.add(box(w, h, d * 0.6, base, 0, 0, -d * 0.2));
      g.add(box(w, 0.1, d * 0.4, base, 0, 0.68, d * 0.3));
      g.add(box(w - 0.1, 0.02, 0.15, white, 0, 0.78, d * 0.25));
      break;
    }
    case "pet_house": {
      g.add(box(w, h * 0.65, d, base));
      const roof = new THREE.Mesh(new THREE.CylinderGeometry(0.001, w * 0.72, h * 0.35, 4, 1), dark);
      roof.rotation.y = Math.PI / 4; roof.position.y = h * 0.65 + h * 0.175; roof.scale.z = d / w; g.add(roof);
      const hole = new THREE.Mesh(new THREE.CircleGeometry(Math.min(w, h) * 0.2, 20), mat("#2a211a"));
      hole.position.set(0, h * 0.28, d / 2 + 0.002); g.add(hole);
      break;
    }
    default:
      g.add(box(w, h, d, base));
  }
  return g;
}

// ---------- 벽 ----------
function mergeIntervals(list) {
  list.sort((a, b) => a[0] - b[0]);
  const out = [];
  for (const [a, b] of list) {
    if (out.length && a <= out[out.length - 1][1] + 1) out[out.length - 1][1] = Math.max(out[out.length - 1][1], b);
    else out.push([a, b]);
  }
  return out;
}
/** 방 경계선을 모아 중복을 합친 벽 선분 목록. {axis:'h'|'v', c: 고정좌표, a, b} */
function wallSegments(fp) {
  const lines = { h: new Map(), v: new Map() };
  const key = (v) => Math.round(v / 10) * 10;
  for (const r of fp.rooms) {
    for (const y of [r.y, r.y + r.depth]) { const k = key(y); (lines.h.get(k) || lines.h.set(k, []).get(k)).push([r.x, r.x + r.width]); }
    for (const x of [r.x, r.x + r.width]) { const k = key(x); (lines.v.get(k) || lines.v.set(k, []).get(k)).push([r.y, r.y + r.depth]); }
  }
  const segs = [];
  for (const axis of ["h", "v"]) for (const [c, list] of lines[axis]) for (const [a, b] of mergeIntervals(list)) segs.push({ axis, c, a, b });
  return segs;
}

export class Scene3D {
  constructor(container) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    container.appendChild(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color("#e9e6e1");
    this.camera = new THREE.PerspectiveCamera(45, 16 / 9, 0.1, 200);
    this.camera.position.set(8, 14, 16);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.maxPolarAngle = Math.PI / 2.1;
    this.scene.add(new THREE.HemisphereLight("#ffffff", "#b9ab98", 1.4));
    this.sun = new THREE.DirectionalLight("#fff4e0", 2.2);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    this.sun.shadow.bias = -0.0005;
    this.scene.add(this.sun, this.sun.target);
    this.root = new THREE.Group(); this.scene.add(this.root);
    this.woodTex = woodTexture(); this.tileTex = tileTexture();
    this.anim = null; // 재생 중인 타임라인
    this.overlay = null;
    new ResizeObserver(() => this.resize()).observe(container);
    this.resize();
    this.renderer.setAnimationLoop(() => this.frame());
  }

  resize() {
    const w = this.container.clientWidth || 800, h = this.container.clientHeight || 450;
    if (this.fixedSize) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }

  clear() {
    this.root.traverse((o) => { o.geometry?.dispose?.(); });
    this.scene.remove(this.root); this.root = new THREE.Group(); this.scene.add(this.root);
  }

  build(fp, layout, showLabels = true) {
    this.clear();
    this.fp = fp; this.layout = layout; this.walls = []; this.furniture = []; this.roomLabels = [];
    if (!fp) return;
    const W = fp.total_width * M, D = fp.total_depth * M, H = (fp.ceiling_height || 2300) * M;
    this.center = new THREE.Vector3(W / 2, 0, D / 2);
    this.size = Math.max(W, D);

    const ground = new THREE.Mesh(new THREE.PlaneGeometry(W + 30, D + 30), mat("#d9d4cc"));
    ground.rotation.x = -Math.PI / 2; ground.position.set(W / 2, -0.01, D / 2); ground.receiveShadow = true;
    this.root.add(ground);

    for (const r of fp.rooms) {
      const wood = WOOD.has(r.type);
      const tex = (wood ? this.woodTex : this.tileTex).clone(); tex.needsUpdate = true;
      tex.repeat.set((r.width * M) / (wood ? 2.4 : 1.2), (r.depth * M) / (wood ? 2.4 : 1.2));
      const floor = new THREE.Mesh(new THREE.PlaneGeometry(r.width * M, r.depth * M),
        mat(wood ? "#ffffff" : ROOM_COLORS[r.type] || "#ddd", { map: tex, roughness: wood ? 0.6 : 0.4 }));
      floor.rotation.x = -Math.PI / 2; floor.position.set((r.x + r.width / 2) * M, 0.001, (r.y + r.depth / 2) * M);
      floor.receiveShadow = true; this.root.add(floor);
      if (showLabels) {
        const s = labelSprite(r.name, 1.3); s.position.set((r.x + r.width / 2) * M, H + 0.5, (r.y + r.depth / 2) * M);
        this.root.add(s); this.roomLabels.push(s);
      }
    }

    // 벽 + 개구부
    const wallMat = mat("#fbfaf7", { roughness: 0.9 });
    const glass = new THREE.MeshStandardMaterial({ color: "#bcd8e6", transparent: true, opacity: 0.35, roughness: 0.05, metalness: 0.1 });
    const T = 0.12;
    for (const seg of wallSegments(fp)) {
      const ops = fp.openings.map((o) => {
        const horiz = Math.abs(o.y2 - o.y1) < Math.abs(o.x2 - o.x1);
        if ((seg.axis === "h") !== horiz) return null;
        const c = horiz ? (o.y1 + o.y2) / 2 : (o.x1 + o.x2) / 2;
        if (Math.abs(c - seg.c) > 150) return null;
        const a = Math.max(seg.a, Math.min(horiz ? o.x1 : o.y1, horiz ? o.x2 : o.y2));
        const b = Math.min(seg.b, Math.max(horiz ? o.x1 : o.y1, horiz ? o.x2 : o.y2));
        return b - a > 100 ? { a, b, kind: o.kind } : null;
      }).filter(Boolean).sort((p, q) => p.a - q.a);
      const pieces = []; let cur = seg.a;
      for (const o of ops) { if (o.a > cur) pieces.push({ a: cur, b: o.a }); pieces.push(o); cur = Math.max(cur, o.b); }
      if (cur < seg.b) pieces.push({ a: cur, b: seg.b });
      for (const p of pieces) {
        const len = (p.b - p.a) * M, mid = ((p.a + p.b) / 2) * M;
        const add = (y0, y1, material = wallMat, thick = T) => {
          if (y1 - y0 <= 0.001) return;
          const m = box(seg.axis === "h" ? len : thick, y1 - y0, seg.axis === "h" ? thick : len, material);
          if (seg.axis === "h") m.position.set(mid, y0 + (y1 - y0) / 2, seg.c * M); else m.position.set(seg.c * M, y0 + (y1 - y0) / 2, mid);
          this.root.add(m); this.walls.push(m);
          if (material === glass) { m.castShadow = false; }
        };
        if (!p.kind) add(0, H);
        else if (p.kind === "window") { add(0, 0.9); add(0.9, 2.1, glass, 0.02); add(2.1, H); }
        else if (p.kind === "sliding_door") { add(0, 2.2, glass, 0.02); add(2.2, H); }
        else add(2.1, H);
      }
    }

    // 가구
    if (layout) {
      const byId = Object.fromEntries(layout.items.map((i) => [i.id, i]));
      const placed = layout.placements.filter((p) => byId[p.item_id]);
      for (const p of placed) {
        const item = byId[p.item_id];
        const g = buildFurniture(item);
        let elev = 0;
        const under = (cat) => placed.find((q) => byId[q.item_id].category === cat && Math.hypot(q.x - p.x, q.y - p.y) < 600);
        if (item.category === "tv") { const st = under("tv_stand"); elev = st ? byId[st.item_id].height * M : 1.0; }
        if (item.category === "dryer") { const wm = under("washing_machine"); elev = wm ? byId[wm.item_id].height * M : 0; }
        g.position.set(p.x * M, elev, p.y * M);
        g.rotation.y = (p.rotation * Math.PI) / 180;
        g.userData = { item, placement: p, elev };
        this.root.add(g);
        if (showLabels && !["rug", "tv", "dryer", "chair"].includes(item.category)) {
          const s = labelSprite(item.name, 0.75); s.position.set(0, item.height * M + 0.25, 0);
          s.userData.isLabel = true; g.add(s);
        }
        this.furniture.push(g);
      }
      // 방 순서대로 등장하도록 정렬
      const roomOrder = Object.fromEntries(fp.rooms.map((r, i) => [r.id, i]));
      this.furniture.sort((a, b) => (roomOrder[a.userData.placement.room_id] ?? 99) - (roomOrder[b.userData.placement.room_id] ?? 99)
        || (a.userData.elev - b.userData.elev) || (a.userData.item.category === "rug" ? -1 : 0));
    }

    this.sun.position.set(W / 2 + 6, 14, D + 8);
    this.sun.target.position.set(W / 2, 0, D / 2);
    const sc = this.sun.shadow.camera; const ext = this.size * 0.8 + 2;
    sc.left = -ext; sc.right = ext; sc.top = ext; sc.bottom = -ext; sc.far = 60; sc.updateProjectionMatrix();
    if (!this.anim) this.homeView();
  }

  homeView() {
    if (!this.center) return;
    this.controls.target.copy(this.center);
    this.camera.position.set(this.center.x, this.size * 1.15, this.center.z + this.size * 0.85);
    this.controls.update();
  }

  // ---------- 영상 타임라인 ----------
  timeline(meta) {
    const fp = this.fp; const keys = [];
    const c = this.center, S = this.size;
    const over = (ang, dist, height) => ({
      pos: new THREE.Vector3(c.x + Math.sin(ang) * dist, height, c.z + Math.cos(ang) * dist), target: c.clone(),
    });
    const intro = 3.5;
    const nF = this.furniture.length;
    const per = nF ? Math.min(0.35, 9 / nF) : 0;
    const build = nF * per + 1.0;
    // 가구가 놓인 주요 공간만 돌아본다
    const tourRooms = fp.rooms.filter((r) => !["hallway", "balcony", "entrance", "storage", "bathroom"].includes(r.type)
      && this.furniture.some((f) => f.userData.placement.room_id === r.id));
    const hold = 2.6, move = 1.4;
    const shots = [];
    let t = 0;
    shots.push({ t0: 0, t1: intro, from: over(-0.6, S * 1.2, S * 1.4), to: over(-0.2, S * 0.95, S * 1.05), caption: meta.title, sub: meta.members, overview: true });
    t = intro;
    shots.push({ t0: t, t1: t + build, from: over(-0.2, S * 0.95, S * 1.05), to: over(0.35, S * 0.9, S * 0.9), caption: "가구 배치", sub: "", overview: true });
    t += build;
    let prev = over(0.35, S * 0.9, S * 0.9);
    for (const r of tourRooms) {
      const rc = new THREE.Vector3((r.x + r.width / 2) * M, 0.5, (r.y + r.depth / 2) * M);
      const span = Math.max(3.5, Math.max(r.width, r.depth) * M);
      // 방 남쪽(아래)에서 비스듬히 내려다보기
      const pos = new THREE.Vector3(rc.x + span * 0.15, 2.3 + span * 0.85, rc.z + span * 0.75);
      const shot = { pos, target: rc };
      const items = this.furniture.filter((f) => f.userData.placement.room_id === r.id).map((f) => f.userData.item.name);
      shots.push({ t0: t, t1: t + move, from: prev, to: shot, caption: r.name, sub: "" });
      shots.push({ t0: t + move, t1: t + move + hold, from: shot, to: { pos: pos.clone().add(new THREE.Vector3(-span * 0.25, -0.2, -0.1)), target: rc },
        caption: r.name, sub: items.slice(0, 5).join(" · ") + (items.length > 5 ? ` 외 ${items.length - 5}개` : ""), dims: `${(r.width / 1000).toFixed(1)} × ${(r.depth / 1000).toFixed(1)} m` });
      prev = { pos: shots[shots.length - 1].to.pos, target: rc };
      t += move + hold;
    }
    const outro = 4.5;
    shots.push({ t0: t, t1: t + outro, from: prev, to: over(0.9, S * 1.1, S * 1.25), caption: "완성", sub: (meta.summary || "").slice(0, 60), overview: true });
    t += outro;
    return { shots, total: t, intro, per, buildStart: intro };
  }

  applyTime(tl, t) {
    // 벽 올라오기
    const wk = ease(t / (tl.intro * 0.8));
    for (const w of this.walls) w.scale.y = Math.max(0.001, wk), w.position.y = w.userData.y0 * wk;
    // 가구 떨어지기
    this.furniture.forEach((f, i) => {
      const k = (t - tl.buildStart - i * tl.per) / 0.6;
      f.visible = k > 0;
      const e = easeOutBack(k);
      f.position.y = f.userData.elev + (1 - Math.min(1, ease(k))) * 1.6;
      f.scale.setScalar(Math.max(0.001, Math.min(1.05, e)));
    });
    // 카메라
    const shot = tl.shots.find((s) => t >= s.t0 && t < s.t1) || tl.shots[tl.shots.length - 1];
    for (const s of this.roomLabels) s.visible = t > tl.intro && !!shot.overview;
    const k = ease((t - shot.t0) / (shot.t1 - shot.t0));
    this.camera.position.lerpVectors(shot.from.pos, shot.to.pos, k);
    const tgt = new THREE.Vector3().lerpVectors(shot.from.target, shot.to.target, k);
    this.camera.lookAt(tgt); this.controls.target.copy(tgt);
    this.overlay = { shot, t, total: tl.total, fade: Math.min(1, (t - shot.t0) / 0.5) };
  }

  resetAnim() {
    for (const w of this.walls) { w.scale.y = 1; w.position.y = w.userData.y0; }
    for (const f of this.furniture) { f.visible = true; f.position.y = f.userData.elev; f.scale.setScalar(1); }
    for (const s of this.roomLabels) s.visible = true;
    this.overlay = null; this.anim = null; this.controls.enabled = true;
  }

  prepare(meta) {
    for (const w of this.walls) if (w.userData.y0 === undefined) w.userData.y0 = w.position.y;
    this.controls.enabled = false;
    return this.timeline(meta);
  }

  play(meta) {
    if (!this.fp) return;
    const tl = this.prepare(meta);
    this.anim = { tl, start: performance.now() };
  }

  frame() {
    if (this.anim) {
      const t = (performance.now() - this.anim.start) / 1000;
      if (t > this.anim.tl.total) { this.resetAnim(); this.homeView(); }
      else this.applyTime(this.anim.tl, t);
    } else this.controls.update();
    this.renderer.render(this.scene, this.camera);
    if (this.compositeCtx) this.drawComposite();
  }

  /** 오버레이 자막을 그린 합성 캔버스 (녹화용) */
  drawComposite() {
    const g = this.compositeCtx, cw = g.canvas.width, ch = g.canvas.height;
    g.drawImage(this.renderer.domElement, 0, 0, cw, ch);
    const o = this.overlay; if (!o) return;
    const s = ch / 720;
    g.save(); g.globalAlpha = o.fade;
    g.fillStyle = "rgba(20,16,12,.55)"; g.fillRect(0, ch - 130 * s, cw, 130 * s);
    g.fillStyle = "#fff"; g.font = `700 ${40 * s}px sans-serif`; g.textBaseline = "alphabetic";
    g.fillText(o.shot.caption || "", 48 * s, ch - 72 * s);
    if (o.shot.dims) { g.font = `500 ${22 * s}px sans-serif`; g.fillStyle = "#f1c9a8"; g.fillText(o.shot.dims, 48 * s, ch - 112 * s); }
    g.font = `400 ${22 * s}px sans-serif`; g.fillStyle = "#eee"; g.fillText(o.shot.sub || "", 48 * s, ch - 34 * s);
    g.restore();
    g.fillStyle = "rgba(255,255,255,.75)"; g.font = `600 ${18 * s}px sans-serif`;
    g.fillText("AI 인테리어 플래너", cw - 200 * s, 40 * s);
    g.fillStyle = "#b5663d"; g.fillRect(0, ch - 4 * s, (cw * o.t) / o.total, 4 * s);
  }

  /** 타임라인을 실시간으로 재생하며 1280×720 WebM으로 녹화한다. */
  async record(meta, onProgress = () => {}) {
    if (!window.MediaRecorder) throw new Error("이 브라우저는 영상 녹화를 지원하지 않습니다 (Chrome/Edge 권장).");
    const W = 1280, H = 720;
    this.fixedSize = true;
    this.renderer.setPixelRatio(1);
    this.renderer.setSize(W, H, false);
    this.camera.aspect = W / H; this.camera.updateProjectionMatrix();
    const comp = document.createElement("canvas"); comp.width = W; comp.height = H;
    this.compositeCtx = comp.getContext("2d");
    const stream = comp.captureStream(30);
    const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find((m) => MediaRecorder.isTypeSupported(m));
    const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 8_000_000 });
    const chunks = []; rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const done = new Promise((ok) => (rec.onstop = ok));
    const tl = this.prepare(meta);
    this.applyTime(tl, 0); this.renderer.render(this.scene, this.camera); this.drawComposite();
    rec.start(500);
    const start = performance.now();
    this.anim = { tl, start };
    await new Promise((ok) => {
      const tick = () => {
        const t = (performance.now() - start) / 1000;
        onProgress(Math.min(1, t / tl.total));
        if (t >= tl.total + 0.3) return ok();
        setTimeout(tick, 200);
      };
      tick();
    });
    rec.stop(); await done;
    this.compositeCtx = null; this.fixedSize = false;
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.resetAnim(); this.resize(); this.homeView();
    return new Blob(chunks, { type: "video/webm" });
  }
}
