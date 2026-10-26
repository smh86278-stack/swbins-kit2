# -*- coding: utf-8 -*-
"""참고 글 — 사용자가 붙여 넣은 주소(비슷한 블로그·인스타 글)를 읽어 본문 글자만 뽑는다.

- 글마다 refs.txt(주소 한 줄에 하나, 앞 MAX_REFS 개)와 읽은 결과 refs.json(주소별 캐시)을 둔다.
- 네이버 블로그는 본문이 iframe 안에 있어 모바일 주소(m.blog.naver.com/아이디/글번호)로 바꿔 읽는다.
- 인스타는 로그인 벽이라 og:description(캡션 앞부분)만 잡히는 일이 많다.
- 프롬프트엔 "구성만 참고, 문장은 옮기지 않는다"로 넣는다(gen.refs_block) — 유사 문서로 걸리지 않게.
"""
import html
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

MAX_REFS = 3
MAX_CHARS = 3000           # 한 글에 앞 3000자까지
MAX_BYTES = 3 * 1024 * 1024
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
LOCK = threading.Lock()    # 플랫폼마다 같은 글을 동시에 만들 때 한 번만 읽게
URL_RE = re.compile(r"https?://[^\s<>\"']+")


def parse_urls(text):
    out = []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(").,]")
        if u not in out:
            out.append(u)
    return out[:MAX_REFS]


def naver_blog(url):
    """네이버 블로그 글 주소 → 본문이 바로 있는 모바일 주소(아니면 None)."""
    p = urllib.parse.urlparse(url)
    if not p.netloc.endswith("blog.naver.com"):
        return None
    q = urllib.parse.parse_qs(p.query)
    if q.get("blogId") and q.get("logNo"):
        bid, no = q["blogId"][0], q["logNo"][0]
    else:
        m = re.match(r"^/([\w-]+)/(\d+)", p.path)
        if not m:
            return None
        bid, no = m.groups()
    return "https://m.blog.naver.com/%s/%s" % (bid, no)


def fetch(url, timeout=10):
    """→ (최종 주소, html 문자열)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(MAX_BYTES)
        cs = r.headers.get_content_charset() or "utf-8"
        return r.geturl(), raw.decode(cs, "replace")


def meta(page, prop):
    m = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']*)' % re.escape(prop), page, re.I) \
        or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']%s["\']' % re.escape(prop), page, re.I)
    return html.unescape(m.group(1)).strip() if m else ""


def page_text(page):
    """html → 본문 글자. 네이버 스마트에디터 본문(se-main-container)이 있으면 그 부분만."""
    i = page.find("se-main-container")
    if i >= 0:
        page = page[page.rfind("<", 0, i):]              # 그 태그 처음부터(속성 글자가 본문에 섞이지 않게)
    page = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)\b.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6])>", "\n", page)
    t = html.unescape(re.sub(r"<[^>]+>", " ", page))
    lines = [re.sub(r"[ \t ​]+", " ", l).strip() for l in t.splitlines()]
    return "\n".join(l for l in lines if l)


def read_one(url):
    """→ {url, title, text, error}."""
    try:
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("http(s) 주소만 읽어요")
        final, page = fetch(naver_blog(url) or url)
        nb = naver_blog(final)                           # naver.me 같은 짧은 주소가 블로그로 넘어간 경우
        if nb and not urllib.parse.urlparse(final).netloc.startswith("m."):
            final, page = fetch(nb)
        title = meta(page, "og:title") or html.unescape((re.search(r"(?is)<title>(.*?)</title>", page) or [None, ""])[1]).strip()
        text = page_text(page)
        desc = meta(page, "og:description")
        if len(text) < 200 and desc:                     # 인스타처럼 본문이 안 잡히면 설명이라도
            text = desc
        text = text[:MAX_CHARS]
        if len(text) < 30:
            if "instagram.com" in url:                   # 2026-10 확인: 공개 계정도 로그인 벽이라 본문·캡션이 안 온다
                raise ValueError("인스타 글은 로그인 때문에 못 읽어요 — 참고할 캡션을 복사해 메모에 붙여 넣어 주세요")
            raise ValueError("본문을 못 읽었어요(로그인이 필요한 글일 수 있어요)")
        return {"url": url, "title": title[:120], "text": text, "error": ""}
    except Exception as e:                               # 주소 하나가 틀려도 글 만들기는 이어 간다
        return {"url": url, "title": "", "text": "", "error": str(e)[:200]}


def load(post_dir, fresh=False):
    """글의 참고 주소를 읽어 [{url, title, text, error}] — refs.json 에 담아 두고 다시 쓴다(fresh 면 새로)."""
    urls = parse_urls(_read(os.path.join(post_dir, "refs.txt")))
    if not urls:
        return []
    cache_p = os.path.join(post_dir, "refs.json")
    with LOCK:
        try:
            with open(cache_p, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            cache = {}
        out = []
        for u in urls:
            r = cache.get(u)
            if fresh or not r or r.get("error"):
                r = dict(read_one(u), ts=int(time.time()))
                cache[u] = r
            out.append(r)
        with open(cache_p, "w", encoding="utf-8") as f:
            json.dump({u: cache[u] for u in urls}, f, ensure_ascii=False, indent=1)
    return out


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""
