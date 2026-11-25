"""
안전 감지 화면(HUD) 그리기
- 감지 박스: 모서리 브래킷 + 반투명 박스 + 라벨 칩
- 상단 바: 시스템 이름, 카메라, REC, 시계, FPS
- 하단 바: 상태(SAFE/WARNING), 안전모·조끼 체크, 사람 수, 경고 횟수
- 경고 중: 빨간 테두리가 깜빡임, 경고 직전에는 판정 진행 바 표시
한글은 PIL로 그린다 (맑은 고딕 / 나눔고딕). 폰트가 없으면 영어로 표시.
"""
import math
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ----- 색상 (BGR) -----
CYAN = (255, 200, 0)
GREEN = (90, 220, 90)
RED = (60, 60, 255)
AMBER = (0, 190, 255)
WHITE = (240, 240, 240)
GRAY = (150, 150, 150)
DARK = (25, 22, 20)

# 클래스별 색상과 라벨 (한글, 영어)
STYLE = {
    "Person": (CYAN, "작업자", "PERSON"),
    "Hardhat": (GREEN, "안전모", "HELMET"),
    "Safety Vest": (GREEN, "안전조끼", "VEST"),
    "NO-Hardhat": (RED, "안전모 없음", "NO HELMET"),
    "NO-Safety Vest": (RED, "조끼 없음", "NO VEST"),
}
REASON_EN = {"안전모 미착용": "NO HELMET", "안전조끼 미착용": "NO VEST"}

FONT_CANDIDATES = {
    False: ["C:/Windows/Fonts/malgun.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"],
    True: ["C:/Windows/Fonts/malgunbd.ttf",
           "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
           "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"],
}
_font_path = {b: next((p for p in c if Path(p).exists()), None) for b, c in FONT_CANDIDATES.items()}
_font_path[True] = _font_path[True] or _font_path[False]
KOREAN = _font_path[False] is not None
_fonts = {}


def _font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(_font_path[bold], size)
    return _fonts[key]


