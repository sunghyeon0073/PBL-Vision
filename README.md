# Vision AI 작업자 안전 감지 시스템 (PBL-Vision)

웹캠 영상에서 작업자의 **안전모·안전조끼 착용 여부**를 실시간으로 확인하는 프로그램입니다.
미착용이 감지되면 다음 순서로 경고합니다.

1. 화면에 빨간 경고 테두리와 미착용 항목을 표시합니다.
2. 라즈베리파이에서는 GPIO17 릴레이로 **경광등**을 켭니다.
3. 경고 순간의 화면을 사진으로 저장하고 `log.csv`에 기록합니다.
4. 사진이 들어간 **카카오톡 알림**을 나와 지정한 친구(최대 5명)에게 보냅니다.

Windows 노트북에서도 실행할 수 있습니다. 이때는 릴레이 없이 감지, 기록, 카카오 알림만 동작합니다.

---

## 프로젝트 소개

### 배경
건설·제조 현장에서는 보호구를 쓰지 않아서 생기는 사고가 끊이지 않습니다. 하지만 관리자가 계속 지켜보기는 어렵습니다.
이 프로젝트는 카메라 한 대와 YOLO 객체 탐지 모델로 보호구 착용 여부를 자동으로 확인하는 시스템입니다.
현장에서는 경광등으로, 원격에서는 카카오톡으로 바로 알려 줍니다.

### 동작 방식

```
웹캠 프레임 ─▶ YOLO11n (ppe_n.pt) ─▶ 클래스별 확신도 필터 ─▶ 위반 판단
                                                              │
         ┌────────────────────────────────────────────────────┘
         ▼
 연속 5프레임 위반 ─▶ 경고 ON ─▶ 릴레이(경광등) ON + 사진/CSV 저장 + 카카오톡 알림
 연속 15프레임 정상 ─▶ 경고 OFF ─▶ 릴레이 OFF + 경고 지속 시간 기록
 경고가 계속되면 10초마다 사진 추가 저장
```

**위반 판단 기준** (`safety_alarm.py`의 `check_violation`)
- 모델이 `NO-Hardhat`이나 `NO-Safety Vest`를 직접 감지하면 위반입니다.
- 감지된 사람(`Person`)마다 확인합니다.
  - 머리 쪽 영역(박스 위쪽 45%)에 안전모가 없으면 위반입니다.
  - 몸 영역 안에 조끼가 없으면 위반입니다.
- 사람은 못 찾았지만 장비 일부만 보이면, 빠진 장비를 위반으로 봅니다.
- 한두 프레임만 잘못 감지돼도 경고가 울리지 않도록 ON 5프레임, OFF 15프레임의 여유를 둡니다.

