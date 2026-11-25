"""
작업자 안전 감지 + 경고등(릴레이) 제어 + 위반 기록
- 사람이 안전모 '와' 안전조끼를 둘 다 착용해야 정상(OK).
  둘 중 하나라도 없으면 릴레이를 켜서 경고등을 울린다.
- 경고가 켜질 때 사진과 시간을 violations/ 폴더에 저장한다.
- 실행(Pi): cd ~/safety && source venv/bin/activate
            DISPLAY=:0 QT_QPA_PLATFORM=xcb python safety_alarm.py
- 실행(Windows): cd C:/safety ; ./venv/Scripts/Activate.ps1 ; python safety_alarm.py
  (Windows에서는 릴레이 없이 감지 + 기록 + 카카오 알림만 동작)
- 종료: 영상 창에서 q 키, 또는 터미널에서 Ctrl + C
"""
import csv
import platform
import shutil
import sys
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
from ultralytics import YOLO

try:
    import kakao_notify          # 카카오톡 알림 (없으면 알림 없이 동작)
except Exception as e:
    kakao_notify = None
    print(f"카카오 알림 비활성: {e}")

# ===== 설정 =====
# 모델: NCNN 변환본이 있으면 그걸 쓰고(Pi), 없으면 ppe_n.pt를 쓴다(Windows 노트북 등)
MODEL_PATH = "ppe_n_ncnn_model" if Path("ppe_n_ncnn_model").exists() else "ppe_n.pt"
# 웹캠 번호: 기본 0. 다른 카메라는 'python safety_alarm.py 1' 처럼 번호를 붙여 실행
CAMERA = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 0
IMGSZ = 640                       # 입력 크기

# 클래스별 최소 확신도 (착용 장비는 조금 낮게 잡아야 놓치지 않음)
CONF_TABLE = {
    "Person": 0.35,
    "Hardhat": 0.30,
    "Safety Vest": 0.30,
    "NO-Hardhat": 0.45,
    "NO-Safety Vest": 0.45,
}

RELAY_PIN = 17                    # 릴레이 IN이 연결된 GPIO 번호 (11번 핀)
RELAY_ON_HIGH = True              # 'pinctrl set 17 op dh'에서 켜졌으면 True

ON_FRAMES = 5                     # 연속 몇 프레임 위반이면 경고등 ON
OFF_FRAMES = 15                   # 연속 몇 프레임 정상이면 경고등 OFF

LOG_DIR = Path("violations")      # 위반 사진/기록 저장 폴더
SNAPSHOT_INTERVAL = 10            # 경고가 계속될 때 몇 초마다 사진을 추가로 저장할지
# =================


HAS_RELAY = shutil.which("pinctrl") is not None   # Pi에만 있음. 노트북에서는 릴레이 없이 동작


def set_relay(on: bool):
    if not HAS_RELAY:
        return
    level = "dh" if (on == RELAY_ON_HIGH) else "dl"
    subprocess.run(["pinctrl", "set", str(RELAY_PIN), "op", level], check=False)


def center_in(box, area):
    """box의 중심점이 area 안에 있는지"""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return area[0] <= cx <= area[2] and area[1] <= cy <= area[3]


def check_violation(dets):
    """
    dets: [(클래스명, [x1,y1,x2,y2]), ...]
    반환: (위반 여부, 이유 리스트)
    """
    persons = [b for n, b in dets if n == "Person"]
    helmets = [b for n, b in dets if n == "Hardhat"]
    vests = [b for n, b in dets if n == "Safety Vest"]
    names = {n for n, _ in dets}
    reasons = []

    # 1) 미착용이 직접 감지되면 바로 위반
    if "NO-Hardhat" in names:
        reasons.append("안전모 미착용")
    if "NO-Safety Vest" in names:
        reasons.append("안전조끼 미착용")

    # 2) 사람마다 안전모와 조끼가 둘 다 있는지 확인
    for p in persons:
        h = p[3] - p[1]
        upper = [p[0], p[1] - h * 0.15, p[2], p[1] + h * 0.45]   # 머리 쪽 영역
        if not any(center_in(b, upper) for b in helmets):
            reasons.append("안전모 미착용")
        if not any(center_in(b, p) for b in vests):
            reasons.append("안전조끼 미착용")

    # 3) 사람 박스는 못 찾았지만 장비 일부만 보이는 경우
    if not persons and names & {"Hardhat", "Safety Vest"}:
        if not helmets:
            reasons.append("안전모 미착용")
        if not vests:
            reasons.append("안전조끼 미착용")

    reasons = sorted(set(reasons))
    return bool(reasons), reasons


