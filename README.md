# AI 인테리어 플래너

평면도 사진 한 장으로 집 구조와 치수를 읽어 내고, 가족 구성과 요청 사항에 맞춰 가구·가전을 배치한 뒤 3D 투어 영상으로 만들어 주는 웹 앱입니다.

## 주요 기능

| 단계 | 내용 |
|---|---|
| 1. 도면 판독 | 평면도 사진을 Claude(비전)가 읽어 방마다 위치와 치수(mm), 문·창·개구부를 추출합니다. 치수선 숫자를 우선 쓰고, 치수선이 없으면 면적이나 표준 문 폭으로 축척을 추정합니다. 결과는 표에서 바로 고칠 수 있습니다. |
| 2. 가족 구성 | 구성원(역할, 나이)과 특별 요청 사항, 스타일을 입력합니다. 영유아, 학령기 자녀, 어르신, 재택근무, 반려동물 여부에 따라 배치 방식이 달라집니다. |
| 3. 가구·가전 | 실제 제품은 사진과 치수를 넣으면 종류, 색상, 치수를 분석해 그 크기 그대로 배치합니다(입력한 실측값이 항상 우선). 제품 없이 "냉장고, 소파"처럼 이름만 요청해도 되고, 아무것도 넣지 않으면 가족 구성에 맞춰 필요한 가구를 알아서 고릅니다. |
| 4. 배치 생성 | Claude가 배치를 설계하고, 규칙 엔진이 결과를 검증해 보정합니다. 방 밖으로 나간 가구, 겹친 가구, 문 앞을 막은 가구는 가장 가까운 유효 위치로 옮깁니다. 2D 배치도에서 가구를 끌어 옮기거나(R 회전, Delete 삭제) 직접 고칠 수 있습니다. |
| 5. 영상 | 3D 장면에서 벽이 올라오고, 가구가 하나씩 놓이고, 방마다 카메라가 돌아보는 투어 영상(1280×720)을 녹화합니다. WebM으로 받거나 서버의 ffmpeg로 MP4로 변환해 받을 수 있습니다. |

API 키가 없어도 샘플 도면과 규칙 기반 배치 엔진으로 전체 흐름을 체험할 수 있습니다.
이 모드에서는 도면 사진 자동 판독과 요구사항 문장 이해가 빠지고, 방 치수는 직접 입력해야 합니다.

## 실행

```bash
cd ai-interior
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # 선택. 없으면 규칙 엔진 모드로 동작
uvicorn backend.main:app --port 8000
# 브라우저에서 http://localhost:8000
```

- 영상 녹화는 Chrome이나 Edge에서 됩니다(MediaRecorder 사용). 녹화하는 동안 탭을 열어 두세요.
- MP4 변환에는 서버에 `ffmpeg`가 설치되어 있어야 합니다.
- 기본 모델은 `claude-opus-5-5`이고 환경변수 `INTERIOR_MODEL`로 바꿀 수 있습니다.

## 구조

```
backend/
  main.py           FastAPI 서버 (API + 정적 파일)
  ai.py             Claude 호출: 도면 판독, 가구 사진 분석, 배치 설계 (구조화 출력)
  layout_engine.py  규칙 기반 배치/검증 엔진: 충돌·문 앞 동선·정면 사용 공간·창 가림 검사, 가구 간 관계 배치
  catalog.py        국내 일반 규격 가구 카탈로그, 이름→종류 추정
  models.py         데이터 스키마 (mm 단위, 도면 좌상단 원점)
  demo.py           샘플 84㎡ 평면도
frontend/
  index.html, style.css, app.js   단계별 입력 UI, 2D 배치도 편집
  scene3d.js        Three.js 3D 장면, 투어 애니메이션, 영상 녹화
  vendor/           three.js r160 (오프라인 동작용 로컬 사본)
tests/              pytest (배치 엔진, API, Claude 요청 모킹)
```

### API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/status` | AI 사용 가능 여부 |
| GET | `/api/floorplan/sample` | 샘플 도면 |
| POST | `/api/floorplan/analyze` | multipart `image`, `hint` → FloorPlan |
| POST | `/api/furniture/analyze` | multipart `image`(선택), `name`, `width`, `depth`, `height`, `preferred_room` → FurnitureItem |
| POST | `/api/layout?engine=auto\|ai\|rule` | LayoutRequest JSON → Layout |
| POST | `/api/video/convert` | multipart `video`(webm) → mp4 |

### 좌표 규칙

- 단위는 mm이고 도면 좌상단이 (0, 0)입니다. x는 오른쪽, y는 아래쪽으로 커집니다.
- 방은 축 정렬 직사각형입니다. ㄱ자 공간은 직사각형 여러 개로 나눕니다.
- 가구 `rotation`은 정면이 향하는 방향입니다(0=아래, 90=오른쪽, 180=위, 270=왼쪽).

### AI 동작 메모

- 세 호출 모두 adaptive thinking과 Pydantic 구조화 출력(`messages.parse`)을 씁니다.
- 안전 분류기가 요청을 거절하면 서버 측에서 다른 모델로 재시도하도록 `fallbacks: "default"`(beta `server-side-fallback-2026-07-01`)를 켜 두었습니다.
- AI 배치에 실패하면 `engine=auto`일 때 자동으로 규칙 엔진 결과를 돌려주고, 경고에 사유를 적습니다.

## 테스트

```bash
python -m pytest -q
```

## 한계와 다음 단계

- 방을 직사각형으로 단순화하므로 사선 벽이나 곡선 벽은 근사치로 표현됩니다.
- 붙박이 주방 가구와 욕실 설비는 이미 있다고 보고 배치하지 않습니다.
- 3D 가구는 종류별 절차적 모델입니다. 실제 제품은 치수와 색상이 반영되고 형태는 일반형입니다.
  실제 제품의 3D 모델(GLB)을 불러오도록 확장할 수 있습니다.
- 영상은 브라우저에서 실시간으로 녹화합니다. 서버에서 렌더링하려면 헤드리스 Chromium으로 같은 페이지를 녹화하면 됩니다.
