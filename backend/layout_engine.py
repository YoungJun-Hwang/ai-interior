"""규칙 기반 배치 엔진.

두 가지 용도로 쓰인다.
1. AI(Claude)가 제안한 배치를 검증하고, 벽 밖으로 나가거나 겹치거나 문을 막는 가구를 가장 가까운 유효 위치로 옮긴다.
2. API 키가 없을 때 가족 구성과 요청 목록만으로 직접 배치안을 만든다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from . import catalog
from .models import FloorPlan, FurnitureItem, HouseholdMember, Layout, Placement, Room

Rect = tuple[float, float, float, float]  # x1, y1, x2, y2

STEP = 100          # 후보 위치 탐색 간격 (mm)
WALL_GAP = 20       # 벽과 가구 사이 여유
TOL = 30            # 겹침 허용 오차

# 가구 정면의 사용 공간(문 열림, 서랍, 의자 빼는 공간 등)
FRONT_CLEARANCE = {
    "wardrobe": 600, "dresser": 500, "refrigerator": 800, "kimchi_fridge": 700,
    "washing_machine": 600, "dryer": 600, "styler": 600, "shoe_cabinet": 500,
    "storage_cabinet": 500, "bookshelf": 400, "bed": 500, "desk": 700, "piano": 600,
    "sofa": 300, "tv_stand": 0,
}
# 사방 여유가 필요한 가구
AROUND_CLEARANCE = {"dining_table": 600, "kitchen_island": 800}

# 바닥에 깔리거나 다른 가구 위에 올라가 충돌 검사에서 제외되는 조합
STACKABLE = {("tv", "tv_stand"), ("dryer", "washing_machine"), ("rug", "*")}
# 앵커 가구의 사용 공간 안에 들어가도 되는 조합 (들어가는 가구, 앵커)
ZONE_OK = {
    ("office_chair", "desk"), ("chair", "desk"), ("chair", "dining_table"), ("chair", "kitchen_island"),
    ("coffee_table", "sofa"), ("rug", "*"), ("armchair", "sofa"), ("side_table", "bed"),
    ("pet_house", "sofa"), ("air_purifier", "sofa"),
}
FREE_STANDING = {"dining_table", "kitchen_island", "coffee_table", "rug", "armchair", "chair", "office_chair"}
# 지정된 방 타입 밖으로는 옮기지 않는 가구 (세탁기가 거실에 가는 일을 막음)
FIXED_ROOM = {"washing_machine", "dryer", "refrigerator", "kimchi_fridge", "shoe_cabinet", "styler",
              "coffee_table", "rug", "tv_stand", "tv"}
CENTERED = {"bed", "sofa", "tv_stand", "tv", "desk", "piano", "crib", "dresser"}

FRONT = {0: (0, 1), 90: (1, 0), 180: (0, -1), 270: (-1, 0)}


def footprint(item: FurnitureItem, rot: int) -> tuple[float, float]:
    return (item.depth, item.width) if rot in (90, 270) else (item.width, item.depth)


def item_rect(item: FurnitureItem, x: float, y: float, rot: int) -> Rect:
    w, d = footprint(item, rot)
    return (x - w / 2, y - d / 2, x + w / 2, y + d / 2)


def room_rect(room: Room) -> Rect:
    return (room.x, room.y, room.x + room.width, room.y + room.depth)


def overlaps(a: Rect, b: Rect, tol: float = TOL) -> bool:
    return a[0] < b[2] - tol and b[0] < a[2] - tol and a[1] < b[3] - tol and b[1] < a[3] - tol


def inside(a: Rect, b: Rect, tol: float = TOL) -> bool:
    return a[0] >= b[0] - tol and a[1] >= b[1] - tol and a[2] <= b[2] + tol and a[3] <= b[3] + tol


def front_zone(item: FurnitureItem, x: float, y: float, rot: int, depth: float) -> Optional[Rect]:
    if depth <= 0:
        return None
    r = item_rect(item, x, y, rot)
    fx, fy = FRONT[rot]
    if fx == 1:
        return (r[2], r[1], r[2] + depth, r[3])
    if fx == -1:
        return (r[0] - depth, r[1], r[0], r[3])
    if fy == 1:
        return (r[0], r[3], r[2], r[3] + depth)
    return (r[0], r[1] - depth, r[2], r[1])


def _pair(table: set, a: str, b: str) -> bool:
    return (a, b) in table or (b, a) in table or (a, "*") in table or (b, "*") in table


@dataclass
class Placed:
    item: FurnitureItem
    p: Placement
    rect: Rect
    zones: list[Rect] = field(default_factory=list)


@dataclass
class Ctx:
    fp: FloorPlan
    clearance_scale: float = 1.0
    placed: list[Placed] = field(default_factory=list)
    door_zones: list[Rect] = field(default_factory=list)
    window_zones: list[Rect] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for o in self.fp.openings:
            length = math.hypot(o.x2 - o.x1, o.y2 - o.y1)
            horizontal = abs(o.y2 - o.y1) < abs(o.x2 - o.x1)
            if o.kind == "window":
                reach = 300
            elif o.kind == "door":
                reach = max(800, min(length, 1000))
            else:
                reach = 450
            x1, x2 = sorted((o.x1, o.x2))
            y1, y2 = sorted((o.y1, o.y2))
            zone = (x1, y1 - reach, x2, y2 + reach) if horizontal else (x1 - reach, y1, x2 + reach, y2)
            (self.window_zones if o.kind == "window" else self.door_zones).append(zone)

    def room(self, room_id: str) -> Optional[Room]:
        return next((r for r in self.fp.rooms if r.id == room_id), None)

    def zones_for(self, item: FurnitureItem, x: float, y: float, rot: int) -> list[Rect]:
        zones = []
        front = FRONT_CLEARANCE.get(item.category, 0) * self.clearance_scale
        z = front_zone(item, x, y, rot, front)
        if z:
            zones.append(z)
        around = AROUND_CLEARANCE.get(item.category)
        if around:
            r = item_rect(item, x, y, rot)
            a = around * self.clearance_scale
            zones.append((r[0] - a, r[1] - a, r[2] + a, r[3] + a))
        return zones

    def check(self, item: FurnitureItem, room: Room, x: float, y: float, rot: int,
              ignore: Optional[str] = None) -> Optional[str]:
        """배치 가능하면 None, 아니면 이유 문자열."""
        rect = item_rect(item, x, y, rot)
        rr = room_rect(room)
        if not inside(rect, rr):
            return "방 밖으로 벗어남"
        cat = item.category
        if cat != "rug":
            for dz in self.door_zones:
                if overlaps(rect, dz):
                    return "문 앞 동선을 막음"
            if item.height >= 1200 and any(overlaps(rect, wz, 0) for wz in self.window_zones):
                return "키 큰 가구가 창을 가림"
        my_zones = self.zones_for(item, x, y, rot)
        for z in my_zones:
            if cat not in ("dining_table", "kitchen_island") and not inside(z, rr, 50):
                return "정면 사용 공간이 부족함"
        for other in self.placed:
            if other.item.id == ignore:
                continue
            oc = other.item.category
            if not _pair(STACKABLE, cat, oc) and overlaps(rect, other.rect):
                return f"'{other.item.name}'과(와) 겹침"
            if not _pair(ZONE_OK, cat, oc):
                if any(overlaps(rect, z) for z in other.zones):
                    return f"'{other.item.name}' 사용 공간을 침범"
                if oc != "rug" and any(overlaps(other.rect, z) for z in my_zones):
                    return f"정면 공간에 '{other.item.name}'이(가) 있음"
        return None

    def place(self, item: FurnitureItem, room: Room, x: float, y: float, rot: int, reason: str) -> Placement:
        p = Placement(item_id=item.id, room_id=room.id, x=round(x), y=round(y), rotation=rot, reason=reason)
        self.placed.append(Placed(item, p, item_rect(item, x, y, rot), self.zones_for(item, x, y, rot)))
        return p

    # ---------- 후보 위치 생성 ----------

    def wall_candidates(self, item: FurnitureItem, room: Room) -> list[tuple[float, float, int, dict]]:
        out = []
        rx1, ry1, rx2, ry2 = room_rect(room)
        for side, rot in (("top", 0), ("bottom", 180), ("left", 90), ("right", 270)):
            w, d = footprint(item, rot)
            if side in ("top", "bottom"):
                y = ry1 + d / 2 + WALL_GAP if side == "top" else ry2 - d / 2 - WALL_GAP
                lo, hi = rx1 + w / 2 + WALL_GAP, rx2 - w / 2 - WALL_GAP
                wall_len = room.width
            else:
                x = rx1 + w / 2 + WALL_GAP if side == "left" else rx2 - w / 2 - WALL_GAP
                lo, hi = ry1 + d / 2 + WALL_GAP, ry2 - d / 2 - WALL_GAP
                wall_len = room.depth
            if hi < lo:
                continue
            n = max(1, int((hi - lo) // STEP))
            for i in range(n + 1):
                s = lo + (hi - lo) * i / n
                t = 0.5 if hi == lo else (s - lo) / (hi - lo)
                cx, cy = (s, y) if side in ("top", "bottom") else (x, s)
                out.append((cx, cy, rot, {"side": side, "t": t, "wall_len": wall_len}))
        return out

    def free_candidates(self, item: FurnitureItem, room: Room) -> list[tuple[float, float, int, dict]]:
        out = []
        rx1, ry1, rx2, ry2 = room_rect(room)
        for rot in (0, 90, 180, 270):
            w, d = footprint(item, rot)
            x = rx1 + w / 2 + WALL_GAP
            while x <= rx2 - w / 2 - WALL_GAP:
                y = ry1 + d / 2 + WALL_GAP
                while y <= ry2 - d / 2 - WALL_GAP:
                    out.append((x, y, rot, {}))
                    y += STEP
                x += STEP
        return out

    def candidates(self, item: FurnitureItem, room: Room):
        if item.category in FREE_STANDING:
            return self.free_candidates(item, room)
        return self.wall_candidates(item, room)

    def wall_has(self, room: Room, side: str, kinds: tuple[str, ...]) -> bool:
        rx1, ry1, rx2, ry2 = room_rect(room)
        for o in self.fp.openings:
            if o.kind not in kinds:
                continue
            ox1, ox2 = sorted((o.x1, o.x2))
            oy1, oy2 = sorted((o.y1, o.y2))
            near = 200
            if side == "top" and abs(oy1 - ry1) < near and ox2 > rx1 and ox1 < rx2:
                return True
            if side == "bottom" and abs(oy1 - ry2) < near and ox2 > rx1 and ox1 < rx2:
                return True
            if side == "left" and abs(ox1 - rx1) < near and oy2 > ry1 and oy1 < ry2:
                return True
            if side == "right" and abs(ox1 - rx2) < near and oy2 > ry1 and oy1 < ry2:
                return True
        return False

    def nearest_door_dist(self, x: float, y: float) -> float:
        ds = [math.hypot(x - (z[0] + z[2]) / 2, y - (z[1] + z[3]) / 2) for z in self.door_zones]
        return min(ds) if ds else 5000

    def score(self, item: FurnitureItem, room: Room, x: float, y: float, rot: int, meta: dict) -> float:
        cat = item.category
        s = 0.0
        if "t" in meta:
            t, side = meta["t"], meta["side"]
            if cat in CENTERED:
                s += abs(t - 0.5) * meta["wall_len"]
            else:
                s += min(t, 1 - t) * meta["wall_len"] * 0.6
            if self.wall_has(room, side, ("window",)) and cat in ("bed", "sofa", "wardrobe", "bookshelf", "tv_stand", "tv"):
                s += 1500
            if self.wall_has(room, side, ("door", "sliding_door", "opening")):
                s += 1200 if cat in ("bed", "sofa") else 300
            if cat == "bed":
                s -= self.nearest_door_dist(x, y) * 0.5
                if meta["wall_len"] < item.width + 900:
                    s += 800
            if cat == "sofa":
                s -= meta["wall_len"] * 0.3
        else:
            cx, cy = room.x + room.width / 2, room.y + room.depth / 2
            s += math.hypot(x - cx, y - cy)
            if cat in ("dining_table", "kitchen_island"):
                long_x = room.width >= room.depth
                if (rot in (0, 180)) != long_x:
                    s += 300
            if rot in (180, 270):
                s += 1  # 같은 점수면 0/90 선호
        return s

    def best(self, item: FurnitureItem, room: Room, target: Optional[tuple[float, float]] = None):
        best, best_s = None, float("inf")
        for x, y, rot, meta in self.candidates(item, room):
            if target is not None:
                s = math.hypot(x - target[0], y - target[1])
            else:
                s = self.score(item, room, x, y, rot, meta)
            if s >= best_s:
                continue
            if self.check(item, room, x, y, rot) is None:
                best, best_s = (x, y, rot), s
        return best


# ---------------- 방 선택 ----------------

def rooms_by_pref(fp: FloorPlan, item: FurnitureItem) -> list[Room]:
    rooms: list[Room] = []
    if item.preferred_room:
        pr = item.preferred_room.strip()
        rooms += [r for r in fp.rooms if r.id == pr or r.name == pr]
    for t in catalog.spec(item.category)[5]:
        rooms += sorted([r for r in fp.rooms if r.type == t and r not in rooms],
                        key=lambda r: -r.width * r.depth)
    if item.category in FIXED_ROOM:
        return rooms
    big = sorted([r for r in fp.rooms if r not in rooms and r.type not in ("bathroom", "entrance", "balcony", "hallway")],
                 key=lambda r: -r.width * r.depth)
    return rooms + big


# ---------------- 가구 간 관계 배치 ----------------

def _rotate(rot: int, by: int) -> int:
    return (rot + by) % 360


def place_companion(ctx: Ctx, item: FurnitureItem, anchors: dict[str, list[Placed]]) -> Optional[Placement]:
    cat = item.category

    def first(c: str) -> Optional[Placed]:
        return anchors.get(c, [None])[0] if anchors.get(c) else None

    def try_at(room_id: str, x: float, y: float, rot: int, reason: str, ignore=None):
        room = ctx.room(room_id)
        if room and ctx.check(item, room, x, y, rot, ignore=ignore) is None:
            return ctx.place(item, room, x, y, rot, reason)
        return None

    if cat == "tv" and first("tv_stand"):
        st = first("tv_stand")
        fx, fy = FRONT[st.p.rotation]
        off = st.item.depth / 2 - item.depth / 2 - 30
        return try_at(st.p.room_id, st.p.x - fx * off, st.p.y - fy * off, st.p.rotation, "TV 거실장 위에 배치")

    if cat == "dryer" and first("washing_machine"):
        wm = first("washing_machine")
        return try_at(wm.p.room_id, wm.p.x, wm.p.y, wm.p.rotation, "세탁기 위 직렬 설치")

    if cat == "tv_stand" and first("sofa"):
        sofa = first("sofa")
        room = ctx.room(sofa.p.room_id)
        want = _rotate(sofa.p.rotation, 180)
        best, best_s = None, float("inf")
        for x, y, rot, meta in ctx.wall_candidates(item, room):
            if rot != want:
                continue
            s = abs(x - sofa.p.x) if rot in (0, 180) else abs(y - sofa.p.y)
            if s < best_s and ctx.check(item, room, x, y, rot) is None:
                best, best_s = (x, y, rot), s
        if best:
            return ctx.place(item, room, *best, "소파 맞은편 벽에 TV 시청 축을 맞춤")

    if cat == "coffee_table" and first("sofa"):
        sofa = first("sofa")
        fx, fy = FRONT[sofa.p.rotation]
        for gap in (400, 350, 450, 300, 500):
            off = sofa.item.depth / 2 + gap + item.depth / 2
            p = try_at(sofa.p.room_id, sofa.p.x + fx * off, sofa.p.y + fy * off, sofa.p.rotation,
                       f"소파 앞 {gap}mm 간격으로 배치")
            if p:
                return p

    if cat == "rug" and first("sofa"):
        sofa = first("sofa")
        fx, fy = FRONT[sofa.p.rotation]
        off = sofa.item.depth / 2 + item.depth / 2 - 200
        return try_at(sofa.p.room_id, sofa.p.x + fx * off, sofa.p.y + fy * off, sofa.p.rotation, "소파 앞 공간을 러그로 묶음")

    if cat == "armchair" and first("sofa"):
        sofa = first("sofa")
        fx, fy = FRONT[sofa.p.rotation]
        lx, ly = -fy, fx
        for side in (1, -1):
            off_f = sofa.item.depth / 2 + 700
            off_l = sofa.item.width / 2 + item.depth / 2 + 150
            x = sofa.p.x + fx * off_f + lx * off_l * side
            y = sofa.p.y + fy * off_f + ly * off_l * side
            rot = {(1, 0): 90, (-1, 0): 270, (0, 1): 0, (0, -1): 180}[(-int(lx * side), -int(ly * side))]
            p = try_at(sofa.p.room_id, x, y, rot, "소파와 ㄱ자 대화 공간 구성")
            if p:
                return p

    if cat == "side_table" and first("bed"):
        for bed in anchors.get("bed", []):
            fx, fy = FRONT[bed.p.rotation]
            lx, ly = -fy, fx
            for side in (1, -1):
                off_b = bed.item.depth / 2 - item.depth / 2 - WALL_GAP
                off_l = bed.item.width / 2 + item.width / 2 + 30
                x = bed.p.x - fx * off_b + lx * off_l * side
                y = bed.p.y - fy * off_b + ly * off_l * side
                p = try_at(bed.p.room_id, x, y, bed.p.rotation, "침대 머리맡 협탁")
                if p:
                    return p

    if cat in ("office_chair", "chair") and (first("desk") and (cat == "office_chair" or not first("dining_table"))):
        desks = sorted(anchors.get("desk", []), key=lambda d: d.p.room_id != item.preferred_room)
        for desk in desks:
            if any(pl.item.category in ("office_chair", "chair") and pl.p.room_id == desk.p.room_id
                   and math.hypot(pl.p.x - desk.p.x, pl.p.y - desk.p.y) < 900 for pl in ctx.placed):
                continue
            fx, fy = FRONT[desk.p.rotation]
            off = desk.item.depth / 2 + item.depth / 2 - 150
            p = try_at(desk.p.room_id, desk.p.x + fx * off, desk.p.y + fy * off, _rotate(desk.p.rotation, 180),
                       "책상 앞 의자", ignore=desk.item.id)
            if p:
                return p

    if cat == "chair" and (first("dining_table") or first("kitchen_island")):
        table = first("dining_table") or first("kitchen_island")
        tw, td = footprint(table.item, table.p.rotation)
        seats = []
        long_x = tw >= td
        n_side = max(1, int((tw if long_x else td) // 650))
        span = tw if long_x else td
        for side in (-1, 1):
            for i in range(n_side):
                along = -span / 2 + span * (i + 0.5) / n_side
                if long_x:
                    seats.append((table.p.x + along, table.p.y + side * (td / 2 + item.depth / 2 - 50), 0 if side < 0 else 180))
                else:
                    seats.append((table.p.x + side * (tw / 2 + item.depth / 2 - 50), table.p.y + along, 90 if side < 0 else 270))
        for side in (-1, 1):  # 끝자리
            if long_x:
                seats.append((table.p.x + side * (tw / 2 + item.depth / 2 - 50), table.p.y, 90 if side < 0 else 270))
            else:
                seats.append((table.p.x, table.p.y + side * (td / 2 + item.depth / 2 - 50), 0 if side < 0 else 180))
        for x, y, rot in seats:
            p = try_at(table.p.room_id, x, y, rot, "식탁 의자", ignore=table.item.id)
            if p:
                return p
    return None


# ---------------- 공개 API ----------------

PRIORITY = [
    "bed", "crib", "wardrobe", "refrigerator", "kimchi_fridge", "washing_machine", "dryer", "sofa", "tv_stand",
    "piano", "dining_table", "kitchen_island", "desk", "shoe_cabinet", "styler", "dresser", "bookshelf",
    "storage_cabinet", "air_conditioner", "tv", "coffee_table", "armchair", "side_table", "office_chair",
    "chair", "air_purifier", "pet_house", "plant", "lamp", "other", "rug",
]


def _prio(item: FurnitureItem) -> tuple[int, int, float]:
    cat = item.category
    idx = PRIORITY.index(cat) if cat in PRIORITY else len(PRIORITY)
    return (0 if item.source == "user" and cat not in ("chair", "office_chair", "rug", "tv", "side_table", "coffee_table") else 1,
            idx, -item.width * item.depth)


def clearance_scale(household: list[HouseholdMember], requirements: str) -> float:
    scale = 1.0
    if any((m.age or 0) >= 65 for m in household) or any(k in requirements for k in ("어르신", "노인", "부모님")):
        scale = 1.3
    if any(k in requirements for k in ("휠체어", "보행기")):
        scale = 1.6
    return scale


def _place_generic(ctx: Ctx, item: FurnitureItem, target=None, room_order: Optional[list[Room]] = None) -> Optional[Placement]:
    for room in room_order or rooms_by_pref(ctx.fp, item):
        spot = ctx.best(item, room, target if (target and room_order and room == room_order[0]) else None)
        if spot:
            return ctx.place(item, room, *spot, f"{room.name}에 배치")
    return None


def _anchors(ctx: Ctx) -> dict[str, list[Placed]]:
    out: dict[str, list[Placed]] = {}
    for pl in ctx.placed:
        out.setdefault(pl.item.category, []).append(pl)
    return out


def rule_layout(fp: FloorPlan, items: list[FurnitureItem], household: list[HouseholdMember],
                requirements: str = "") -> Layout:
    ctx = Ctx(fp, clearance_scale(household, requirements))
    placements: list[Placement] = []
    for item in sorted(items, key=_prio):
        p = place_companion(ctx, item, _anchors(ctx)) or _place_generic(ctx, item)
        if p:
            placements.append(p)
        else:
            ctx.warnings.append(f"'{item.name}'({int(item.width)}×{int(item.depth)}mm)을(를) 놓을 공간을 찾지 못했습니다.")
    return Layout(items=items, placements=placements, warnings=ctx.warnings + density_warnings(ctx), engine="rule")


def repair_layout(fp: FloorPlan, items: list[FurnitureItem], placements: list[Placement],
                  household: list[HouseholdMember], requirements: str = "") -> tuple[list[Placement], list[str]]:
    """AI 배치를 검증하고, 문제가 있는 가구만 가장 가까운 유효 위치로 옮긴다."""
    ctx = Ctx(fp, clearance_scale(household, requirements))
    by_id = {i.id: i for i in items}
    proposed = {p.item_id: p for p in placements if p.item_id in by_id}
    result: list[Placement] = []
    for item in sorted(items, key=_prio):
        p = proposed.get(item.id)
        if p is None:
            np_ = place_companion(ctx, item, _anchors(ctx)) or _place_generic(ctx, item)
            if np_:
                result.append(np_)
                ctx.warnings.append(f"'{item.name}': AI가 배치하지 않아 자동 배치했습니다.")
            else:
                ctx.warnings.append(f"'{item.name}': 놓을 공간이 없습니다.")
            continue
        room = ctx.room(p.room_id) or next(
            (r for r in fp.rooms if inside(item_rect(item, p.x, p.y, p.rotation), room_rect(r), 200)), None)
        if room and ctx.check(item, room, p.x, p.y, p.rotation) is None:
            result.append(ctx.place(item, room, p.x, p.y, p.rotation, p.reason))
            continue
        reason = ctx.check(item, room, p.x, p.y, p.rotation) if room else "방을 찾을 수 없음"
        order = ([room] if room else []) + [r for r in rooms_by_pref(fp, item) if r != room]
        np_ = place_companion(ctx, item, _anchors(ctx)) if item.category in ("tv", "chair", "office_chair", "side_table") else None
        np_ = np_ or _place_generic(ctx, item, target=(p.x, p.y), room_order=order)
        if np_:
            np_.reason = (p.reason + " " if p.reason else "") + f"(보정: {reason} → 위치 조정)"
            result.append(np_)
        else:
            ctx.warnings.append(f"'{item.name}': {reason}, 대체 위치를 찾지 못해 제외했습니다.")
    return result, ctx.warnings + density_warnings(ctx)


def density_warnings(ctx: Ctx) -> list[str]:
    out = []
    for room in ctx.fp.rooms:
        area = room.width * room.depth
        used = sum((pl.rect[2] - pl.rect[0]) * (pl.rect[3] - pl.rect[1])
                   for pl in ctx.placed if pl.p.room_id == room.id and pl.item.category != "rug")
        if area > 0 and used / area > 0.55:
            out.append(f"{room.name}: 가구가 바닥 면적의 {used / area:.0%}를 차지해 다소 답답할 수 있습니다.")
    return out


# ---------------- AI 없이 필요한 가구 목록 만들기 ----------------

def _new_item(idx: int, category: str, room: Optional[Room], name: Optional[str] = None,
              size: Optional[tuple[int, int, int]] = None) -> FurnitureItem:
    dname, w, d, h, color, _, _ = catalog.spec(category)
    if size:
        w, d, h = size
    return FurnitureItem(id=f"a{idx}", name=name or dname, category=category, width=w, depth=d, height=h,
                         color=color, source="ai", preferred_room=room.id if room else None)


def default_items(fp: FloorPlan, user_items: list[FurnitureItem], requested: list[str],
                  household: list[HouseholdMember], requirements: str) -> list[FurnitureItem]:
    """가족 구성/요청에 따라 필요한 가구 목록을 규칙으로 생성한다 (사용자 제품과 중복되는 카테고리는 생략)."""
    have = {i.category for i in user_items}
    out: list[FurnitureItem] = []
    n = [0]

    def add(cat: str, room: Optional[Room], name=None, size=None, force=False):
        if not force and cat in have:
            return
        n[0] += 1
        out.append(_new_item(n[0], cat, room, name, size))

    rooms = {t: sorted([r for r in fp.rooms if r.type == t], key=lambda r: -r.width * r.depth)
             for t in {r.type for r in fp.rooms}}
    living = (rooms.get("living") or [None])[0]
    kitchen = (rooms.get("kitchen") or [None])[0]
    dining = (rooms.get("dining") or [kitchen])[0]
    bedrooms = rooms.get("master_bedroom", []) + rooms.get("bedroom", []) + rooms.get("kids_room", []) + rooms.get("study", [])
    master = bedrooms[0] if bedrooms else None
    others = bedrooms[1:]

    adults = [m for m in household if (m.age is None or m.age >= 20) and not _is_pet(m)]
    kids = [m for m in household if m.age is not None and m.age < 20 and not _is_pet(m)]
    pets = [m for m in household if _is_pet(m)]
    seniors = [m for m in adults if (m.age or 0) >= 65]
    people = max(1, len(adults) + len(kids)) if household else 4

    if requested:
        for name in requested:
            cat = catalog.guess_category(name)
            n[0] += 1
            out.append(_new_item(n[0], cat, None, name=name))
    else:
        # 거실
        add("sofa", living, name="4인 소파" if people >= 4 else None, size=(2600, 1000, 850) if people >= 4 else None)
        add("tv_stand", living)
        add("tv", living)
        add("coffee_table", living)
        add("rug", living)
        add("air_conditioner", living)
        # 주방
        add("refrigerator", kitchen)
        add("kimchi_fridge", kitchen)
        seats = 6 if people > 4 else 4 if people > 2 else 2
        add("dining_table", dining, name=f"{seats}인 식탁", size=(1800 if seats == 6 else 1400 if seats == 4 else 900, 800 if seats > 2 else 750, 750))
        for _ in range(seats):
            add("chair", dining, force=True)
        # 다용도실
        laundry = (rooms.get("utility") or rooms.get("balcony") or [None])[0]
        add("washing_machine", laundry)
        add("dryer", laundry)
        add("shoe_cabinet", (rooms.get("entrance") or [None])[0])
        # 안방
        couple = [m for m in adults if m not in seniors] or adults
        if master:
            add("bed", master, name="킹 침대" if len(couple) >= 2 else "퀸 침대",
                size=(1800, 2100, 1000) if len(couple) >= 2 else None)
            add("side_table", master, force=True)
            if len(couple) >= 2:
                add("side_table", master, force=True)
            add("wardrobe", (rooms.get("dressroom") or [master])[0])
            add("dresser", (rooms.get("dressroom") or [master])[0])
        # 아이/어르신 방
        free_rooms = list(others)
        for kid in sorted(kids, key=lambda k: k.age or 0):
            if (kid.age or 0) < 3:
                add("crib", master, force=True)
                continue
            room = free_rooms.pop(0) if free_rooms else (others[-1] if others else master)
            add("bed", room, name=f"{kid.role} 싱글 침대", size=(1100, 2000, 900), force=True)
            if (kid.age or 0) >= 7:
                add("desk", room, name=f"{kid.role} 책상", force=True)
                add("office_chair", room, name=f"{kid.role} 의자", force=True)
                add("bookshelf", room, force=True)
            else:
                add("storage_cabinet", room, name="장난감 수납장", size=(1000, 400, 900), force=True)
        for s in seniors:
            room = free_rooms.pop(0) if free_rooms else None
            if room:
                add("bed", room, name=f"{s.role} 저상 침대", size=(1100, 2100, 450), force=True)
                add("wardrobe", room, name="옷장", size=(1200, 600, 2000), force=True)
                add("side_table", room, force=True)
        if any(k in requirements for k in ("재택", "홈오피스", "서재", "업무")) or (not household and free_rooms):
            room = free_rooms.pop(0) if free_rooms else (master or living)
            add("desk", room, name="업무용 책상", size=(1400, 700, 740), force=True)
            add("office_chair", room, force=True)
            add("bookshelf", room, force=True)
        for room in free_rooms:
            add("bed", room, name="게스트 침대", size=(1100, 2000, 900), force=True)
        for p in pets:
            add("pet_house", living, name=f"{p.role} 하우스", force=True)
        if any(k in requirements for k in ("피아노",)):
            add("piano", living)
    return out


def _is_pet(m: HouseholdMember) -> bool:
    return any(k in m.role for k in ("강아지", "고양이", "반려", "개", "펫", "cat", "dog"))