def save_snapshot(view, reasons, writer, f):
    now = datetime.now()
    img_path = LOG_DIR / f"{now:%Y%m%d_%H%M%S}.jpg"
    cv2.imwrite(str(img_path), view)
    writer.writerow([now.strftime("%Y-%m-%d %H:%M:%S"), "ON", " / ".join(reasons), img_path.name])
    f.flush()
    print(f"  사진 저장: {img_path}")
    return now, img_path


def notify(text, kind, image_path=None):
    """카카오톡 알림을 별도 스레드로 보낸다 (네트워크가 느려도 감지는 멈추지 않음)"""
    if kakao_notify is None:
        return
    threading.Thread(target=kakao_notify.send_alert, args=(text, kind, str(image_path) if image_path else None),
                     daemon=True).start()


def main():
    model = YOLO(MODEL_PATH)
    names = model.names
    show_ids = [i for i, n in names.items() if n in CONF_TABLE]
    min_conf = min(CONF_TABLE.values())

    if platform.system() == "Windows":
        cap = cv2.VideoCapture(CAMERA, cv2.CAP_DSHOW)   # Windows에서 카메라가 빨리 열림
    else:
        cap = cv2.VideoCapture(CAMERA)
    if not cap.isOpened():
        print("웹캠을 열 수 없습니다. CAMERA 번호를 확인하세요.")
        return

    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / "log.csv"
    new_file = not log_file.exists()
    f = open(log_file, "a", newline="", encoding="utf-8-sig")
    writer = csv.writer(f)
    if new_file:
        writer.writerow(["시간", "상태", "이유", "사진"])

    set_relay(False)
    alarm_on = False
    bad_count = good_count = 0
    alarm_start = last_snap = 0.0
    reasons = []

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("프레임을 읽지 못했습니다.")
                break

            t0 = time.time()
            result = model.predict(frame, imgsz=IMGSZ, conf=min_conf,
                                   classes=show_ids, verbose=False)[0]
            ms = (time.time() - t0) * 1000

            # 클래스별 확신도 기준으로 다시 거르기
            dets = []
            for c, cf, xyxy in zip(result.boxes.cls, result.boxes.conf, result.boxes.xyxy):
                n = names[int(c)]
                if float(cf) >= CONF_TABLE[n]:
                    dets.append((n, xyxy.tolist()))

            violation, now_reasons = check_violation(dets)

            if violation:
                bad_count += 1
                good_count = 0
                reasons = now_reasons
            else:
                good_count += 1
                bad_count = 0

            view = result.plot()

            if not alarm_on and bad_count >= ON_FRAMES:
                alarm_on = True
                alarm_start = last_snap = time.time()
                set_relay(True)
                print(f"[경고 ON] {', '.join(reasons)}")
                t, img = save_snapshot(view, reasons, writer, f)
                notify(f"[안전 경고]\n{t:%Y-%m-%d %H:%M:%S}\n{' / '.join(reasons)}", "ppe-" + "-".join(reasons), img)
            elif alarm_on and good_count >= OFF_FRAMES:
                alarm_on = False
                set_relay(False)
                dur = time.time() - alarm_start
                writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                 "OFF", f"경고 {dur:.0f}초 지속", ""])
                f.flush()
                print(f"[경고 OFF] 정상 착용 (경고 {dur:.0f}초)")
            elif alarm_on and time.time() - last_snap >= SNAPSHOT_INTERVAL:
                last_snap = time.time()
                save_snapshot(view, reasons, writer, f)

            # 화면 표시
            if alarm_on:
                text, color = "WARNING: " + ", ".join(
                    {"안전모 미착용": "NO HELMET", "안전모 미착용": "NO HELMET",
                     "안전조끼 미착용": "NO VEST", "안전조끼 미착용": "NO VEST"}[r]
                    for r in reasons), (0, 0, 255)
                text = "WARNING: " + ", ".join(sorted(set(text[9:].split(", "))))
            else:
                text, color = "OK", (0, 200, 0)
            cv2.putText(view, f"{text}  {ms:.0f}ms", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            cv2.imshow("Safety Monitor", view)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    except KeyboardInterrupt:
        pass
    finally:
        set_relay(False)   # 종료할 때 경고등은 반드시 끄기
        cap.release()
        cv2.destroyAllWindows()
        f.close()
        print("종료했습니다. 경고등 OFF")


if __name__ == "__main__":
    main()
