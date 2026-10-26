# -*- coding: utf-8 -*-
"""업체 안내문 → 캠페인 칸 — 체험단 사이트·업체가 보낸 안내문을 통째로 붙이면 AI 가 칸을 채운다.

- AI 에겐 JSON 한 덩어리만 받는다(prompt). 받은 값은 여기서 다시 고른다(normalize) — 날짜 꼴·숫자·종류·링크·태그를 확인하고
  모르는 값은 버린다. 화면은 채우기만 하고 저장은 사용자가 확인한 뒤 「저장」으로.
- AI 가 놓쳐도 확실한 것(http 링크·#태그)은 안내문에서 직접 줍는다(scan).
"""
import json
import re
from datetime import date

KINDS = ("experience", "sponsor", "groupbuy")
FIELDS = ("kind", "brand", "title", "visit", "deadline", "start", "provided", "price", "sale_price", "rate",
          "keywords", "tags", "links", "min_photos", "need_map", "notes", "platforms")
PLATFORMS = ("naver_blog", "naver_cafe", "instagram", "tiktok")
URL_RE = re.compile(r"https?://[^\s<>\"'()\[\]]+")
TAG_RE = re.compile(r"(?<![\w&#])#([0-9A-Za-z가-힣_]{1,30})")


def prompt(text, today=None):
    today = today or date.today()
    return """아래는 체험단·협찬·공구 업체가 보낸 안내문이다. 안내문에 **적힌 것만** 골라 JSON 한 덩어리로만 답한다(설명·코드블록 없이).
없는 값은 빈 문자열·빈 목록·0·false 로 둔다. 지어내지 않는다. 오늘은 %s 이다(연도가 없는 날짜는 오늘 뒤로 가장 가까운 날로).

{
  "kind": "experience(방문·배송 체험단) | sponsor(협찬·원고료) | groupbuy(공동구매)",
  "brand": "업체·가게·브랜드 이름",
  "title": "캠페인 이름(짧게)",
  "visit": "방문·체험 예약 날짜와 시간 YYYY-MM-DDTHH:MM, 시간이 없으면 YYYY-MM-DD",
  "deadline": "글을 올릴 마감일(공구는 공구 마감일) YYYY-MM-DD",
  "start": "공구 시작일 YYYY-MM-DD",
  "provided": "제공받는 것(예: 2인 식사권, 제품 1개)",
  "price": "공구 정가", "sale_price": "공구가", "rate": "공구 수수료율 숫자만",
  "keywords": [{"word": "필수 키워드(본문에 넣을 낱말)", "min": 몇 번 이상(숫자, 안 적혀 있으면 1)}],
  "tags": "필수 해시태그를 #붙여 띄어쓰기로",
  "links": ["본문에 넣어야 하는 링크(지도·구매·업체 링크)"],
  "min_photos": 사진 최소 장수(숫자, 없으면 0),
  "need_map": 지도(장소) 첨부가 필수면 true,
  "notes": "위 칸에 안 들어가는 요구사항을 짧게 줄 단위로(예: 주차 정보 꼭, 동영상 1개, 공정위 문구는 배너로)",
  "platforms": ["naver_blog | naver_cafe | instagram | tiktok 중 올릴 곳"]
}

안내문:
\"\"\"
%s
\"\"\"""" % (today.isoformat(), text.strip()[:6000])


def _date(v, with_time=False):
    v = str(v or "").strip().replace(" ", "T")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return v
    if with_time and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", v):
        return v[:16]
    return ""


def _int(v, lo=0, hi=999):
    try:
        return max(lo, min(hi, int(float(str(v).replace(",", "")))))
    except (TypeError, ValueError):
        return 0


def scan(text):
    """안내문에서 직접 줍는 링크·태그."""
    links = []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(".,;")
        if u not in links:
            links.append(u)
    tags = []
    for t in TAG_RE.findall(text or ""):
        if t not in tags:
            tags.append(t)
    return links, tags


def parse_reply(reply):
    """AI 답 → dict(JSON 덩어리를 찾아 읽는다). 못 읽으면 ValueError."""
    m = re.search(r"\{.*\}", reply or "", re.S)
    if not m:
        raise ValueError("AI 답에서 내용을 찾지 못했어요. 다시 해 보거나 직접 채워 주세요.")
    try:
        return json.loads(m.group(0))
    except ValueError:
        raise ValueError("AI 답을 읽지 못했어요. 다시 해 보거나 직접 채워 주세요.")


def normalize(d, text=""):
    """AI 가 준 값 → 캠페인 칸에 넣을 값(확인한 것만)."""
    d = d if isinstance(d, dict) else {}
    out = {"kind": d.get("kind") if d.get("kind") in KINDS else "experience"}
    for k in ("brand", "title", "provided", "price", "sale_price"):
        out[k] = str(d.get(k) or "").strip()[:80]
    out["rate"] = re.sub(r"[^\d.]", "", str(d.get("rate") or ""))[:5]
    out["visit"] = _date(d.get("visit"), with_time=True)
    out["deadline"] = _date(d.get("deadline"))
    out["start"] = _date(d.get("start")) if out["kind"] == "groupbuy" else ""
    kws = []
    for k in d.get("keywords") or []:
        w = str((k or {}).get("word") if isinstance(k, dict) else k or "").strip()
        if w and w not in [x["word"] for x in kws]:
            kws.append({"word": w[:40], "min": _int((k or {}).get("min", 1) if isinstance(k, dict) else 1, 1, 20) or 1})
    out["keywords"] = kws[:10]
    links, tags = scan(text)
    ai_links = [u for u in (d.get("links") or []) if isinstance(u, str) and u.startswith(("http://", "https://"))]
    out["links"] = list(dict.fromkeys(ai_links + links))[:10]
    ai_tags = [t.lstrip("#") for t in re.split(r"[\s,]+", str(d.get("tags") or "")) if t.strip("#")]
    out["tags"] = " ".join("#" + t for t in dict.fromkeys(ai_tags + tags))[:300]
    out["min_photos"] = _int(d.get("min_photos"), 0, 100)
    out["need_map"] = d.get("need_map") is True or str(d.get("need_map")).lower() == "true"
    notes = d.get("notes") or ""
    out["notes"] = ("\n".join(str(x) for x in notes) if isinstance(notes, list) else str(notes)).strip()[:1000]
    out["platforms"] = [p for p in (d.get("platforms") or []) if p in PLATFORMS] or ["naver_blog"]
    return out
