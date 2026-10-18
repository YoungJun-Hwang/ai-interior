"""도면 판독 정확도 점검.

정답을 아는 샘플 도면을 평면도 이미지로 그린 뒤, AI 판독 결과와 방별로 비교한다.

    python -m tools.floorplan_eval render out.png        # 테스트 도면 이미지만 생성
    python -m tools.floorplan_eval run [이미지] [--hint ..] # 판독 + 채점 (ANTHROPIC_API_KEY 필요)

이미지를 주지 않으면 샘플 도면을 그려서 쓴다. 다른 도면 이미지를 주면 정답이 없으므로 판독 결과만 출력한다.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from backend.demo import sample_floorplan
from backend.models import FloorPlan, Room

FONT_PATHS = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "C:/Windows/Fonts/malgun.ttf",
]


def _font(size: int):
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def render(fp: FloorPlan, px_per_m: int = 80) -> bytes:
    """한국 분양 평면도와 비슷하게 벽, 문, 창, 실명, 치수선을 그린다."""
    s = px_per_m / 1000
    pad = 140
    W, H = int(fp.total_width * s) + pad * 2, int(fp.total_depth * s) + pad * 2
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    X = lambda x: pad + x * s  # noqa: E731
    Y = lambda y: pad + y * s  # noqa: E731
    name_f, dim_f = _font(22), _font(18)

    for r in fp.rooms:
        fill = "#eef3f6" if r.type in ("bathroom", "balcony", "utility") else "#fbf6ee"
        d.rectangle([X(r.x), Y(r.y), X(r.x + r.width), Y(r.y + r.depth)], fill=fill)
    for r in fp.rooms:
        d.rectangle([X(r.x), Y(r.y), X(r.x + r.width), Y(r.y + r.depth)], outline="black", width=8)
    for o in fp.openings:
        horiz = abs(o.y2 - o.y1) < abs(o.x2 - o.x1)
        a, b = (X(o.x1), Y(o.y1)), (X(o.x2), Y(o.y2))
        if o.kind == "window":
            d.line([a, b], fill="white", width=9)
            off = (0, 3) if horiz else (3, 0)
            for k in (-1, 1):
                d.line([(a[0] + off[0] * k, a[1] + off[1] * k), (b[0] + off[0] * k, b[1] + off[1] * k)], fill="#3c7fb1", width=2)
        else:
            d.line([a, b], fill="white", width=10)
            if o.kind == "door":
                L = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
                if horiz:
                    box = [a[0] - L, a[1] - L, a[0] + L, a[1] + L]
                    d.arc(box, 0, 90, fill="#555", width=2)
                    d.line([a, (a[0], a[1] + L)], fill="#555", width=2)
                else:
                    box = [a[0] - L, a[1] - L, a[0] + L, a[1] + L]
                    d.arc(box, 0, 90, fill="#555", width=2)
                    d.line([a, (a[0] + L, a[1])], fill="#555", width=2)
            elif o.kind == "sliding_door":
                d.line([a, b], fill="#3c7fb1", width=3)
    for r in fp.rooms:
        cx, cy = X(r.x + r.width / 2), Y(r.y + r.depth / 2)
        d.text((cx, cy), r.name, fill="black", font=name_f, anchor="mm")

    # 치수선: 위쪽은 북측 실들의 가로, 왼쪽은 서측 실들의 세로, 아래/오른쪽은 전체 치수
    def hdim(x1, x2, y, label):
        d.line([(X(x1), y), (X(x2), y)], fill="#444", width=1)
        for x in (x1, x2):
            d.line([(X(x), y - 8), (X(x), y + 8)], fill="#444", width=1)
        d.text(((X(x1) + X(x2)) / 2, y - 12), label, fill="#222", font=dim_f, anchor="mb")

    def vdim(y1, y2, x, label):
        d.line([(x, Y(y1)), (x, Y(y2))], fill="#444", width=1)
        for y in (y1, y2):
            d.line([(x - 8, Y(y)), (x + 8, Y(y))], fill="#444", width=1)
        txt = Image.new("RGBA", (200, 30), (255, 255, 255, 0))
        ImageDraw.Draw(txt).text((100, 15), label, fill="#222", font=dim_f, anchor="mm")
        txt = txt.rotate(90, expand=True)
        img.paste(txt, (int(x - 32), int((Y(y1) + Y(y2)) / 2 - 100)), txt)

    fmt = lambda v: f"{int(round(v)):,}"  # noqa: E731
    xs = sorted({r.x for r in fp.rooms if r.y == 0} | {r.x + r.width for r in fp.rooms if r.y == 0})
    for a, b in zip(xs, xs[1:]):
        hdim(a, b, pad - 50, fmt(b - a))
    hdim(0, fp.total_width, pad - 100, fmt(fp.total_width))
    ys = sorted({r.y for r in fp.rooms if r.x == 0} | {r.y + r.depth for r in fp.rooms if r.x == 0})
    for a, b in zip(ys, ys[1:]):
        vdim(a, b, pad - 50, fmt(b - a))
    vdim(0, fp.total_depth, pad - 100, fmt(fp.total_depth))
    xs = sorted({r.x for r in fp.rooms if r.y + r.depth == fp.total_depth - 1200 or r.type == "living" or r.type == "master_bedroom"}
                | {r.x + r.width for r in fp.rooms if r.type in ("living", "master_bedroom", "bedroom") and r.y >= 3600})
    for a, b in zip(xs, xs[1:]):
        hdim(a, b, H - pad + 60, fmt(b - a))
    ys = sorted({r.y for r in fp.rooms if r.x + r.width == fp.total_width} | {fp.total_depth})
    for a, b in zip(ys, ys[1:]):
        vdim(a, b, W - pad + 50, fmt(b - a))

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ---------- 채점 ----------

def iou(a: Room, b: Room) -> float:
    ix = max(0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
    iy = max(0, min(a.y + a.depth, b.y + b.depth) - max(a.y, b.y))
    inter = ix * iy
    union = a.width * a.depth + b.width * b.depth - inter
    return inter / union if union else 0.0


def score(truth: FloorPlan, pred: FloorPlan) -> dict:
    rows, used = [], set()
    for t in truth.rooms:
        cands = [(iou(t, p), p) for p in pred.rooms if p.id not in used]
        best_iou, best = max(cands, key=lambda c: c[0], default=(0.0, None))
        if best is not None and best_iou > 0:
            used.add(best.id)
        rows.append({
            "room": t.name,
            "truth": f"{t.width:.0f}×{t.depth:.0f}",
            "pred": f"{best.name} {best.width:.0f}×{best.depth:.0f}" if best and best_iou > 0 else "(없음)",
            "iou": round(best_iou, 2),
            "size_err_mm": round(abs(best.width - t.width) + abs(best.depth - t.depth)) if best and best_iou > 0 else None,
            "type_ok": bool(best and best.type == t.type),
        })
    matched = [r for r in rows if r["iou"] > 0]
    return {
        "rooms_truth": len(truth.rooms),
        "rooms_pred": len(pred.rooms),
        "mean_iou": round(sum(r["iou"] for r in rows) / len(rows), 3),
        "rooms_iou_over_0.8": sum(r["iou"] >= 0.8 for r in rows),
        "type_accuracy": round(sum(r["type_ok"] for r in rows) / len(rows), 3),
        "mean_size_err_mm": round(sum(r["size_err_mm"] for r in matched) / len(matched)) if matched else None,
        "total_size_err_mm": round(abs(pred.total_width - truth.total_width) + abs(pred.total_depth - truth.total_depth)),
        "openings_truth": len(truth.openings),
        "openings_pred": len(pred.openings),
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("out")
    run = sub.add_parser("run")
    run.add_argument("image", nargs="?")
    run.add_argument("--hint", default="")
    run.add_argument("--out", default="floorplan_result.json")
    args = ap.parse_args()

    truth = sample_floorplan()
    if args.cmd == "render":
        Path(args.out).write_bytes(render(truth))
        print("저장:", args.out)
        return

    from backend import ai
    if not ai.enabled():
        sys.exit("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    data = Path(args.image).read_bytes() if args.image else render(truth)
    pred = ai.analyze_floorplan(data, args.hint)
    Path(args.out).write_text(pred.model_dump_json(indent=2), encoding="utf-8")
    print(f"판독 결과 저장: {args.out}  ({pred.name}, 신뢰도 {pred.confidence})")
    print("근거:", pred.scale_note)
    if args.image:
        for rm in pred.rooms:
            print(f"  {rm.name:8s} {rm.type:15s} x={rm.x:.0f} y={rm.y:.0f} {rm.width:.0f}×{rm.depth:.0f}")
        return
    res = score(truth, pred)
    for row in res.pop("rows"):
        print(f"  {row['room']:8s} 정답 {row['truth']:>11s} | 판독 {row['pred']:22s} IoU {row['iou']:.2f}"
              f"{'' if row['type_ok'] else '  (종류 다름)'}")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
