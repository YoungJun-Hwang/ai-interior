"""데이터 스키마. 모든 길이 단위는 mm, 좌표계는 도면 좌상단이 (0, 0)이고 x는 오른쪽, y는 아래쪽으로 증가한다."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

RoomType = Literal[
    "living", "kitchen", "dining", "master_bedroom", "bedroom", "kids_room",
    "study", "dressroom", "bathroom", "entrance", "balcony", "utility", "storage", "hallway",
]

FurnitureCategory = Literal[
    "bed", "sofa", "armchair", "dining_table", "chair", "desk", "office_chair", "wardrobe",
    "dresser", "bookshelf", "tv_stand", "tv", "coffee_table", "side_table", "refrigerator",
    "washing_machine", "dryer", "kimchi_fridge", "air_conditioner", "air_purifier",
    "styler", "kitchen_island", "shoe_cabinet", "plant", "rug", "lamp", "crib",
    "piano", "storage_cabinet", "pet_house", "other",
]


class Room(BaseModel):
    id: str = Field(description="짧은 고유 id, 예: r1")
    name: str = Field(description="도면에 적힌 실 이름, 예: 거실, 침실1")
    type: RoomType
    x: float = Field(description="방 좌상단 x (mm)")
    y: float = Field(description="방 좌상단 y (mm)")
    width: float = Field(description="x 방향 길이 (mm)")
    depth: float = Field(description="y 방향 길이 (mm)")


class Opening(BaseModel):
    """문 또는 창. 벽 위의 선분 (x1,y1)-(x2,y2) 로 표현한다 (수평 또는 수직)."""

    id: str
    kind: Literal["door", "window", "sliding_door", "opening"]
    x1: float
    y1: float
    x2: float
    y2: float


class FloorPlan(BaseModel):
    name: str = Field(default="우리 집", description="평면도 이름 또는 평형, 예: 84㎡ 판상형")
    total_width: float = Field(description="전체 외곽 가로 (mm)")
    total_depth: float = Field(description="전체 외곽 세로 (mm)")
    ceiling_height: float = Field(default=2300, description="천장고 (mm), 모르면 2300")
    rooms: list[Room]
    openings: list[Opening] = Field(default_factory=list)
    scale_note: str = Field(default="", description="치수를 어떻게 추정했는지 (치수선 판독, 평형 기준 추정 등)")
    confidence: Literal["high", "medium", "low"] = "medium"


class FurnitureItem(BaseModel):
    id: str
    name: str = Field(description="표시 이름, 예: 3인 패브릭 소파")
    category: FurnitureCategory
    width: float = Field(description="가로 (mm), 정면 기준 좌우 폭")
    depth: float = Field(description="깊이 (mm), 앞뒤")
    height: float = Field(description="높이 (mm)")
    color: str = Field(default="#b08d6e", description="대표 색상 hex")
    source: Literal["user", "ai"] = "ai"
    preferred_room: Optional[str] = Field(default=None, description="배치 희망 방 id 또는 이름")
    note: str = ""
    # 사용자 업로드 사진(data URL). AI 응답 스키마에는 포함하지 않는다.
    image: Optional[str] = None


class Placement(BaseModel):
    item_id: str
    room_id: str
    x: float = Field(description="가구 중심 x (mm)")
    y: float = Field(description="가구 중심 y (mm)")
    rotation: Literal[0, 90, 180, 270] = Field(
        description="가구 정면이 향하는 방향. 0=아래(+y), 90=오른쪽(+x), 180=위(-y), 270=왼쪽(-x). "
                    "90/270이면 도면상 점유 폭과 깊이가 서로 바뀐다")
    reason: str = ""


class HouseholdMember(BaseModel):
    role: str = Field(description="예: 아빠, 엄마, 아들, 할머니, 반려견")
    age: Optional[int] = None
    note: str = ""


class LayoutRequest(BaseModel):
    floorplan: FloorPlan
    items: list[FurnitureItem] = Field(default_factory=list, description="사용자가 직접 등록한 실제 제품")
    requested: list[str] = Field(default_factory=list, description="제품 없이 필요하다고만 요청한 가구/가전 이름")
    household: list[HouseholdMember] = Field(default_factory=list)
    requirements: str = ""
    style: str = ""
    floorplan_image: Optional[str] = Field(default=None, description="원본 도면 data URL (선택)")


class Layout(BaseModel):
    items: list[FurnitureItem]
    placements: list[Placement]
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)
    engine: Literal["ai", "rule"] = "rule"


# ---- Claude 구조화 출력용 스키마 (이미지 등 대용량 필드를 제외) ----

class AIFurnitureSpec(BaseModel):
    id: str
    name: str
    category: FurnitureCategory
    width: float
    depth: float
    height: float
    color: str


class AILayoutResult(BaseModel):
    added_items: list[AIFurnitureSpec] = Field(
        description="요청 목록과 가족 구성에 맞춰 새로 추가한 가구/가전 (사용자 제품은 제외)")
    placements: list[Placement]
    summary: str = Field(description="배치 콘셉트와 가족 구성 반영 내용을 한국어 3~6문장으로")
    warnings: list[str] = Field(description="공간 부족 등으로 배치하지 못했거나 주의할 점")


class AIFurnitureAnalysis(BaseModel):
    name: str
    category: FurnitureCategory
    width: float
    depth: float
    height: float
    color: str
    note: str = Field(description="재질/스타일 등 짧은 설명")
