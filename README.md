# Vision AI 작업자 안전 감지 시스템

웹캠으로 **안전모·안전조끼 미착용**을 감지하면 사진을 저장하고 **카카오톡으로 사진 알림**을 보냅니다.
라즈베리파이에서는 GPIO17 릴레이로 경광등도 켭니다. Windows에서는 릴레이 없이 동작합니다.

## 구성

| 파일 | 설명 |
|---|---|
| `safety_alarm.py` | 감지 → 위반 판단 → 릴레이 → 사진/CSV 로그 → 카카오 알림 |
| `kakao_notify.py` | 카카오톡 메시지 모듈 (토큰 발급·자동 갱신, 사진 업로드, 친구 전송) |
| `ppe_n.pt` | YOLO11n 학습 모델 (Construction Site Safety v30, CC BY 4.0) |
| `kakao_config.example.json` | 설정 파일 예시 (실제 키는 `kakao_config.json`에, 커밋 금지) |

## 1. 설치 (Windows, Python 3.12)

```powershell
git clone https://github.com/<계정>/<저장소>.git C:\safety
cd C:\safety
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

> `Activate.ps1` 실행이 막히면 먼저 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`을 실행하세요.
> 라즈베리파이는 `python3 -m venv venv && source venv/bin/activate`로 같은 작업을 하면 됩니다.

## 2. 카카오 설정 (처음 한 번)

1. [카카오 디벨로퍼스](https://developers.kakao.com)에서 앱을 만들고 아래를 설정합니다.
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
   - "사이트에 연결할 수 없음" 화면이 나오면 정상입니다. 주소창의 `code=` 뒤 값을 복사합니다.
   ```powershell
   python kakao_notify.py auth <code>
   python kakao_notify.py test
   ```
   - 코드는 약 10분 뒤 만료되고, 한 번만 쓸 수 있습니다.
   - 카톡 "나와의 채팅"에 메시지가 오면 성공입니다.

## 3. 실행

```powershell
cd C:\safety
.\venv\Scripts\Activate.ps1
python safety_alarm.py      # 카메라 0번
python safety_alarm.py 1    # 다른 카메라
```
`q`를 누르면 종료합니다. 위반 사진과 `log.csv`는 `violations/`에 저장됩니다.

## 4. 친구에게도 보내기 (선택)

카카오 앱에 "카카오톡 친구 목록/메시지" 권한이 있어야 합니다. 승인 전에는 팀원끼리만 테스트할 수 있습니다.

1. 동의 항목에서 `friends`를 켭니다.
2. 받을 사람을 **앱 → 멤버**에 추가합니다. 받는 사람은 보내는 사람과 카톡 친구여야 하고, 앱에 한 번 로그인해야 합니다.
3. 친구 권한을 포함해 토큰을 다시 받고, 받을 친구를 고릅니다.
   ```powershell
   python kakao_notify.py url friends
   python kakao_notify.py auth <code>
   python kakao_notify.py pick
   python kakao_notify.py testfriend
   ```
   - `url friends` 다음에 나온 주소를 열고, 새 code로 `auth`를 실행합니다.
   - `pick`에서 받을 친구 번호를 고릅니다. 최대 5명입니다.

## 오류 코드

| 코드 | 원인 | 해결 |
|---|---|---|
| KOE006 | Redirect URI 불일치 | 콘솔에 `https://localhost` 등록 |
| KOE101 | REST API 키 오류 | `setup`에서 REST 키 다시 입력 |
| KOE010 | 클라이언트 시크릿 오류/빈 값 | `setup`에서 현재 시크릿 입력 |
| KOE320 | code 만료/재사용 | `url`부터 다시 |

## 보안

- `kakao_config.json`, `kakao_token.json`은 `.gitignore`에 들어 있습니다. **절대 커밋하거나 공유하지 마세요.**
- 키가 노출됐다면 카카오 콘솔에서 시크릿을 재발급하세요. 그다음 `python kakao_notify.py setup`으로 새 값을 넣으면 됩니다.
