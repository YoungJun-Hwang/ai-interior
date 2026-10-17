"""API 키 없이 체험할 수 있는 샘플 평면도 (전용 약 84㎡, 4bay 판상형을 단순화)."""

from .models import FloorPlan, Opening, Room


def sample_floorplan() -> FloorPlan:
    R = Room
    rooms = [
        R(id="r1", name="침실3", type="bedroom", x=0, y=0, width=3000, depth=3600),
        R(id="r2", name="현관", type="entrance", x=3000, y=0, width=1800, depth=2000),
        R(id="r3", name="복도", type="hallway", x=3000, y=2000, width=1800, depth=1600),
        R(id="r4", name="주방/식당", type="kitchen", x=4800, y=0, width=3600, depth=3600),
        R(id="r5", name="다용도실", type="utility", x=8400, y=0, width=1800, depth=1600),
        R(id="r6", name="공용욕실", type="bathroom", x=8400, y=1600, width=1800, depth=2000),
        R(id="r11", name="안방욕실", type="bathroom", x=10200, y=0, width=1800, depth=1600),
        R(id="r10", name="드레스룸", type="dressroom", x=10200, y=1600, width=1800, depth=2000),
        R(id="r7", name="침실2", type="bedroom", x=0, y=3600, width=3000, depth=4200),
        R(id="r8", name="거실", type="living", x=3000, y=3600, width=5400, depth=4200),
        R(id="r9", name="안방", type="master_bedroom", x=8400, y=3600, width=3600, depth=4200),
        R(id="r12", name="발코니", type="balcony", x=0, y=7800, width=12000, depth=1200),
    ]
    O = Opening
    openings = [
        O(id="d1", kind="door", x1=3400, y1=0, x2=4400, y2=0),            # 현관문
        O(id="d2", kind="door", x1=3000, y1=2500, x2=3000, y2=3400),      # 침실3
        O(id="d3", kind="door", x1=3000, y1=3800, x2=3000, y2=4700),      # 침실2
        O(id="o1", kind="opening", x1=3200, y1=3600, x2=4600, y2=3600),   # 복도→거실
        O(id="o2", kind="opening", x1=4800, y1=2100, x2=4800, y2=3500),   # 복도→주방
        O(id="o3", kind="opening", x1=5000, y1=3600, x2=8200, y2=3600),   # 주방↔거실
        O(id="d4", kind="door", x1=8400, y1=400, x2=8400, y2=1200),       # 다용도실
        O(id="d5", kind="door", x1=8400, y1=2500, x2=8400, y2=3300),      # 공용욕실
        O(id="d6", kind="door", x1=8400, y1=3800, x2=8400, y2=4700),      # 안방
        O(id="d7", kind="sliding_door", x1=10400, y1=3600, x2=11200, y2=3600),  # 드레스룸
        O(id="d8", kind="door", x1=10600, y1=1600, x2=11400, y2=1600),    # 안방욕실
        O(id="s1", kind="sliding_door", x1=400, y1=7800, x2=2600, y2=7800),
        O(id="s2", kind="sliding_door", x1=3400, y1=7800, x2=8000, y2=7800),
        O(id="s3", kind="sliding_door", x1=8800, y1=7800, x2=11600, y2=7800),
        O(id="w1", kind="window", x1=300, y1=9000, x2=11700, y2=9000),
        O(id="w2", kind="window", x1=600, y1=0, x2=2400, y2=0),
        O(id="w3", kind="window", x1=5400, y1=0, x2=7800, y2=0),
        O(id="w4", kind="window", x1=8700, y1=0, x2=9900, y2=0),
    ]
    return FloorPlan(name="샘플 84㎡ (4bay 판상형)", total_width=12000, total_depth=9000, ceiling_height=2300,
                     rooms=rooms, openings=openings, scale_note="샘플 데이터", confidence="high")