class _Text:
    """글자는 모아 두었다가 마지막에 한 번에 그린다 (속도)"""

    def __init__(self):
        self.items = []

    def add(self, text, xy, size=16, color=WHITE, bold=False, anchor="la"):
        self.items.append((text, xy, size, color, bold, anchor))

    def render(self, img):
        if not self.items:
            return img
        if not KOREAN:   # 폰트가 없으면 OpenCV 기본 글꼴 (영어만)
            for text, (x, y), size, color, _, anchor in self.items:
                scale = size / 30
                (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
                x -= w if anchor[0] == "r" else w // 2 if anchor[0] == "m" else 0
                y += h // 2 if anchor[1] == "m" else h if anchor[1] == "a" else 0
                cv2.putText(img, text, (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)
            return img
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil)
        for text, xy, size, color, bold, anchor in self.items:
            draw.text(xy, text, font=_font(size, bold), fill=color[::-1], anchor=anchor)
        return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


def _label(ko, en):
    return ko if KOREAN else en


def _panel(img, x1, y1, x2, y2, color=DARK, alpha=0.6):
    x1, y1 = max(0, x1), max(0, y1)
    roi = img[y1:y2, x1:x2]
    if roi.size:
        img[y1:y2, x1:x2] = cv2.addWeighted(roi, 1 - alpha, np.full_like(roi, color), alpha, 0)


def _brackets(img, x1, y1, x2, y2, color, t=3):
    L = int(max(12, min(x2 - x1, y2 - y1) * 0.2))
    for (cx, cy, dx, dy) in [(x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)]:
        cv2.line(img, (cx, cy), (cx + dx * L, cy), color, t, cv2.LINE_AA)
        cv2.line(img, (cx, cy), (cx, cy + dy * L), color, t, cv2.LINE_AA)


def _pill(img, txt, x, y, w, h, color, label, size=15, bold=True, alpha=0.85):
    _panel(img, x, y, x + w, y + h, color, alpha)
    txt.add(label, (x + w // 2, y + h // 2), size, WHITE, bold, "mm")


def draw(frame, dets, state):
    """
    frame : 원본 BGR 영상
    dets  : [(클래스이름, 확신도, [x1,y1,x2,y2]), ...]
    state : dict(alarm, reasons, progress(0~1), fps, ms, camera, events, alarm_sec,
                 helmet, vest, persons)  helmet/vest = True / False / None(판단 불가)
    """
    img = frame.copy()
    H, W = img.shape[:2]
    txt = _Text()
    now = time.time()

    # ----- 감지 박스 -----
    placed = []   # 이미 그린 라벨 위치 (겹치면 아래로 밀기)
    for name, conf, (x1, y1, x2, y2) in sorted(dets, key=lambda d: d[0] != "Person"):
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
        color, ko, en = STYLE.get(name, (WHITE, name, name))
        _panel(img, x1, y1, x2, y2, color, 0.08 if name == "Person" else 0.15)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 1, cv2.LINE_AA)
        _brackets(img, x1, y1, x2, y2, color)
        label = f"{_label(ko, en)} {conf * 100:.0f}%"
        tw = _font(13, True).getlength(label) if KOREAN else len(label) * 8
        lw = int(tw + 14)
        if name == "Person":          # 사람 라벨은 박스 오른쪽 위, 장비 라벨은 박스 안쪽 왼쪽 위 (겹침 방지)
            ly = y1 - 22 if y1 > 70 else y1 + 2
            x1 = max(0, x2 - lw)
        else:
            ly = y1 + 3
            x1 += 3
        while any(x1 < px2 and x1 + lw > px1 and ly < py2 and ly + 20 > py1 for px1, py1, px2, py2 in placed):
            ly += 22
        placed.append((x1, ly, x1 + lw, ly + 20))
        _panel(img, x1, ly, x1 + lw, ly + 20, color, 0.85)
        txt.add(label, (x1 + 7, ly + 10), 13, DARK if color != RED else WHITE, True, "lm")

    # ----- 경고 테두리 (깜빡임) -----
    if state["alarm"]:
        pulse = 0.5 + 0.5 * math.sin(now * 8)
        _panel(img, 0, 0, W, H, RED, 0.10 * pulse)
        cv2.rectangle(img, (0, 0), (W - 1, H - 1), RED, int(4 + 6 * pulse))

    # ----- 상단 바 -----
    _panel(img, 0, 0, W, 44, DARK, 0.75)
    cv2.line(img, (0, 44), (W, 44), CYAN, 1)
    cv2.circle(img, (20, 22), 6, CYAN, -1, cv2.LINE_AA)
    txt.add("AI SAFETY MONITOR", (34, 22), 17, WHITE, True, "lm")
    txt.add(f"CAM {state['camera']:02d}", (210, 22), 13, GRAY, False, "lm")
    if int(now * 2) % 2 == 0:
        cv2.circle(img, (W - 250, 22), 5, RED, -1, cv2.LINE_AA)
    txt.add("REC", (W - 240, 22), 13, RED, True, "lm")
    txt.add(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"), (W - 200, 22), 14, WHITE, False, "lm")
    txt.add(f"{state['fps']:.0f} FPS · {state['ms']:.0f}ms", (W - 12, 58), 12, GRAY, False, "ra")

    # ----- 경고 직전: 판정 진행 바 -----
    if not state["alarm"] and state["progress"] > 0:
        bw = 220
        bx, by = (W - bw) // 2, H - 64 - 36   # 하단 바 바로 위
        _panel(img, bx, by, bx + bw, by + 26, DARK, 0.7)
        cv2.rectangle(img, (bx + 6, by + 18), (bx + 6 + int((bw - 12) * state["progress"]), by + 22), AMBER, -1)
        txt.add(_label("미착용 판정 중...", "CHECKING..."), (bx + bw // 2, by + 9), 12, AMBER, True, "mm")

    # ----- 하단 바 -----
    BH = 64
    top = H - BH
    _panel(img, 0, top, W, H, DARK, 0.78)
    cv2.line(img, (0, top), (W, top), RED if state["alarm"] else CYAN, 2 if state["alarm"] else 1)

    # 상태 표시
    if state["alarm"]:
        _pill(img, txt, 12, top + 12, 130, 40, RED, "WARNING", 17)
        reasons = state["reasons"]
        if KOREAN:
            parts = [k for k, w in (("안전모", "안전모"), ("조끼", "조끼")) if any(w in r for r in reasons)]
            msg = "·".join(parts) + " 미착용"
        else:
            msg = " / ".join(REASON_EN.get(r, r) for r in reasons)
        txt.add(msg, (154, top + 22), 16, (120, 120, 255), True, "lm")
        txt.add(f"{_label('경고 지속', 'DURATION')} {state['alarm_sec']:.0f}s", (154, top + 44), 12, GRAY, False, "lm")
    elif state["persons"] == 0 and state["helmet"] is None:
        _pill(img, txt, 12, top + 12, 130, 40, (90, 90, 90), "STANDBY", 17)
        txt.add(_label("작업자 대기 중", "WAITING FOR WORKER"), (154, top + 32), 15, GRAY, False, "lm")
    elif state["progress"] > 0:
        _pill(img, txt, 12, top + 12, 130, 40, (0, 140, 200), "CHECK", 17)
        txt.add(_label("보호구 확인 중", "CHECKING PPE"), (154, top + 32), 15, AMBER, True, "lm")
    else:
        _pill(img, txt, 12, top + 12, 130, 40, (60, 160, 60), "SAFE", 17)
        txt.add(_label("보호구 정상 착용", "PPE OK"), (154, top + 32), 15, GREEN, True, "lm")

    # 보호구 체크 (안전모 / 조끼)
    cx = W - 330
    for i, (ko, en, ok) in enumerate([("안전모", "HELMET", state["helmet"]), ("조끼", "VEST", state["vest"])]):
        x = cx + i * 95
        color = GRAY if ok is None else GREEN if ok else RED
        cv2.circle(img, (x + 12, top + 32), 10, color, -1 if ok is not None else 2, cv2.LINE_AA)
        if ok is True:
            cv2.polylines(img, [np.array([(x + 7, top + 32), (x + 11, top + 36), (x + 18, top + 27)])], False, DARK, 2, cv2.LINE_AA)
        elif ok is False:
            cv2.line(img, (x + 8, top + 28), (x + 16, top + 36), WHITE, 2, cv2.LINE_AA)
            cv2.line(img, (x + 16, top + 28), (x + 8, top + 36), WHITE, 2, cv2.LINE_AA)
        txt.add(_label(ko, en), (x + 28, top + 32), 14, WHITE, True, "lm")

    # 통계
    sx = W - 130
    txt.add(f"{_label('작업자', 'PERSON')}  {state['persons']}", (sx, top + 22), 13, WHITE, False, "lm")
    txt.add(f"{_label('경고', 'EVENTS')}  {state['events']}", (sx, top + 44), 13, RED if state["events"] else WHITE, False, "lm")
    cv2.line(img, (sx - 14, top + 12), (sx - 14, top + BH - 12), (70, 70, 70), 1)

    return txt.render(img)
