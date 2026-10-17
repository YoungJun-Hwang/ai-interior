"""백엔드 테스트. 실행: python -m pytest -q"""

import json

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from backend import ai
from backend.demo import sample_floorplan
from backend.layout_engine import (
    Ctx, default_items, footprint, inside, item_rect, overlaps, repair_layout, room_rect, rule_layout,
)
from backend.main import app
from backend.models import FurnitureItem, HouseholdMember as H, LayoutRequest, Placement

FAMILY = [H(role="아빠", age=40), H(role="엄마", age=38), H(role="아들", age=10), H(role="딸", age=2), H(role="강아지")]


def assert_valid(fp, items, placements):
    """모든 가구가 방 안에 있고, 쌓을 수 있는 조합 외에는 겹치지 않는지 검사."""
    by_id = {i.id: i for i in items}
    rooms = {r.id: r for r in fp.rooms}
    rects = []
    for p in placements:
        it = by_id[p.item_id]
        r = item_rect(it, p.x, p.y, p.rotation)
        assert inside(r, room_rect(rooms[p.room_id])), f"{it.name} 방 밖"
        rects.append((it, r))
    # 의자는 식탁/책상 아래로 조금 밀어 넣는 것을 허용
    ok = {("tv", "tv_stand"), ("dryer", "washing_machine"), ("chair", "dining_table"), ("chair", "kitchen_island"),
          ("office_chair", "desk"), ("chair", "desk")}
    for i, (a, ra) in enumerate(rects):
        for b, rb in rects[i + 1:]:
            if "rug" in (a.category, b.category) or (a.category, b.category) in ok or (b.category, a.category) in ok:
                continue
            assert not overlaps(ra, rb), f"{a.name} / {b.name} 겹침"


@pytest.mark.parametrize("household,req", [
    (FAMILY, ""),
    ([H(role="할머니", age=78), H(role="아빠", age=50), H(role="엄마", age=48)], "휠체어 사용"),
    ([H(role="남편", age=32), H(role="아내", age=30)], "재택근무 공간 필요"),
    ([], ""),
])
def test_rule_layout_is_valid(household, req):
    fp = sample_floorplan()
    items = default_items(fp, [], [], household, req)
    lay = rule_layout(fp, items, household, req)
    assert len(lay.placements) >= len(items) - 1
    assert_valid(fp, lay.items, lay.placements)


def test_household_changes_layout():
    fp = sample_floorplan()
    kids = default_items(fp, [], [], FAMILY, "")
    cats = [i.category for i in kids]
    assert "crib" in cats and "desk" in cats and "pet_house" in cats
    couple = default_items(fp, [], [], [H(role="남편", age=32), H(role="아내", age=30)], "재택근무")
    assert "crib" not in [i.category for i in couple]
    assert any(i.category == "desk" for i in couple)


def test_user_item_dimensions_are_kept():
    fp = sample_floorplan()
    mine = FurnitureItem(id="u1", name="LG 냉장고", category="refrigerator", width=912, depth=930, height=1860, source="user")
    items = [mine] + default_items(fp, [mine], [], FAMILY, "")
    assert sum(i.category == "refrigerator" for i in items) == 1
    lay = rule_layout(fp, items, FAMILY)
    p = next(p for p in lay.placements if p.item_id == "u1")
    assert p.room_id == "r4"
    assert footprint(mine, p.rotation) in ((912, 930), (930, 912))


def test_requested_items_only():
    fp = sample_floorplan()
    items = default_items(fp, [], ["안마의자", "세탁기", "65인치 TV"], [], "")
    assert [i.category for i in items] == ["armchair", "washing_machine", "tv"]


