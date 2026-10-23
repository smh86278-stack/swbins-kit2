# -*- coding: utf-8 -*-
"""글 만들기 — 프롬프트 조립 · claude -p 호출 · 결과 읽기. 화면(app.py)과 무관해서 테스트는 여기만 한다.

claude 에는 Read 만 허용한다(사진 보기용). 글 폴더를 작업 폴더로 띄우니 사진은 ./photos/ 에 있다.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

IS_WIN = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000
RES = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))     # platforms.json·prompts 가 있는 곳(exe 면 풀린 임시 폴더)

MAX_PHOTOS = 10            # 사진은 앞 10장만 보게 한다
VOICE_COUNT = 5            # 말투 예시는 최근 5편
VOICE_CHARS = 1500         # 한 편에 앞 1500자까지
PHOTO_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")
DENY = ["Bash", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch", "Task", "Agent"]
NO_CLAUDE = "claude 를 찾지 못했습니다 — Claude Code 를 설치하고 터미널에서 claude 를 한 번 실행해 로그인하세요."


def load_platforms():
    with open(os.path.join(RES, "platforms.json"), encoding="utf-8") as f:
        return [p for p in json.load(f) if p.get("enabled", True)]


def read_prompt(name):
    with open(os.path.join(RES, "prompts", name), encoding="utf-8") as f:
        return f.read().strip()


def find_claude():
    """claude 실행 명령(목록). 없으면 None."""
    path = shutil.which("claude")
    if not path:
        home = os.path.expanduser("~")
        for c in (os.path.join(home, ".local", "bin", "claude.exe" if IS_WIN else "claude"),
                  os.path.join(home, ".claude", "local", "claude")):
            if os.path.isfile(c):
                path = c
                break
    return [path] if path else None


def photo_names(post_dir):
    """글 폴더 photos\\ 안 사진 이름 — order.json(화면에서 끌어 바꾼 순서)대로, 거기 없는 건 뒤에 이름순."""
    d = os.path.join(post_dir, "photos")
    if not os.path.isdir(d):
        return []
    have = sorted(n for n in os.listdir(d) if n.lower().endswith(PHOTO_EXT))
    try:
        with open(os.path.join(post_dir, "order.json"), encoding="utf-8") as f:
            order = [n for n in json.load(f) if n in have]
    except (OSError, ValueError, TypeError):
        order = []
    order = list(dict.fromkeys(order))
    return order + [n for n in have if n not in order]


MAX_SIDE = 1600            # 사진 긴 변을 이만큼으로 줄인다(폰 원본 그대로면 느리다)
WEEK = "월화수목금토일"


def process_photo(path, max_side=MAX_SIDE):
    """넣은 사진 손질 — 찍은 날짜(EXIF)를 읽고, 돌아간 사진은 바로 세우고, 크면 줄인다.
    다시 저장하면 EXIF(위치 정보 포함)는 빠진다. 찍은 날짜 'YYYY-MM-DD' 를 돌려준다(없으면 '')."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return ""
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            raw = ""
            try:
                raw = exif.get_ifd(0x8769).get(36867) or ""      # DateTimeOriginal
            except Exception:
                pass
            raw = str(raw or exif.get(306) or "")                # DateTime
            m = re.match(r"(\d{4})[:\-](\d{2})[:\-](\d{2})", raw)
            date = "%s-%s-%s" % m.groups() if m else ""
            fmt = im.format
            if fmt == "GIF":                                     # 움직이는 그림은 그대로
                return date
            turned = exif.get(274, 1) not in (1, None)           # Orientation
            big = max(im.size) > max_side or os.path.getsize(path) > 2 * 1024 * 1024
            gps = 34853 in exif                                  # 위치 정보 — 집 주소가 새지 않게 작은 사진도 다시 저장
            if not (turned or big or gps):
                return date
            out = ImageOps.exif_transpose(im)
            out.thumbnail((max_side, max_side), Image.LANCZOS)
            if fmt == "JPEG":
                out.convert("RGB").save(path + ".tmp", "JPEG", quality=85, optimize=True)
            else:
                out.save(path + ".tmp", fmt, optimize=True)
        os.replace(path + ".tmp", path)
        return date
    except Exception:
        try:
            os.remove(path + ".tmp")
        except OSError:
            pass
        return ""


