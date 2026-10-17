"""Claude API 연동: 도면 판독, 가구 사진 분석, 배치 설계."""

from __future__ import annotations

import base64
import io
import json
import os
from typing import Optional, TypeVar

import anthropic
from PIL import Image
from pydantic import BaseModel

from .models import (
    AIFurnitureAnalysis, AILayoutResult, FloorPlan, FurnitureItem, Layout, LayoutRequest,
)

MODEL = os.environ.get("INTERIOR_MODEL", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
T = TypeVar("T", bound=BaseModel)


class AIError(RuntimeError):
    pass


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


_client: Optional[anthropic.Anthropic] = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def image_block(data: bytes, max_side: int = 2000) -> dict:
    """이미지를 적당한 크기로 줄여 Claude 이미지 블록으로 만든다. 치수 숫자를 읽어야 하므로 너무 줄이지 않는다."""
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB") if img.mode not in ("RGB", "L") else img
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="PNG" if img.mode == "L" else "JPEG", quality=92)
    media = "image/png" if img.mode == "L" else "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": media,
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


def data_url_bytes(url: str) -> bytes:
    return base64.b64decode(url.split(",", 1)[1])


def _ask(system: str, content: list[dict], schema: type[T], effort: str = "high") -> T:
    try:
        resp = client().beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            messages=[{"role": "user", "content": content}],
            output_format=schema,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as e:
        raise AIError("API 키가 올바르지 않습니다.") from e
    except anthropic.RateLimitError as e:
        raise AIError("요청이 많아 잠시 후 다시 시도해 주세요.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"Claude API 오류 ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Claude API에 연결할 수 없습니다.") from e
    if resp.stop_reason == "refusal":
        raise AIError("요청이 안전 정책에 의해 거절되었습니다.")
    if resp.stop_reason == "max_tokens":
        raise AIError("응답이 너무 길어 잘렸습니다. 가구 수를 줄여 다시 시도해 주세요.")
    if resp.parsed_output is None:
        raise AIError("AI 응답을 해석하지 못했습니다.")
    return resp.parsed_output


# ---------------- 1. 도면 판독 ----------------

FLOORPLAN_SYSTEM = """당신은 한국 아파트/주택 평면도를 판독하는 건축 도면 전문가입니다.
평면도 이미지를 보고 각 실(방)의 위치와 실제 치수를 mm 단위 좌표로 추출합니다.

좌표 규칙:
- 도면 외곽의 좌상단이 (0,0), x는 오른쪽, y는 아래쪽으로 증가합니다. 이미지의 위쪽이 y=0입니다.
- 각 실은 축에 정렬된 직사각형 (x, y, width, depth) 으로 표현합니다. 벽 중심선 기준으로 잡고 실끼리 겹치지 않게, 맞닿은 실은 경계 좌표가 정확히 일치하게 합니다.
- ㄱ자 등 직사각형이 아닌 실은 가장 큰 직사각형 하나로 표현하고 나머지는 인접 실(복도 등)로 분리합니다.
- 발코니, 다용도실, 현관, 욕실, 드레스룸, 복도도 빠짐없이 포함합니다.

치수 판독:
- 치수선의 숫자(예: 3,300 / 3300)는 mm입니다. 치수선이 있으면 반드시 그 값을 우선 사용하고, 합계가 전체 치수와 맞는지 검산하세요.
- 치수선이 없으면 표기된 면적(㎡, 평형), 일반 문 폭(방문 900mm, 현관문 1000mm, 욕실문 800mm), 침대 등 그려진 가구 크기로 축척을 추정하고 confidence를 낮게 표시합니다.
- scale_note에 어떤 근거로 치수를 정했는지 한국어로 적습니다.

개구부(openings):
- 문(door), 미닫이/발코니 창호(sliding_door), 문 없는 개구부(opening), 창(window)을 벽 위의 선분 (x1,y1)-(x2,y2) 로 표현합니다.
- 선분은 반드시 수평 또는 수직이며, 해당 벽의 좌표 위에 놓여야 합니다.
- 실과 실을 오갈 수 있는 모든 출입구를 표시하세요. 가구 배치 시 문 앞을 비우는 데 쓰입니다."""


def analyze_floorplan(image: bytes, hint: str = "") -> FloorPlan:
    content = [image_block(image), {"type": "text", "text":
               "이 평면도를 판독해 주세요." + (f"\n참고 정보: {hint}" if hint else "")}]
    fp = _ask(FLOORPLAN_SYSTEM, content, FloorPlan, effort="high")
    _dedupe_ids(fp.rooms, "r")
    _dedupe_ids(fp.openings, "o")
    return fp


def _dedupe_ids(objs, prefix: str) -> None:
    seen = set()
    for i, o in enumerate(objs):
        if not o.id or o.id in seen:
            o.id = f"{prefix}{i + 1}_{len(seen)}"
        seen.add(o.id)


# ---------------- 2. 가구 사진 분석 ----------------

FURNITURE_SYSTEM = """당신은 가구/가전 제품 사진을 보고 제품 정보를 정리하는 인테리어 전문가입니다.
사진 속 제품의 종류(category), 짧은 한국어 이름, 대표 색상(hex), 재질/스타일 메모를 정리합니다.
치수는 mm 단위이며 width=정면에서 본 좌우 폭, depth=앞뒤 깊이, height=높이입니다.
사용자가 치수를 알려주면 그 값을 그대로 사용하고, 없으면 사진 속 라벨/스펙표를 우선 읽고, 그것도 없으면 국내 일반 규격으로 추정합니다."""


def analyze_furniture(image: bytes, name: str = "", width: Optional[float] = None,
                      depth: Optional[float] = None, height: Optional[float] = None) -> AIFurnitureAnalysis:
    given = {k: v for k, v in (("이름", name), ("가로", width), ("깊이", depth), ("높이", height)) if v}
    text = "이 제품을 분석해 주세요."
    if given:
        text += "\n사용자가 입력한 정보(mm): " + json.dumps(given, ensure_ascii=False)
    res = _ask(FURNITURE_SYSTEM, [image_block(image, 1200), {"type": "text", "text": text}],
               AIFurnitureAnalysis, effort="medium")
    # 사용자가 입력한 실측값이 항상 우선
    res.width = width or res.width
    res.depth = depth or res.depth
    res.height = height or res.height
    if name:
        res.name = name
    return res


# ---------------- 3. 배치 설계 ----------------

LAYOUT_SYSTEM = """당신은 한국 주거 공간 전문 인테리어 디자이너입니다. 평면도 데이터(mm)와 가족 구성, 요청 사항을 받아 가구/가전 배치를 설계합니다.

좌표 규칙:
- 도면 좌상단 (0,0), x는 오른쪽, y는 아래쪽. 모든 값은 mm.
- placement의 (x, y)는 가구 중심점. rotation은 가구 정면이 향하는 방향입니다:
  0 = 아래(+y), 90 = 오른쪽(+x), 180 = 위(-y), 270 = 왼쪽(-x).
- rotation이 0/180이면 도면상 점유 크기는 가로 width × 세로 depth, 90/270이면 가로 depth × 세로 width 입니다.
- 벽에 붙는 가구는 등이 벽을 향하게 합니다. 예: 방의 위쪽 벽(y = room.y)에 붙이면 rotation 0, 중심 y = room.y + depth/2 + 20.
- 가구는 반드시 배정한 방(room_id)의 직사각형 안에 완전히 들어가야 하며 서로 겹치면 안 됩니다.
  예외: TV는 TV 거실장 위, 건조기는 세탁기 위(직렬), 러그는 다른 가구 아래에 겹쳐 놓을 수 있습니다.

설계 원칙:
- 문(door) 앞 900mm, 미닫이/개구부 앞 450mm는 비워 동선을 확보합니다. 주 동선 폭은 800mm 이상 (어르신·휠체어 사용 시 1200mm 이상).
- 키 큰 가구(1200mm 이상)로 창을 가리지 않습니다. 침대 머리는 창 아래나 문 정면을 피하고 벽에 붙입니다.
- 옷장·냉장고·세탁기 정면에는 문 열림 공간(600~800mm)을 둡니다.
- 소파와 TV는 마주 보게 하고 시청 거리는 TV 화면 크기의 약 1.5~2.5배로 합니다.
- 가족 구성을 반드시 반영합니다:
  · 영유아: 부모 침실에 아기 침대, 모서리 위험 최소화, 놀이 공간 확보.
  · 학령기 자녀: 개인 방에 침대·책상·책장, 책상은 자연광이 드는 창 쪽.
  · 어르신: 화장실과 가까운 방, 낮은 침대, 넓은 동선, 걸려 넘어질 러그 지양.
  · 재택근무: 생활 소음과 분리된 방에 업무 공간.
  · 반려동물: 동선과 겹치지 않는 조용한 곳에 하우스, 깨지기 쉬운 물건 위치 고려.
- 사용자가 등록한 실제 제품(items)은 치수를 바꾸지 말고 반드시 모두 배치합니다.
- 요청 목록(requested)의 가구/가전은 국내 일반 규격으로 치수를 정해 added_items에 넣고 배치합니다.
- 요청 목록이 비어 있으면 가족 구성에 꼭 필요한 가구/가전을 직접 골라 added_items에 넣습니다. 이미 사용자 제품으로 있는 종류는 중복하지 마세요.
- added_items의 id는 a1, a2, ... 형식으로 고유하게 만듭니다.
- 주방 상부장/하부장, 욕실 설비, 붙박이 시설은 이미 있다고 보고 배치하지 않습니다.
- 공간이 부족해 배치할 수 없는 항목은 warnings에 이유와 함께 적습니다.
- reason에는 왜 그 위치인지 한 문장으로 적습니다."""


def plan_layout(req: LayoutRequest) -> Layout:
    from .layout_engine import repair_layout

    user_items = [i.model_dump(exclude={"image"}) for i in req.items]
    payload = {
        "floorplan": req.floorplan.model_dump(),
        "items": user_items,
        "requested": req.requested,
        "household": [m.model_dump() for m in req.household],
        "requirements": req.requirements,
        "style": req.style,
    }
    content: list[dict] = []
    if req.floorplan_image:
        content.append(image_block(data_url_bytes(req.floorplan_image)))
        content.append({"type": "text", "text": "위는 원본 평면도 이미지입니다. 좌표는 아래 JSON을 기준으로 하세요."})
    content.append({"type": "text", "text": "<design_input>\n" + json.dumps(payload, ensure_ascii=False) + "\n</design_input>\n"
                    "위 입력으로 가구 배치를 설계해 주세요."})
    res = _ask(LAYOUT_SYSTEM, content, AILayoutResult, effort="high")

    items: list[FurnitureItem] = list(req.items)
    taken = {i.id for i in items}
    for k, spec in enumerate(res.added_items):
        iid = spec.id if spec.id not in taken else f"a{len(taken) + k + 1}"
        if iid != spec.id:
            for p in res.placements:
                if p.item_id == spec.id:
                    p.item_id = iid
        taken.add(iid)
        items.append(FurnitureItem(**{**spec.model_dump(), "id": iid}, source="ai"))

    placements, warnings = repair_layout(req.floorplan, items, res.placements, req.household, req.requirements)
    return Layout(items=items, placements=placements, summary=res.summary,
                  warnings=list(res.warnings) + warnings, engine="ai")
