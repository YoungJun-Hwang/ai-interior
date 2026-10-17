"""AI 인테리어 플래너 서버. 실행: uvicorn backend.main:app --reload"""

from __future__ import annotations

import base64
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import ai, catalog
from .demo import sample_floorplan
from .layout_engine import default_items, rule_layout
from .models import FloorPlan, FurnitureItem, Layout, LayoutRequest

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
MAX_UPLOAD = 15 * 1024 * 1024

app = FastAPI(title="AI 인테리어 플래너")


async def _read(upload: UploadFile) -> bytes:
    data = await upload.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "파일이 너무 큽니다 (최대 15MB).")
    if not (upload.content_type or "").startswith("image/"):
        raise HTTPException(415, "이미지 파일만 올릴 수 있습니다.")
    return data


@app.get("/api/status")
def status() -> dict:
    return {"ai_enabled": ai.enabled(), "model": ai.MODEL if ai.enabled() else None}


@app.get("/api/floorplan/sample", response_model=FloorPlan)
def floorplan_sample() -> FloorPlan:
    return sample_floorplan()


@app.post("/api/floorplan/analyze", response_model=FloorPlan)
async def floorplan_analyze(image: UploadFile = File(...), hint: str = Form("")) -> FloorPlan:
    data = await _read(image)
    if not ai.enabled():
        raise HTTPException(503, "ANTHROPIC_API_KEY가 설정되지 않아 도면을 자동 판독할 수 없습니다. "
                                 "샘플 도면을 사용하거나 방 치수를 직접 입력해 주세요.")
    try:
        return ai.analyze_floorplan(data, hint)
    except ai.AIError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/furniture/analyze", response_model=FurnitureItem)
async def furniture_analyze(
    image: Optional[UploadFile] = File(None),
    name: str = Form(""),
    width: Optional[float] = Form(None),
    depth: Optional[float] = Form(None),
    height: Optional[float] = Form(None),
    preferred_room: str = Form(""),
) -> FurnitureItem:
    data = await _read(image) if image is not None and image.filename else None
    item_id = "u" + uuid.uuid4().hex[:6]
    data_url = None
    if data:
        data_url = f"data:{image.content_type};base64," + base64.b64encode(data).decode()

    if data and ai.enabled():
        try:
            r = ai.analyze_furniture(data, name, width, depth, height)
        except ai.AIError as e:
            raise HTTPException(502, str(e)) from e
        return FurnitureItem(id=item_id, name=r.name, category=r.category, width=r.width, depth=r.depth,
                             height=r.height, color=r.color, source="user", note=r.note, image=data_url,
                             preferred_room=preferred_room or None)

    # AI 없이: 이름으로 종류를 추정하고, 비어 있는 치수는 기본 규격으로 채운다
    if not name:
        raise HTTPException(400, "AI 분석이 꺼져 있을 때는 제품 이름이 필요합니다.")
    cat = catalog.guess_category(name)
    _, w, d, h, color, _, _ = catalog.spec(cat)
    return FurnitureItem(id=item_id, name=name, category=cat, width=width or w, depth=depth or d,
                         height=height or h, color=color, source="user", image=data_url,
                         preferred_room=preferred_room or None,
                         note="" if (width and depth and height) else "일부 치수는 기본 규격으로 채웠습니다.")


@app.post("/api/layout", response_model=Layout)
def layout(req: LayoutRequest, engine: str = "auto") -> Layout:
    if not req.floorplan.rooms:
        raise HTTPException(400, "도면에 방이 없습니다.")
    if engine != "rule" and ai.enabled():
        try:
            return ai.plan_layout(req)
        except ai.AIError as e:
            if engine == "ai":
                raise HTTPException(502, str(e)) from e
            fallback = _rule(req)
            fallback.warnings.insert(0, f"AI 배치 실패로 규칙 기반 배치를 사용했습니다: {e}")
            return fallback
    if engine == "ai":
        raise HTTPException(503, "ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    return _rule(req)


def _rule(req: LayoutRequest) -> Layout:
    items = list(req.items) + default_items(req.floorplan, req.items, req.requested, req.household, req.requirements)
    res = rule_layout(req.floorplan, items, req.household, req.requirements)
    members = ", ".join(f"{m.role}{f'({m.age}세)' if m.age is not None else ''}" for m in req.household) or "기본 4인 가족"
    res.summary = (f"가족 구성({members})을 기준으로 규칙 기반 엔진이 배치했습니다. 문 앞 동선과 가구 정면 사용 공간을 비우고, "
                   "소파-TV 시청 축, 침대 머리맡 협탁, 식탁 의자 등 가구 간 관계를 맞췄습니다. "
                   "ANTHROPIC_API_KEY를 설정하면 요구사항 문장까지 이해하는 AI 배치를 사용할 수 있습니다.")
    return res


@app.post("/api/video/convert")
async def video_convert(video: UploadFile = File(...)) -> Response:
    """브라우저에서 녹화한 WebM을 MP4(H.264)로 변환한다. ffmpeg가 필요하다."""
    data = await video.read()
    if len(data) > 300 * 1024 * 1024:
        raise HTTPException(413, "영상이 너무 큽니다.")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.webm", Path(tmp) / "out.mp4"
        src.write_bytes(data)
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20", "-movflags", "+faststart",
                            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", str(dst)],
                           check=True, capture_output=True, timeout=600)
        except FileNotFoundError as e:
            raise HTTPException(501, "서버에 ffmpeg가 없어 MP4로 변환할 수 없습니다. WebM 파일을 사용해 주세요.") from e
        except subprocess.CalledProcessError as e:
            raise HTTPException(500, "영상 변환 실패: " + e.stderr.decode(errors="ignore")[-300:]) from e
        return Response(dst.read_bytes(), media_type="video/mp4",
                        headers={"Content-Disposition": 'attachment; filename="interior.mp4"'})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="static")
