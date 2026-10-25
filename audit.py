# -*- coding: utf-8 -*-
"""올린 뒤 검수 — 올린 글 주소를 읽어 캠페인 조건(키워드·태그·링크·사진 수·지도·협찬 표기)을 다 지켰는지 본다.

- 네이버 블로그는 모바일 주소로 읽는다(refs.naver_blog). 사진은 se-image-resource, 지도는 se-placesMap,
  동영상은 se-video, 태그는 페이지 스크립트의 gsTagName 에서 센다(2026-10 실제 글로 확인).
- 다른 사이트는 본문 글자·<img> 수만 대략 — 지도·태그는 '알 수 없음'으로 둔다.
- 결과는 [{item, ok, detail}] — ok 는 True(통과)·False(빠짐)·None(참고만).
"""
import html
import re
import urllib.parse

import refs

DISCLOSE_WORDS = ("제공받", "지원받", "협찬", "원고료", "광고", "소정의", "수수료", "체험단", "유료 광고")


def facts(url):
    """올린 글 → {url, title, text, photos, map, video, tags, links_html, error}. map·tags 는 모르면 None."""
    out = {"url": url, "title": "", "text": "", "photos": 0, "map": None, "video": None, "tags": None, "body": "", "error": ""}
    try:
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("http(s) 주소만 읽어요")
        final, page = refs.fetch(refs.naver_blog(url) or url)
        nb = refs.naver_blog(final)
        if nb and not urllib.parse.urlparse(final).netloc.startswith("m."):
            final, page = refs.fetch(nb)
        out["title"] = refs.meta(page, "og:title")
        i = page.find("se-main-container")
        if i >= 0:                                       # 네이버 스마트에디터
            body = page[page.rfind("<", 0, i):]
            out["photos"] = len(set(re.findall(r'<img[^>]+(?:data-lazy-src|src)="([^"?]+)[^"]*"[^>]*class="se-image-resource', body)))
            out["map"] = "se-placesMap" in body or "se-map" in body
            out["video"] = "se-video" in body
            m = re.search(r'gsTagName\s*=\s*"([^"]*)"', page)
            out["tags"] = [t.strip() for t in html.unescape(m.group(1)).split(",") if t.strip()] if m else []
        else:
            body = page
            out["photos"] = len(set(re.findall(r"<img[^>]+src=\"([^\"]+)\"", page)))
        out["body"] = html.unescape(body)
        out["text"] = refs.page_text(body)
        if len(out["text"]) < 30:
            raise ValueError("본문을 못 읽었어요(비공개·로그인이 필요한 글이거나 주소가 틀렸을 수 있어요)")
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


def check(f, camp):
    """facts + 캠페인 → [{item, ok, detail}]."""
    camp = camp or {}
    if f["error"]:
        return [{"item": "글 읽기", "ok": False, "detail": f["error"]}]
    text = f["text"]
    whole = (f["title"] + "\n" + text).lower()
    rows = [{"item": "글 읽기", "ok": True, "detail": "%s · %s자" % (f["title"] or f["url"], format(len(re.sub(r"\s", "", text)), ","))}]

    for k in camp.get("keywords") or []:
        w = (k.get("word") or "").strip()
        if not w:
            continue
        n, need = whole.count(w.lower()), int(k.get("min") or 1)
        rows.append({"item": "키워드 " + w, "ok": n >= need, "detail": "%d/%d번 (제목 포함)" % (n, need)})

    tags = [t.lstrip("#") for t in re.split(r"[\s,]+", camp.get("tags") or "") if t.strip("#").strip()]
    if tags:
        have = {t.lower().replace(" ", "") for t in (f["tags"] or [])}
        for t in tags:
            ok = t.lower() in have or ("#" + t).lower() in whole
            rows.append({"item": "태그 #" + t, "ok": ok, "detail": "있어요" if ok else "태그 칸에도 본문에도 없어요"})

    for u in [x.strip() for x in camp.get("links") or [] if x.strip()]:
        ok = u in f["body"] or u in text or u.rstrip("/") in f["body"]
        rows.append({"item": "링크", "ok": ok, "detail": u[:60] + ("" if ok else " — 본문에 없어요")})

    need = int(camp.get("min_photos") or 0)
    rows.append({"item": "사진", "ok": (f["photos"] >= need) if need else None,
                 "detail": "%d장%s" % (f["photos"], " / %d장 이상" % need if need else "")})

    if camp.get("need_map"):
        rows.append({"item": "지도", "ok": bool(f["map"]) if f["map"] is not None else None,
                     "detail": "있어요" if f["map"] else ("없어요 — 장소(지도)를 넣어 주세요" if f["map"] is not None else "이 사이트는 확인할 수 없어요")})
    elif f["map"]:
        rows.append({"item": "지도", "ok": None, "detail": "있어요"})

    if camp.get("brand"):
        pos = min([p for p in (text.find(w) for w in DISCLOSE_WORDS) if p >= 0] or [-1])
        if pos < 0:
            rows.append({"item": "협찬 표기", "ok": False, "detail": "글자로는 못 찾았어요 — 배너 이미지로 넣었다면 괜찮아요"})
        else:
            front = pos <= max(300, len(text) // 5)
            rows.append({"item": "협찬 표기", "ok": front, "detail": "글 앞쪽에 있어요" if front else
                         "맨 뒤에만 있어요 — 공정위 지침은 글 앞쪽(제목 아래)이에요"})
    if f["video"]:
        rows.append({"item": "동영상", "ok": None, "detail": "있어요"})
    return rows


def report(camp, f, rows):
    """업체에 보낼 결과 보고 글(복사용)."""
    camp = camp or {}
    head = "[%s%s] 포스팅 완료 보고" % (camp.get("brand", ""), " · " + camp["title"] if camp.get("title") else "")
    lines = [head, "글 주소: " + f["url"]]
    for r in rows:
        if r["item"] == "글 읽기":
            continue
        mark = "✓" if r["ok"] else ("✗" if r["ok"] is False else "·")
        lines.append("%s %s — %s" % (mark, r["item"], r["detail"]))
    return "\n".join(lines)