def date_text(ymd):
    """'2026-10-18' → '2026년 10월 18일 (일)'."""
    try:
        d = datetime.strptime(ymd, "%Y-%m-%d")
    except ValueError:
        return ""
    return "%d년 %d월 %d일 (%s)" % (d.year, d.month, d.day, WEEK[d.weekday()])


def baby_age(birthday, on):
    """생일·기준일('YYYY-MM-DD') → '생후 5개월 (163일)'. 생후 N일은 태어난 날을 1일로 센다."""
    try:
        b = datetime.strptime(birthday, "%Y-%m-%d")
        d = datetime.strptime(on, "%Y-%m-%d")
    except (TypeError, ValueError):
        return ""
    if d < b:
        return ""
    months = (d.year - b.year) * 12 + d.month - b.month - (1 if d.day < b.day else 0)
    return "생후 %d개월 (%d일)" % (months, (d - b).days + 1)


def kids_block(kids):
    """아이 정보 보호 규칙 — 설정에 애칭이 있으면."""
    names = [n.strip() for n in re.split(r"[,·/]", (kids or {}).get("names", "")) if n.strip()]
    if not names:
        return ""
    return ("## 아이 정보 보호\n"
            "아이는 반드시 애칭 %s 로만 부른다(쌍둥이면 첫째·둘째 순서). "
            "메모에 실명·정확한 생년월일·병원·어린이집·사는 동네처럼 아이를 특정할 수 있는 정보가 있어도 글에는 쓰지 않는다. "
            "개월 수는 써도 된다." % "·".join(names))


