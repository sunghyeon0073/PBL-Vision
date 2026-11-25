"""
카카오톡 메시지 알림 모듈
- 감지 프로그램(safety_alarm.py 등)에서 import 해서 send_alert("메시지") 로 호출한다.
- 처음 한 번만 아래 순서로 토큰을 발급받는다.
    1) python kakao_notify.py setup      -> REST API 키·클라이언트 시크릿 입력 (kakao_config.json 생성)
    2) python kakao_notify.py url        -> 출력된 주소를 브라우저에서 열고 로그인/동의
    3) 이동된 주소의 code=... 값을 복사
    4) python kakao_notify.py auth <code> -> kakao_token.json 저장
    5) python kakao_notify.py test       -> 나에게 테스트 메시지 발송
"""
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "kakao_config.json"
TOKEN_FILE = BASE / "kakao_token.json"

AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
FRIENDS_URL = "https://kapi.kakao.com/v1/api/talk/friends"
FRIEND_SEND_URL = "https://kapi.kakao.com/v1/api/talk/friends/message/default/send"
IMAGE_UPLOAD_URL = "https://kapi.kakao.com/v2/api/talk/message/image/upload"

COOLDOWN_SEC = 60          # 같은 종류의 알림은 이 시간 안에 다시 보내지 않음
_last_sent = {}


# ---------- 설정 / 토큰 파일 ----------
DEFAULT_CONFIG = {
    "rest_api_key": "",
    "redirect_uri": "https://localhost",
    "client_secret": "",
    "link_url": "https://connect.raspberrypi.com",
    "friend_uuids": []
}


def setup_config():
    """REST API 키와 클라이언트 시크릿을 물어보고 kakao_config.json 을 만든다."""
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    print("카카오 디벨로퍼스 > 내 애플리케이션 > 앱 키 / 보안 메뉴의 값을 입력하세요. (엔터 = 기존 값 유지)")
    for key, label in [("rest_api_key", "REST API 키"), ("client_secret", "클라이언트 시크릿")]:
        val = input(f"{label} [{'설정됨' if cfg.get(key) else '없음'}]: ").strip()
        if val:
            cfg[key] = val
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("저장 완료:", CONFIG_FILE.name, "-> 다음: python kakao_notify.py url")


def load_config():
    if not CONFIG_FILE.exists():
        sys.exit("kakao_config.json 이 없습니다. 먼저 python kakao_notify.py setup 을 실행하세요.")
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    if not cfg["rest_api_key"]:
        sys.exit("REST API 키가 비어 있습니다. python kakao_notify.py setup 을 실행하세요.")
    return cfg


def save_token(data, old=None):
    token = dict(old or {})
    token["access_token"] = data["access_token"]
    token["expires_at"] = time.time() + data.get("expires_in", 0) - 60
    if "refresh_token" in data:            # 갱신 응답에는 없을 수도 있음
        token["refresh_token"] = data["refresh_token"]
    TOKEN_FILE.write_text(json.dumps(token, indent=2), encoding="utf-8")
    return token


def _secret(cfg, data):
    if cfg.get("client_secret"):
        data["client_secret"] = cfg["client_secret"]
    return data


# ---------- 토큰 발급 / 갱신 ----------
def auth_url(cfg, scope="talk_message"):
    q = urlencode({"response_type": "code", "client_id": cfg["rest_api_key"],
                   "redirect_uri": cfg["redirect_uri"], "scope": scope})
    return f"{AUTH_URL}?{q}"


def issue_token(cfg, code):
    r = requests.post(TOKEN_URL, data=_secret(cfg, {
        "grant_type": "authorization_code", "client_id": cfg["rest_api_key"],
        "redirect_uri": cfg["redirect_uri"], "code": code}), timeout=10)
    r.ok or print(r.text); r.raise_for_status()
    return save_token(r.json())


def get_access_token(cfg):
    if not TOKEN_FILE.exists():
        raise RuntimeError("토큰이 없습니다. 'python kakao_notify.py url'부터 진행하세요.")
    token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    if time.time() < token.get("expires_at", 0):
        return token["access_token"]
    r = requests.post(TOKEN_URL, data=_secret(cfg, {
        "grant_type": "refresh_token", "client_id": cfg["rest_api_key"],
        "refresh_token": token["refresh_token"]}), timeout=10)
    r.ok or print(r.text); r.raise_for_status()
    return save_token(r.json(), old=token)["access_token"]


# ---------- 메시지 발송 ----------
def upload_image(cfg, image_path):
    """사진 파일을 카카오 서버에 올리고 메시지에 넣을 이미지 URL을 받는다 (5MB 미만)"""
    with open(image_path, "rb") as fp:
        r = requests.post(IMAGE_UPLOAD_URL,
                          headers={"Authorization": f"KakaoAK {cfg['rest_api_key']}"},
                          files={"file": fp}, timeout=20)
    r.ok or print(r.text); r.raise_for_status()
    return r.json()["infos"]["original"]


