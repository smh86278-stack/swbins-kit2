# -*- coding: utf-8 -*-
"""키워드 추천 — 네이버 검색광고 API 키워드 도구(/keywordstool)로 연관 키워드·월간 검색 수를 본다.

- 키 세 개(고객 ID·액세스 라이선스·비밀 키)는 사용자가 searchad.naver.com 에서 직접 받는다(무료).
- 키는 데이터 폴더(OneDrive 로 옮겨 다닐 수 있다)가 아니라 이 PC 로컬 폴더 searchad.json 에 —
  비밀 키는 윈도우 DPAPI 로 잠근다(이 PC·이 사용자만 푼다). 맥·리눅스는 파일 권한만(0600).
- 화면에 키를 돌려주지 않는다(있다/없다만). 결과를 AI 에 자동으로 넘기지 않는다 — 사용자가 고른 낱말만 메모에 넣는다.
- 서명: base64(HMAC-SHA256(비밀 키, "<ms 시각>.<METHOD>.<경로>")) — X-Timestamp·X-API-KEY·X-Customer·X-Signature 헤더.
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.searchad.naver.com"
MAX_HINTS = 5                      # 키워드 도구가 한 번에 받는 씨앗 낱말 수


# ---------- 비밀 키 잠그기 (윈도우 DPAPI) ----------

def _dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    src, out = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0x01, ctypes.byref(out)):    # 0x01 = UI 없이
        raise OSError("DPAPI 실패")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def lock(s):
    if sys.platform == "win32":
        return "dpapi:" + base64.b64encode(_dpapi(s.encode("utf-8"), True)).decode()
    return "plain:" + s


def unlock(s):
    if s.startswith("dpapi:"):
        return _dpapi(base64.b64decode(s[6:]), False).decode("utf-8")
    return s[6:] if s.startswith("plain:") else ""


# ---------- 키 파일 ----------

def keys_path(localdata):
    return os.path.join(localdata, "searchad.json")


def save_keys(localdata, customer, license_, secret):
    customer, license_, secret = (str(x or "").strip() for x in (customer, license_, secret))
    if not (customer.isdigit() and license_ and secret):
        raise ValueError("고객 ID(숫자)·액세스 라이선스·비밀 키를 모두 넣어 주세요.")
    os.makedirs(localdata, exist_ok=True)
    p = keys_path(localdata)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"customer": customer, "license": license_, "secret": lock(secret)}, f)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def load_keys(localdata):
    """→ (customer, license, secret) 또는 None. 다른 PC 에서 잠근 키라 못 풀면 None."""
    try:
        with open(keys_path(localdata), encoding="utf-8") as f:
            d = json.load(f)
        return d["customer"], d["license"], unlock(d["secret"])
    except (OSError, ValueError, KeyError):
        return None


def delete_keys(localdata):
    try:
        os.remove(keys_path(localdata))
    except OSError:
        pass


# ---------- 키워드 도구 ----------

def sign(secret, ts, method, path):
    return base64.b64encode(hmac.new(secret.encode("utf-8"), ("%s.%s.%s" % (ts, method, path)).encode("utf-8"), hashlib.sha256).digest()).decode()


def _count(v):
    """'< 10' 같은 값 → 숫자(10 미만은 5 로 어림)."""
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v or "").replace(",", "").strip()
    return 5 if s.startswith("<") else int(s) if s.isdigit() else 0


def hints_of(text):
    """씨앗 낱말 — 쉼표·줄바꿈으로 나누고, 키워드 도구는 띄어쓰기를 받지 않아 붙인다. 최대 5개."""
    out = []
    for w in text.replace("\n", ",").split(","):
        w = w.replace(" ", "").strip()
        if w and w not in out:
            out.append(w)
    return out[:MAX_HINTS]


def related(keys, hints, timeout=10, api=API):
    """→ [{keyword, pc, mobile, total, comp}] (월간 검색 수 많은 순). keys = (customer, license, secret)."""
    if not hints:
        raise ValueError("씨앗 키워드를 넣어 주세요(쉼표로 5개까지).")
    customer, license_, secret = keys
    path = "/keywordstool"
    ts = str(int(time.time() * 1000))
    q = urllib.parse.urlencode({"hintKeywords": ",".join(hints), "showDetail": "1"})
    req = urllib.request.Request(api + path + "?" + q, headers={
        "X-Timestamp": ts, "X-API-KEY": license_, "X-Customer": str(customer), "X-Signature": sign(secret, ts, "GET", path)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ValueError("검색광고 API 키가 맞지 않아요 — 설정에서 다시 넣어 주세요.")
        if e.code == 429:
            raise ValueError("잠깐 너무 많이 물어봤어요. 조금 뒤에 다시 해 주세요.")
        raise ValueError("검색광고 API 오류(%d)" % e.code)
    out = []
    for k in d.get("keywordList") or []:
        pc, mo = _count(k.get("monthlyPcQcCnt")), _count(k.get("monthlyMobileQcCnt"))
        out.append({"keyword": k.get("relKeyword", ""), "pc": pc, "mobile": mo, "total": pc + mo, "comp": k.get("compIdx", "")})
    return sorted(out, key=lambda x: -x["total"])
