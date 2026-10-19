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
            if not (turned or big):
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


def build_prompt(platform, memo, title, photos, voice_texts, voice_note):
    """플랫폼 하나에 쓸 글을 요청하는 프롬프트."""
    head = [read_prompt("base.md"), read_prompt(platform["prompt"]),
            "분량: %s · 해시태그: %s" % (platform.get("length", ""),
                                       "%d개 안팎" % platform["hashtags"] if platform.get("hashtags") else "쓰지 않음")]
    vb = voice_block(voice_texts, voice_note)
    if vb:
        head.append(vb)
    mat = ["## 재료", "메모:\n" + (memo.strip() or "(메모 없음 — 사진만 보고 쓴다)")]
    if title.strip():
        mat.append("제목 후보(그대로 쓰거나 다듬어도 된다): " + title.strip())
    if photos:
        shown = photos[:MAX_PHOTOS]
        mat.append("사진 %d장 — 아래 순서대로 Read 로 열어 보고 쓴다:\n%s" % (len(shown), "\n".join("%d. ./photos/%s" % (i, n) for i, n in enumerate(shown, 1))))
        if len(photos) > MAX_PHOTOS:
            mat.append("(사진이 %d장 더 있지만 보지 않는다.)" % (len(photos) - MAX_PHOTOS))
    else:
        mat.append("사진 없음.")
    head.append("\n\n".join(mat))
    head.append("이제 %s 글을 쓴다. 글 본문만 출력한다." % platform["name"])
    return "\n\n".join(head)


def build_refine_prompt(platform, instruction, current, standalone=False, voice_texts=(), voice_note=""):
    """다듬기. standalone 이면 앞 대화(세션)가 없을 때 — 공통 규칙과 말투를 다시 붙인다."""
    parts = []
    if standalone:
        parts += [read_prompt("base.md"), read_prompt(platform["prompt"])]
        vb = voice_block(list(voice_texts), voice_note)
        if vb:
            parts.append(vb)
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


def run(prompt, workdir, resume_id=None, timeout=300):
    """claude -p 한 번. 프롬프트는 stdin 으로(명령줄 길이·한글 깨짐 피함)."""
    claude = find_claude()
    if not claude:
        return {"text": "", "session_id": "", "error": NO_CLAUDE}
    args = claude + ["-p", "--output-format", "json", "--permission-mode", "dontAsk",
                     "--allowedTools", "Read", "--disallowedTools"] + DENY
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