### 사용 기술
- **모델**: YOLO11n, [Construction Site Safety v30](https://universe.roboflow.com/) 데이터셋으로 학습 (CC BY 4.0)
- **라이브러리**: Ultralytics, OpenCV, Pillow (한글 HUD), Requests (카카오 API)
- **하드웨어(선택)**: 라즈베리파이, 릴레이 모듈, 경광등
- **알림**: 카카오톡 메시지 API (나에게 보내기, 친구에게 보내기, 이미지 업로드)

### 파일 구성

| 파일 | 설명 |
|---|---|
| `safety_alarm.py` | 메인 프로그램. 감지, 위반 판단, 릴레이, 사진/CSV 로그, 카카오 알림 |
| `hud.py` | 감시 화면(HUD). 상단 시계·FPS, 하단 상태 바, 감지 박스, 경고 테두리 |
| `kakao_notify.py` | 카카오톡 알림 모듈. 토큰 발급·자동 갱신, 사진 업로드, 친구 전송 |
| `ppe_n.pt` | 학습된 YOLO11n 보호구 탐지 모델 |
| `kakao_config.example.json` | 카카오 설정 파일 예시 |
| `requirements.txt` | 파이썬 패키지 목록 |
| `violations/` | 실행하면 생성됨. 위반 사진과 `log.csv` 저장 (git에 올라가지 않음) |

---

## 처음 실행할 때 해야 할 작업 (체크리스트)

- [ ] Python 3.12 설치
- [ ] 저장소 받기, 가상환경 만들기, 패키지 설치 → [1. 설치](#1-설치)
- [ ] 웹캠 연결 (노트북 내장 카메라도 됨)
- [ ] 카카오 디벨로퍼스 앱 만들기, 키 입력, 토큰 발급 → [2. 카카오 알림 설정](#2-카카오-알림-설정-처음-한-번)
  - 카카오 알림이 필요 없으면 건너뛰어도 됩니다. 이때는 감지와 기록만 동작합니다.
- [ ] `python safety_alarm.py` 실행 → [3. 실행](#3-실행)
- [ ] (선택) 친구에게도 알림 보내기 → [4. 친구에게도 보내기](#4-친구에게도-보내기-선택)
- [ ] (선택) 라즈베리파이와 경광등 연결 → [5. 라즈베리파이](#5-라즈베리파이에서-실행-선택)

---

## 1. 설치

### Windows (Python 3.12)

```powershell
git clone https://github.com/sunghyeon0073/PBL-Vision.git
cd PBL-Vision
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

> `Activate.ps1` 실행이 막히면 먼저 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`를 실행하세요.
> NVIDIA GPU가 있으면 CPU용 torch 대신 [PyTorch 사이트](https://pytorch.org/get-started/locally/)의 CUDA 버전을 설치하면 더 빠릅니다.

### 라즈베리파이 / Linux

```bash
git clone https://github.com/sunghyeon0073/PBL-Vision.git ~/safety
cd ~/safety
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
sudo apt install fonts-nanum      # 화면에 한글 표시 (없으면 영어로 표시됨)
```

---

## 2. 카카오 알림 설정 (처음 한 번)

1. [카카오 디벨로퍼스](https://developers.kakao.com)에서 앱을 만들고 아래 항목을 설정합니다.
   - **카카오 로그인** 활성화
   - **Redirect URI**에 `https://localhost` 등록
   - **동의 항목**에서 `카카오톡 메시지 전송(talk_message)` 사용
   - **보안**에서 Client Secret 발급 및 활성화
2. 키를 입력합니다.
   ```powershell
   python kakao_notify.py setup
   ```
   REST API 키와 클라이언트 시크릿을 붙여넣으면 `kakao_config.json`이 만들어집니다.
3. 토큰을 발급합니다.
   ```powershell
   python kakao_notify.py url
   ```
   - 출력된 주소를 브라우저에서 열고 로그인합니다.
   - "사이트에 연결할 수 없음" 화면이 나오면 정상입니다. 주소창에서 `code=` 뒤의 값을 복사합니다.
   ```powershell
   python kakao_notify.py auth <code>
   python kakao_notify.py test
   ```
   - code는 약 10분 뒤 만료되고, 한 번만 쓸 수 있습니다.
   - 카톡 "나와의 채팅"에 메시지가 오면 성공입니다.
   - 사진 알림은 `python kakao_notify.py testimg <사진경로>`로 시험해 볼 수 있습니다.

토큰은 만료되면 refresh token으로 자동 갱신됩니다.
같은 종류의 알림은 60초에 한 번만 보냅니다(`COOLDOWN_SEC`).

---

## 3. 실행

```powershell
cd PBL-Vision
.\venv\Scripts\Activate.ps1
python safety_alarm.py      # 기본 카메라(0번)
python safety_alarm.py 1    # 다른 카메라
```

| 키 | 동작 |
|---|---|
| `q` | 종료 (터미널에서 `Ctrl + C`도 가능) |
| `f` | 전체 화면 켜기/끄기 |

**화면 읽는 법**
- 하단 상태는 `STANDBY`(작업자 없음), `CHECK`(미착용 판정 중), `SAFE`(정상), `WARNING`(경고) 중 하나입니다.
- 오른쪽 아래의 안전모·조끼 아이콘은 착용 상태를 보여 줍니다. 초록 ✓는 착용, 빨강 ✕는 미착용, 회색은 판단할 수 없는 상태입니다.
- 위반 사진과 `log.csv`는 `violations/` 폴더에 저장됩니다.

---

## 4. 친구에게도 보내기 (선택)

카카오 앱에 "카카오톡 친구 목록/메시지" 권한이 있어야 합니다. 권한 승인 전에는 팀원끼리만 테스트할 수 있습니다.

1. 동의 항목에서 `friends`를 켭니다.
2. 받을 사람을 **앱 → 멤버**에 추가합니다. 받는 사람은 보내는 사람과 카톡 친구여야 하고, 앱에 한 번 로그인해야 합니다.
3. 친구 권한을 포함해서 토큰을 다시 받고, 받을 친구를 고릅니다.
   ```powershell
   python kakao_notify.py url friends
   python kakao_notify.py auth <code>
   python kakao_notify.py pick
   python kakao_notify.py testfriend
   ```
   - `pick`에서 받을 친구 번호를 쉼표로 구분해 고릅니다. 최대 5명입니다.

---

## 5. 라즈베리파이에서 실행 (선택)

1. **릴레이 연결**: 릴레이 모듈의 IN을 **GPIO17(물리 11번 핀)** 에 연결하고, 경광등을 릴레이 접점에 연결합니다.
2. **릴레이 방향 확인**: `pinctrl set 17 op dh`로 릴레이가 켜지면 그대로 두면 됩니다. `dl`로 켜진다면 `safety_alarm.py`에서 `RELAY_ON_HIGH = False`로 바꿉니다.
3. **속도 높이기 (NCNN 변환)**: Pi에서는 NCNN 모델이 훨씬 빠릅니다. 아래처럼 변환해 두면 프로그램이 자동으로 변환본을 사용합니다.
   ```bash
   yolo export model=ppe_n.pt format=ncnn imgsz=640   # ppe_n_ncnn_model/ 생성
   ```
4. **실행** (모니터에 화면 표시)
   ```bash
   cd ~/safety && source venv/bin/activate
   DISPLAY=:0 QT_QPA_PLATFORM=xcb python safety_alarm.py
   ```

`pinctrl` 명령이 없는 환경(Windows 등)에서는 릴레이 제어를 자동으로 건너뜁니다.

---

## 설정 바꾸기

`safety_alarm.py` 위쪽의 `===== 설정 =====` 부분에서 값을 바꿀 수 있습니다.

| 항목 | 기본값 | 설명 |
|---|---|---|
| `CONF_TABLE` | 0.30 ~ 0.45 | 클래스별 최소 확신도. 낮추면 더 많이 잡히지만 오탐이 늘어납니다 |
| `ON_FRAMES` | 5 | 연속 몇 프레임 위반이면 경고를 켤지 |
| `OFF_FRAMES` | 15 | 연속 몇 프레임 정상이면 경고를 끌지 |
| `SNAPSHOT_INTERVAL` | 10 | 경고 중 사진을 추가로 저장하는 간격(초) |
| `IMGSZ` | 640 | 모델 입력 크기 |
| `RELAY_PIN` | 17 | 릴레이 GPIO 번호 |

---

## 오류 해결

| 증상 / 코드 | 원인 | 해결 |
|---|---|---|
| `웹캠을 열 수 없습니다` | 카메라 번호가 틀렸거나 다른 프로그램이 카메라 사용 중 | `python safety_alarm.py 1`처럼 번호를 바꾸거나 다른 프로그램 종료 |
| `카카오 알림 비활성` | `kakao_notify` 불러오기 실패 | 패키지 설치 확인. 알림 없이 감지는 정상 동작 |
| KOE006 | Redirect URI 불일치 | 콘솔에 `https://localhost` 등록 |
| KOE101 | REST API 키 오류 | `setup`에서 REST 키 다시 입력 |
| KOE010 | 클라이언트 시크릿 오류 또는 빈 값 | `setup`에서 현재 시크릿 입력 |
| KOE320 | code 만료 또는 재사용 | `url`부터 다시 진행 |
| 화면 글자가 영어로 나옴 | 한글 폰트 없음 | Windows는 맑은 고딕, Pi는 `sudo apt install fonts-nanum` |

---

## 보안

- `kakao_config.json`, `kakao_token.json`은 `.gitignore`에 들어 있습니다. **절대 커밋하거나 공유하지 마세요.**
- 키가 노출됐다면 카카오 콘솔에서 시크릿을 재발급한 뒤 `python kakao_notify.py setup`으로 새 값을 넣으세요.
- `violations/`의 사진에는 작업자 얼굴이 찍힐 수 있으니 외부에 공유할 때 주의하세요.

## 라이선스

- 모델 학습 데이터: Construction Site Safety v30 (CC BY 4.0)