def test_repair_moves_bad_placements():
    fp = sample_floorplan()
    sofa = FurnitureItem(id="a1", name="소파", category="sofa", width=2200, depth=950, height=850)
    bed = FurnitureItem(id="a2", name="침대", category="bed", width=1600, depth=2100, height=1000)
    bad = [
        Placement(item_id="a1", room_id="r8", x=2000, y=5000, rotation=90),     # 벽 밖
        Placement(item_id="a2", room_id="r9", x=8900, y=4200, rotation=0),      # 안방 문 막음
    ]
    fixed, _ = repair_layout(fp, [sofa, bed], bad, [])
    assert_valid(fp, [sofa, bed], fixed)
    ctx = Ctx(fp)
    for p in fixed:
        it = sofa if p.item_id == "a1" else bed
        assert not any(overlaps(item_rect(it, p.x, p.y, p.rotation), z) for z in ctx.door_zones)


# ---------- API ----------

client = TestClient(app)


def test_api_rule_layout():
    fp = client.get("/api/floorplan/sample").json()
    res = client.post("/api/layout?engine=rule", json={"floorplan": fp, "household": [h.model_dump() for h in FAMILY]})
    assert res.status_code == 200
    body = res.json()
    assert body["engine"] == "rule" and len(body["placements"]) > 15


def test_api_furniture_without_ai(monkeypatch):
    monkeypatch.setattr(ai, "enabled", lambda: False)
    res = client.post("/api/furniture/analyze", data={"name": "드럼 세탁기", "width": "700"})
    item = res.json()
    assert item["category"] == "washing_machine" and item["width"] == 700 and item["depth"] == 790


def test_api_analyze_requires_key(monkeypatch):
    monkeypatch.setattr(ai, "enabled", lambda: False)
    res = client.post("/api/floorplan/analyze", files={"image": ("a.png", _png(), "image/png")})
    assert res.status_code == 503


def _png() -> bytes:
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, "PNG")
    return buf.getvalue()


# ---------- Claude 호출 (HTTP 모킹) ----------

def _mock_client(payload: dict, captured: dict):
    def handler(req):
        captured["body"] = json.loads(req.content)
        captured["beta"] = req.headers.get("anthropic-beta")
        return httpx2.Response(200, json={
            "id": "m", "type": "message", "role": "assistant", "model": ai.MODEL,
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})
    return anthropic.Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_ai_floorplan_request(monkeypatch):
    fp = sample_floorplan().model_dump()
    cap = {}
    monkeypatch.setattr(ai, "_client", _mock_client(fp, cap))
    out = ai.analyze_floorplan(_png(), "84㎡")
    assert len(out.rooms) == len(fp["rooms"])
    body = cap["body"]
    assert body["model"] == ai.MODEL and body["thinking"] == {"type": "adaptive"}
    assert body["fallbacks"] == "default" and ai.FALLBACK_BETA in cap["beta"]
    assert body["messages"][0]["content"][0]["type"] == "image"
    assert "format" in body["output_config"]


def test_ai_layout_is_repaired(monkeypatch):
    payload = {
        "added_items": [{"id": "a1", "name": "소파", "category": "sofa", "width": 2200, "depth": 950, "height": 850, "color": "#888"}],
        "placements": [{"item_id": "a1", "room_id": "r8", "x": 1000, "y": 5000, "rotation": 90, "reason": "벽"},
                       {"item_id": "ghost", "room_id": "r8", "x": 1, "y": 1, "rotation": 0, "reason": ""}],
        "summary": "요약", "warnings": []}
    monkeypatch.setattr(ai, "_client", _mock_client(payload, {}))
    lay = ai.plan_layout(LayoutRequest(floorplan=sample_floorplan()))
    assert lay.engine == "ai" and [p.item_id for p in lay.placements] == ["a1"]
    assert_valid(sample_floorplan(), lay.items, lay.placements)
    assert "보정" in lay.placements[0].reason


def test_ai_furniture_user_dims_win(monkeypatch):
    payload = {"name": "냉장고", "category": "refrigerator", "width": 900, "depth": 900, "height": 1800, "color": "#ccc", "note": "메탈"}
    monkeypatch.setattr(ai, "_client", _mock_client(payload, {}))
    r = ai.analyze_furniture(_png(), "", 912, None, None)
    assert r.width == 912 and r.depth == 900
