"""AI 없이도 동작하도록 하는 기본 가구 카탈로그 (국내 일반 규격, mm)."""

from __future__ import annotations

# category: (기본 이름, width, depth, height, color, 선호 방 타입 순서, 벽에 붙일지)
CATALOG: dict[str, tuple[str, int, int, int, str, tuple[str, ...], bool]] = {
    "bed":             ("퀸 침대", 1600, 2100, 1000, "#d9cbb8", ("master_bedroom", "bedroom", "kids_room"), True),
    "sofa":            ("3인 소파", 2200, 950, 850, "#8a8f98", ("living",), True),
    "armchair":        ("1인 암체어", 800, 800, 850, "#a89078", ("living", "study"), False),
    "dining_table":    ("4인 식탁", 1400, 800, 750, "#a47551", ("dining", "kitchen", "living"), False),
    "chair":           ("의자", 450, 500, 850, "#6b5b4b", ("dining", "kitchen"), False),
    "desk":            ("책상", 1200, 600, 740, "#c8b49a", ("study", "kids_room", "bedroom"), True),
    "office_chair":    ("사무용 의자", 650, 650, 1100, "#333740", ("study", "kids_room", "bedroom"), False),
    "wardrobe":        ("붙박이 옷장", 1800, 600, 2200, "#e6e0d6", ("master_bedroom", "dressroom", "bedroom", "kids_room"), True),
    "dresser":         ("화장대", 900, 450, 750, "#efe7dc", ("master_bedroom", "dressroom"), True),
    "bookshelf":       ("책장", 800, 300, 1800, "#b89a74", ("study", "kids_room", "living"), True),
    "tv_stand":        ("TV 거실장", 1800, 450, 450, "#5d5048", ("living",), True),
    "tv":              ("65인치 TV", 1450, 80, 840, "#111111", ("living",), True),
    "coffee_table":    ("소파 테이블", 1000, 550, 400, "#9c7a5b", ("living",), False),
    "side_table":      ("협탁", 450, 400, 550, "#b39b80", ("master_bedroom", "bedroom"), True),
    "refrigerator":    ("양문형 냉장고", 910, 920, 1800, "#d7dbe0", ("kitchen",), True),
    "kimchi_fridge":   ("김치냉장고", 800, 850, 1800, "#cfd5da", ("kitchen", "utility"), True),
    "washing_machine": ("드럼 세탁기", 690, 790, 990, "#f2f2f2", ("utility", "balcony", "bathroom"), True),
    "dryer":           ("건조기", 690, 790, 990, "#e8e8e8", ("utility", "balcony"), True),
    "air_conditioner": ("스탠드 에어컨", 380, 380, 1800, "#fafafa", ("living",), True),
    "air_purifier":    ("공기청정기", 350, 350, 800, "#f5f5f5", ("living", "master_bedroom", "kids_room"), True),
    "styler":          ("의류관리기", 450, 600, 1850, "#3a3a3a", ("dressroom", "master_bedroom"), True),
    "kitchen_island":  ("아일랜드 식탁", 1600, 900, 900, "#e9e4dc", ("kitchen", "dining"), False),
    "shoe_cabinet":    ("신발장", 1000, 380, 2100, "#ddd5c8", ("entrance",), True),
    "plant":           ("화분", 450, 450, 1200, "#4f7a4a", ("living", "balcony"), False),
    "rug":             ("러그", 2000, 1400, 10, "#c9b79c", ("living",), False),
    "lamp":            ("플로어 스탠드", 400, 400, 1600, "#e0c27a", ("living", "master_bedroom"), False),
    "crib":            ("아기 침대", 1200, 700, 950, "#f3e6d0", ("kids_room", "master_bedroom"), True),
    "piano":           ("업라이트 피아노", 1500, 600, 1250, "#1e1b18", ("living", "kids_room", "study"), True),
    "storage_cabinet": ("수납장", 1000, 450, 1200, "#d8cfc2", ("utility", "storage", "living"), True),
    "pet_house":       ("반려동물 하우스", 700, 600, 600, "#c79d6b", ("living",), True),
    "other":           ("가구", 800, 500, 800, "#a0a0a0", ("living",), False),
}

# 한국어/영어 키워드 → 카테고리
KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("아기침대", "아기 침대", "유아침대", "crib"), "crib"),
    (("침대", "매트리스", "bed"), "bed"),
    (("소파", "쇼파", "sofa", "couch"), "sofa"),
    (("안마의자", "암체어", "안락의자", "1인의자", "리클라이너", "armchair"), "armchair"),
    (("아일랜드", "island"), "kitchen_island"),
    (("식탁", "다이닝", "dining"), "dining_table"),
    (("사무용", "게이밍", "책상의자", "office chair"), "office_chair"),
    (("책상", "desk"), "desk"),
    (("의자", "chair"), "chair"),
    (("옷장", "장롱", "wardrobe", "closet"), "wardrobe"),
    (("화장대", "서랍장", "dresser"), "dresser"),
    (("책장", "선반", "bookshelf"), "bookshelf"),
    (("거실장", "tv장", "티비장", "tv stand"), "tv_stand"),
    (("tv", "티비", "텔레비전", "television"), "tv"),
    (("소파테이블", "커피테이블", "거실테이블", "coffee"), "coffee_table"),
    (("협탁", "사이드테이블", "side table", "nightstand"), "side_table"),
    (("김치냉장고", "김치 냉장고"), "kimchi_fridge"),
    (("냉장고", "fridge", "refrigerator"), "refrigerator"),
    (("세탁기", "washer", "washing"), "washing_machine"),
    (("건조기", "dryer"), "dryer"),
    (("에어컨", "air conditioner"), "air_conditioner"),
    (("공기청정기", "청정기", "purifier"), "air_purifier"),
    (("스타일러", "의류관리기", "styler"), "styler"),
    (("신발장", "shoe"), "shoe_cabinet"),
    (("화분", "식물", "plant"), "plant"),
    (("러그", "카펫", "rug"), "rug"),
    (("스탠드", "조명", "lamp"), "lamp"),
    (("피아노", "piano"), "piano"),
    (("수납장", "캐비닛", "cabinet"), "storage_cabinet"),
    (("강아지", "고양이", "반려", "펫", "캣타워", "pet"), "pet_house"),
]


def guess_category(name: str) -> str:
    key = name.lower().replace(" ", "")
    for words, cat in KEYWORDS:
        if any(w.replace(" ", "") in key for w in words):
            return cat
    return "other"


def spec(category: str) -> tuple[str, int, int, int, str, tuple[str, ...], bool]:
    return CATALOG.get(category, CATALOG["other"])


def against_wall(category: str) -> bool:
    return spec(category)[6]