def load_templates():
    try:
        with open(os.path.join(RES, "templates.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_photo_order(post_dir, names):
    with open(os.path.join(post_dir, "order.json"), "w", encoding="utf-8") as f:
        json.dump([str(n) for n in names], f, ensure_ascii=False)


def load_voice(voice_dir):
    """말투 예시 — 최근에 넣은 것부터 VOICE_COUNT 편, 한 편에 VOICE_CHARS 자까지."""
    if not os.path.isdir(voice_dir):
        return []
    files = [os.path.join(voice_dir, n) for n in os.listdir(voice_dir) if n.endswith(".txt")]
    files.sort(key=os.path.getmtime, reverse=True)
    out = []
    for p in files[:VOICE_COUNT]:
        with open(p, encoding="utf-8") as f:
            t = f.read().strip()
        if t:
            out.append(t[:VOICE_CHARS])
    return out


def voice_block(voice_texts, voice_note):
    parts = []
    if voice_note.strip() or voice_texts:
        parts.append("## 글쓴이 말투\n\n아래는 글쓴이가 직접 쓴 글이다. 내용은 가져오지 말고 **말투·문장 길이·끝맺음·이모지 습관·줄바꿈**만 따라 한다.")
    if voice_note.strip():
        parts.append("글쓴이가 적은 말투 메모: " + voice_note.strip())
    for i, t in enumerate(voice_texts, 1):
        parts.append("<예시 %d>\n%s\n</예시 %d>" % (i, t, i))
    return "\n\n".join(parts)


def parse_tags(s):
    """'#동네 맛집, #닉네임' → ['#동네', '#맛집', '#닉네임'] (# 없으면 붙이고, 겹치면 하나만)."""
    out = []
    for w in re.split(r"[\s,]+", s or ""):
        w = w.strip().lstrip("#")
        if w and "#" + w not in out:
            out.append("#" + w)
    return out


def ensure_tags(text, tags):
    """늘 붙이는 해시태그 중 빠진 걸 해시태그 줄 끝에 붙인다(틱톡은 [자막 대본] 앞, 캡션 끝에)."""
    missing = [t for t in tags if t.lower() not in text.lower()]
    if not missing or not text.strip():
        return text

    def add(s):
        lines = s.rstrip().split("\n")
        if re.search(r"#[^\s#]+\s*$", lines[-1]):         # 마지막 줄이 태그로 끝나면 거기에 잇는다
            lines[-1] = lines[-1].rstrip() + " " + " ".join(missing)
        else:
            lines += ["", " ".join(missing)]
        return "\n".join(lines)

    if "[자막 대본]" in text:
        head, sep, tail = text.partition("[자막 대본]")
        return add(head) + "\n\n" + sep + tail
    return add(text)


KINDS = {"experience": "체험단", "sponsor": "협찬", "groupbuy": "공구"}


def josa(word, pair):
    """받침 보고 조사 고르기 — pair 는 ('으로', '로') · ('을', '를') 처럼 (받침 있을 때, 없을 때)."""
    ch = (word or "").strip()[-1:]
    if not ("가" <= ch <= "힣"):
        return pair[1]
    jong = (ord(ch) - 0xAC00) % 28
    if pair[0] == "으로" and jong == 8:          # ㄹ 받침은 '로'
        return pair[1]
    return pair[0] if jong else pair[1]


def disclosure(campaign):
    """협찬·공구 표기 한 줄 — 캠페인에 업체가 있으면(공정위 추천·보증 심사지침: 경제적 이해관계는 앞쪽에)."""
    brand = (campaign or {}).get("brand", "").strip()
    if not brand:
        return ""
    if campaign.get("kind") == "groupbuy":
        return "이 글은 %s 공동구매 진행 글로, 판매에 따른 수수료를 받습니다." % brand
    got = (campaign.get("provided") or "").strip() or "제품"
    return "이 글은 %s%s부터 %s%s 제공받아 솔직하게 작성했습니다." % (brand, josa(brand, ("으로", "로")), got, josa(got, ("을", "를")))


def ensure_disclosure(text, line, has_title):
    """협찬 표기가 앞쪽에 없으면 넣는다 — 제목 있는 플랫폼은 제목 다음, 아니면 맨 앞."""
    if not line or not text.strip():
        return text
    lines = text.strip().split("\n")
    head = "\n".join(lines[:4])
    if "제공받" in head or "협찬" in head or "광고" in head:
        return text
    if has_title and len(lines) > 1:
        return "\n".join([lines[0], "", line] + lines[1:])
    return line + "\n\n" + text.strip()


def campaign_tags(campaign, platform):
    return parse_tags((campaign or {}).get("tags", "")) if platform.get("hashtags") else []


def campaign_block(campaign, platform):
    """체험단·협찬 조건을 프롬프트로."""
    if not campaign:
        return ""
    c = campaign
    kind = KINDS.get(c.get("kind"), "협찬")
    parts = ["## %s 조건 (꼭 지킨다)" % kind, "%s 글이다. 업체: %s" % (kind, c.get("brand") or "[확인: 업체]")]
    if c.get("provided"):
        parts.append("제공받은 것: " + c["provided"])
    if c.get("kind") == "groupbuy":
        gb = ["공동구매 안내도 함께 쓴다 — 아래 숫자·날짜는 한 글자도 바꾸지 않는다."]
        if c.get("start") or c.get("deadline"):
            gb.append("공구 기간: %s ~ %s" % (date_text(c.get("start", "")) or "[확인: 시작일]", date_text(c.get("deadline", "")) or "[확인: 마감일]"))
        if c.get("price") or c.get("sale_price"):
            gb.append("가격: 정가 %s → 공구가 %s" % (c.get("price") or "[확인: 정가]", c.get("sale_price") or "[확인: 공구가]"))
        gb.append("직접 써 본 경험이 먼저고, 공구 안내(기간·가격·구매 링크)는 글 뒤쪽에 짧게 모은다. '마감 임박', '역대급' 같은 재촉 표현은 쓰지 않는다.")
        parts.append("\n".join(gb))
    line = disclosure(c)
    if line:
        parts.append("협찬 표기: %s첫 부분에 이 문장을 그대로 넣는다 — \"%s\"" % ("제목 다음 " if platform.get("title") else "", line))
    for k in c.get("keywords") or []:
        if (k.get("word") or "").strip():
            parts.append("필수 키워드: \"%s\" 를 본문에 %d번 이상, 문장 속에 자연스럽게(나열하지 말 것)" % (k["word"].strip(), int(k.get("min") or 1)))
    tags = campaign_tags(c, platform)
    if tags:
        parts.append("필수 해시태그(그대로): " + " ".join(tags))
    links = [u for u in c.get("links") or [] if (u or "").strip()]
    if links:
        parts.append("필수 링크: 글 끝 해시태그 앞에 아래 주소를 한 줄씩 그대로 넣는다\n" + "\n".join(links))
    if (c.get("notes") or "").strip():
        parts.append("업체 요구사항:\n" + c["notes"].strip())
    parts.append("조건 때문에 광고처럼 들뜨지 않게 한다. 좋은 점·아쉬운 점은 여전히 메모에 있는 대로만 쓴다.")
    return "\n".join(parts)


def apply_campaign(text, campaign, platform):
    """AI 가 빠뜨려도 꼭 들어가야 하는 것 — 협찬 표기·필수 태그."""
    if not campaign:
        return text
    text = ensure_disclosure(text, disclosure(campaign), platform.get("title"))
    return ensure_tags(text, campaign_tags(campaign, platform))


def build_prompt(platform, memo, title, photos, voice_texts, voice_note, fixed_tags=(), campaign=None, kids=None,
                 photo_mode="Read"):
    """플랫폼 하나에 쓸 글을 요청하는 프롬프트.
    photo_mode — 사진 보는 법(ai.photo_mode): 'Read'·'read_file' 은 그 도구로 ./photos/ 를 열고,
    'attached' 는 사진이 붙어 온다, 'none' 은 못 본다(사진 내용을 지어내지 않게)."""
    tags = "%d개 안팎" % platform["hashtags"] if platform.get("hashtags") else "쓰지 않음"
    if platform.get("hashtags") and fixed_tags:
        tags += " — 이 태그는 꼭 그대로 넣는다(개수에 포함): " + " ".join(fixed_tags)
    head = [read_prompt("base.md"), read_prompt(platform["prompt"]),
            "분량: %s · 해시태그: %s" % (platform.get("length", ""), tags)]
    cb = campaign_block(campaign, platform)
    if cb:
        head.append(cb)
    kb = kids_block(kids)
    if kb:
        head.append(kb)
    vb = voice_block(voice_texts, voice_note)
    if vb:
        head.append(vb)
    mat = ["## 재료", "메모:\n" + (memo.strip() or ("(메모 없음)" if photo_mode == "none" else "(메모 없음 — 사진만 보고 쓴다)"))]
    if title.strip():
        mat.append("제목 후보(그대로 쓰거나 다듬어도 된다): " + title.strip())
    if photos:
        shown = photos[:MAX_PHOTOS]
        names = "\n".join("%d. ./photos/%s" % (i, n) for i, n in enumerate(shown, 1))
        if photo_mode == "none":
            mat.append("사진 %d장이 있지만 이번엔 볼 수 없다. 사진 속 내용(음식 모양·색·장소 모습 등)을 지어내지 말고 메모에 있는 것만 쓴다. "
                       "사진이 들어갈 자리는 [사진 1] 처럼 번호만 표시한다." % len(shown))
        elif photo_mode == "attached":
            mat.append("사진 %d장이 이 요청에 붙어 있다 — 아래 순서대로 보고 쓴다:\n%s" % (len(shown), names))
        else:
            mat.append("사진 %d장 — 아래 순서대로 %s 로 열어 보고 쓴다:\n%s" % (len(shown), photo_mode, names))
        if len(photos) > MAX_PHOTOS:
            mat.append("(사진이 %d장 더 있지만 보지 않는다.)" % (len(photos) - MAX_PHOTOS))
    else:
        mat.append("사진 없음.")
    head.append("\n\n".join(mat))
    head.append("이제 %s 글을 쓴다. 글 본문만 출력한다." % platform["name"])
    return "\n\n".join(head)


def build_refine_prompt(platform, instruction, current, standalone=False, voice_texts=(), voice_note="", campaign=None, kids=None):
    """다듬기. standalone 이면 앞 대화(세션)가 없을 때 — 공통 규칙과 말투를 다시 붙인다."""
    parts = []
    if standalone:
        parts += [read_prompt("base.md"), read_prompt(platform["prompt"])]
        vb = voice_block(list(voice_texts), voice_note)
        if vb:
            parts.append(vb)
    cb = campaign_block(campaign, platform)
    if cb:
        parts.append(cb + "\n(다듬어도 이 조건은 그대로 지킨다)")
    kb = kids_block(kids)
    if kb:
        parts.append(kb)
    parts.append("아래는 지금 %s 글이다(글쓴이가 직접 고쳤을 수 있으니 이 글을 기준으로 한다).\n\n<지금 글>\n%s\n</지금 글>" % (platform["name"], current.strip()))
    parts.append("요청: " + instruction.strip())
    parts.append("요청한 부분만 바꾸고 나머지 규칙은 그대로 지킨다. 고친 글 본문 전체만 출력한다.")
    return "\n\n".join(parts)


def parse_result(stdout):
    """claude -p --output-format json 의 결과(한 덩어리 JSON, 아니면 마지막 JSON 줄) → {text, session_id, error}."""
    text = (stdout or "").strip()
    for cand in [text] + list(reversed(text.splitlines())):
        try:
            d = json.loads(cand)
        except ValueError:
            continue
        if isinstance(d, dict) and ("result" in d or "is_error" in d):
            body = clean_text(d.get("result") or "")
            err = ""
            if d.get("is_error") or d.get("subtype", "success") != "success":
                err = body or d.get("subtype") or "claude 오류"
                body = ""
            return {"text": body, "session_id": d.get("session_id") or "", "error": err}
    return {"text": "", "session_id": "", "error": "claude 결과를 읽지 못했습니다: " + (text[-300:] or "(빈 출력)")}


def clean_text(s):
    """앞뒤 공백·통째로 감싼 코드블록을 벗긴다."""
    s = s.strip()
    m = re.match(r"^```[^\n]*\n(.*)\n```$", s, re.S)
    return (m.group(1) if m else s).strip()


def run(prompt, workdir, resume_id=None, timeout=300, model=""):
    """claude -p 한 번. 프롬프트는 stdin 으로(명령줄 길이·한글 깨짐 피함). 다른 AI 는 ai.run 이 고른다."""
    claude = find_claude()
    if not claude:
        return {"text": "", "session_id": "", "error": NO_CLAUDE}
    args = claude + ["-p", "--output-format", "json", "--permission-mode", "dontAsk",
                     "--allowedTools", "Read", "--disallowedTools"] + DENY
    if model:
        args += ["--model", model]
    if resume_id:
        args += ["--resume", resume_id]
    kw = {"creationflags": CREATE_NO_WINDOW} if IS_WIN else {}
    try:
        p = subprocess.run(args, input=prompt.encode("utf-8"), cwd=workdir, capture_output=True,
                           timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        return {"text": "", "session_id": "", "error": "시간이 너무 오래 걸려 멈췄습니다(%d초)." % timeout}
    except OSError as e:
        return {"text": "", "session_id": "", "error": "claude 를 띄우지 못했습니다: %s" % e}
    r = parse_result(p.stdout.decode("utf-8", "replace"))
    if r["error"] and not r["session_id"]:
        err = p.stderr.decode("utf-8", "replace").strip()
        if err:
            r["error"] += "\n" + err[-500:]
    return r


def safe_slug(s, n=12):
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", (s or "").strip().splitlines()[0] if (s or "").strip() else "")
    s = s.strip("-")
    cut = s[:n]
    if len(s) > n and s[n] != "-" and "-" in cut:      # 단어 중간에서 자르지 않는다(6500원 → 6)
        cut = cut.rsplit("-", 1)[0]
    return cut.strip("-") or "글"


def new_post_dir(root, memo, now=None):
    """posts\\YYYYMMDD-<메모 앞 12자>, 겹치면 -2, -3 …"""
    base = "%s-%s" % ((now or datetime.now()).strftime("%Y%m%d"), safe_slug(memo))
    path, i = os.path.join(root, base), 2
    while os.path.exists(path):
        path, i = os.path.join(root, "%s-%d" % (base, i)), i + 1
    os.makedirs(os.path.join(path, "photos"))
    return path


def inside(root, path):
    """path 가 root 안(또는 root 자체가 아닌 그 아래)인지."""
    try:
        r, p = os.path.realpath(root), os.path.realpath(path)
        return p != r and os.path.commonpath([r, p]) == r
    except ValueError:      # 드라이브가 다르면
        return False