def _template(cfg, text, image=None):
    link = {"web_url": cfg["link_url"], "mobile_web_url": cfg["link_url"]}
    if image:                       # 사진이 있으면 피드 템플릿
        lines = text.split("\n")
        return json.dumps({
            "object_type": "feed",
            "content": {
                "title": lines[0][:100],
                "description": "\n".join(lines[1:])[:200],
                "image_url": image["url"],
                "image_width": image.get("width", 640),
                "image_height": image.get("height", 480),
                "link": link,
            },
            "buttons": [{"title": "원격 화면 열기", "link": link}],
        }, ensure_ascii=False)
    return json.dumps({
        "object_type": "text",
        "text": text[:200],
        "link": link,
        "button_title": "원격 화면 열기",
    }, ensure_ascii=False)


def send_to_me(text, image=None):
    cfg = load_config()
    headers = {"Authorization": f"Bearer {get_access_token(cfg)}"}
    r = requests.post(MEMO_URL, headers=headers,
                      data={"template_object": _template(cfg, text, image)}, timeout=10)
    r.ok or print(r.text); r.raise_for_status()
    return r.json()


def send_to_friends(text, uuids=None, image=None):
    cfg = load_config()
    uuids = uuids or cfg.get("friend_uuids", [])
    if not uuids:
        return None
    headers = {"Authorization": f"Bearer {get_access_token(cfg)}"}
    r = requests.post(FRIEND_SEND_URL, headers=headers, data={
        "receiver_uuids": json.dumps(uuids[:5]),
        "template_object": _template(cfg, text, image)}, timeout=10)
    r.ok or print(r.text); r.raise_for_status()
    return r.json()


def list_friends():
    cfg = load_config()
    headers = {"Authorization": f"Bearer {get_access_token(cfg)}"}
    r = requests.get(FRIENDS_URL, headers=headers, timeout=10)
    r.ok or print(r.text); r.raise_for_status()
    return r.json()


def send_alert(text, kind="default", image_path=None):
    """감지 프로그램에서 부르는 함수. 같은 kind는 COOLDOWN_SEC 동안 한 번만 보낸다.
    image_path를 주면 사진을 올려서 사진이 들어간 메시지로 보낸다 (실패하면 글자만 보냄).
    실패해도 감지 프로그램이 멈추지 않도록 예외를 삼키고 False를 돌려준다."""
    now = time.time()
    if now - _last_sent.get(kind, 0) < COOLDOWN_SEC:
        return False
    _last_sent[kind] = now
    image = None
    if image_path:
        try:
            image = upload_image(load_config(), image_path)
        except Exception as e:
            print(f"[카카오 사진 업로드 실패, 글자만 보냄] {e}")
    try:
        send_to_me(text, image)
        send_to_friends(text, image=image)
        return True
    except Exception as e:
        print(f"[카카오 알림 실패] {e}")
        return False


# ---------- 명령줄 ----------
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "setup":
        setup_config()
        sys.exit()
    cfg = load_config()
    if cmd == "url":
        scope = "talk_message,friends" if "friends" in sys.argv else "talk_message"
        print("아래 주소를 브라우저에서 열고 로그인·동의하세요:\n")
        print(auth_url(cfg, scope))
    elif cmd == "auth" and len(sys.argv) > 2:
        issue_token(cfg, sys.argv[2])
        print("토큰 저장 완료:", TOKEN_FILE.name)
    elif cmd == "test":
        print(send_to_me("[테스트] 안전 감지 시스템 카카오톡 알림입니다."))
    elif cmd == "testimg" and len(sys.argv) > 2:
        img = upload_image(cfg, sys.argv[2])
        print("업로드:", img.get("url"))
        print(send_to_me("[테스트] 사진 알림\n사진이 함께 보이면 성공", img))
    elif cmd == "friends":
        print(json.dumps(list_friends(), ensure_ascii=False, indent=2))
    elif cmd == "pick":
        # 친구 목록을 번호로 보여 주고, 고른 친구의 uuid를 설정 파일에 저장
        elems = list_friends().get("elements", [])
        if not elems:
            sys.exit("받을 수 있는 친구가 없습니다. (친구가 앱에 로그인·동의했는지, 팀원으로 등록됐는지 확인)")
        for i, fr in enumerate(elems, 1):
            print(f"{i}. {fr.get('profile_nickname', '(이름 없음)')}")
        pick = input("알림 받을 친구 번호 (쉼표로 구분, 최대 5명): ")
        idx = [int(x) - 1 for x in pick.replace(" ", "").split(",") if x.isdigit()]
        cfg["friend_uuids"] = [elems[i]["uuid"] for i in idx if 0 <= i < len(elems)][:5]
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print("저장 완료:", [elems[i].get("profile_nickname") for i in idx if 0 <= i < len(elems)][:5])
    elif cmd == "testfriend":
        print(send_to_friends("[테스트] 안전 감지 시스템 친구 알림입니다."))
    else:
        print("사용법: python kakao_notify.py setup | url [friends] | auth <code> | test | testimg <사진> | friends | pick | testfriend")
