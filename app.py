# -*- coding: utf-8 -*-
"""글 도우미(PostKit) — 사진·메모를 넣으면 플랫폼별 글을 내 말투로 써 주는 앱.

    python app.py      (exe 는 build.py)

- 화면은 127.0.0.1 에만 연다. 상태를 바꾸는 POST 는 띄울 때마다 새로 만드는 토큰(X-Token)이 있어야 한다.
  「폰에서 쓰기」를 켰을 때만 집 네트워크 주소에 따로 연다(PIN → 세션 쿠키, PC 를 건드리는 길은 막음 — PhoneHandler).
- 창은 Edge --app(따로 둔 프로필). 창이 닫혀 신호(/api/ping)가 끊기면 서버도 스스로 끝난다.
- 데이터는 %APPDATA%\\PostKit (config.json · voice\\*.txt · posts\\<글>\\ · campaigns.json · ledger.json).
  설정에서 OneDrive 같은 곳으로 옮길 수 있고(store.py), 하루 한 번 사진 빼고 %LOCALAPPDATA%\\PostKit\\backups 에 자동 백업.
- 올리기는 사람이 한다 — 여기선 복사와 글쓰기 창 열기까지만.
"""
import http.server
import json
import os
import re
import secrets
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from datetime import datetime

import ai
import gen
import store

APP = "PostKit"
PORT = 8650
IS_WIN = sys.platform == "win32"
HERE = os.path.dirname(os.path.abspath(__file__))
# 기본 데이터 자리 — 데이터 폴더를 옮기면 여기 location.json 에 새 자리를 적는다. 시험할 땐 POSTKIT_DATA 로 따로
HOME = os.environ.get("POSTKIT_DATA") or os.path.join(os.environ.get("APPDATA") or HERE, APP)
LOCALDATA = os.path.join(os.environ.get("LOCALAPPDATA") or HERE, APP)
BACKUPS = os.path.join(HOME, "_backups") if os.environ.get("POSTKIT_DATA") else os.path.join(LOCALDATA, "backups")


def set_data(path):
    """데이터 폴더를 정한다(옮길 때도 이걸로)."""
    global DATA, POSTS, VOICE, CFG, ITEMS
    DATA = path
    POSTS = os.path.join(DATA, "posts")
    VOICE = os.path.join(DATA, "voice")
    CFG = os.path.join(DATA, "config.json")
    ITEMS = {"campaigns": os.path.join(DATA, "campaigns.json"),     # 체험단·협찬·공구
             "ledger": os.path.join(DATA, "ledger.json")}           # 장부


set_data(store.load_location(HOME) or HOME)
TOKEN = secrets.token_urlsafe(24)
FROZEN = bool(getattr(sys, "frozen", False))      # PostKit.exe 로 돌고 있나
NAME_RE = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,120}$")

JOBS = {}                      # job id → {platform id: {status, text, error}}
LOCK = threading.Lock()
LAST_PING = [0.0]              # 창이 보내는 신호 — 끊기면 끝낸다
STARTED = time.time()


def log(*a):
    try:
        os.makedirs(LOCALDATA, exist_ok=True)
        with open(os.path.join(LOCALDATA, "app.log"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), " ".join(str(x) for x in a)))
    except OSError:
        pass


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def load_cfg():
    c = read_json(CFG, {})
    c.setdefault("voice_note", "")
    c.setdefault("default_platforms", ["naver_blog", "instagram"])
    c.setdefault("write_urls", {})
    return c


def platforms():
    cfg = load_cfg()
    out = []
    for p in gen.load_platforms():
        p = dict(p)
        if cfg["write_urls"].get(p["id"]):
            p["write_url"] = cfg["write_urls"][p["id"]]
        out.append(p)
    return out


def platform(pid):
    return next((p for p in platforms() if p["id"] == pid), None)


def post_path(name):
    """화면이 보낸 글 이름 → posts 아래 실제 폴더. 아니면 ValueError."""
    if not name or not NAME_RE.match(name):
        raise ValueError("글 이름이 올바르지 않습니다.")
    p = os.path.join(POSTS, name)
    if not gen.inside(POSTS, p) or not os.path.isdir(p):
        raise ValueError("글을 찾을 수 없습니다.")
    return p


def load_items(kind):
    items = read_json(ITEMS[kind], [])
    return items if isinstance(items, list) else []


def save_item(kind, item):
    """id 로 바꿔 끼우거나 새로 넣는다."""
    if not isinstance(item, dict):
        raise ValueError("내용이 올바르지 않습니다.")
    with LOCK:
        items = load_items(kind)
        if not item.get("id"):
            item["id"] = secrets.token_hex(5)
            item["created"] = datetime.now().isoformat(timespec="seconds")
            items.append(item)
        else:
            items = [item if x.get("id") == item["id"] else x for x in items]
            if not any(x.get("id") == item["id"] for x in items):
                items.append(item)
        os.makedirs(DATA, exist_ok=True)
        write_text(ITEMS[kind], json.dumps(items, ensure_ascii=False, indent=1))
    return item


def delete_item(kind, iid):
    with LOCK:
        items = [x for x in load_items(kind) if x.get("id") != iid]
        write_text(ITEMS[kind], json.dumps(items, ensure_ascii=False, indent=1))


def campaign_for(post_dir):
    """글에 이어진 캠페인(없으면 None)."""
    cid = read_text(os.path.join(post_dir, "campaign.txt")).strip()
    return next((c for c in load_items("campaigns") if c.get("id") == cid), None) if cid else None


def history(post_dir, pid):
    rows = []
    for line in read_text(os.path.join(post_dir, pid + ".history.jsonl")).splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def save_result(post_dir, pid, text, session_id, instruction, engine="claude"):
    write_text(os.path.join(post_dir, pid + ".md"), text)
    with open(os.path.join(post_dir, pid + ".history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "instruction": instruction,
                            "text": text, "session_id": session_id, "engine": engine}, ensure_ascii=False) + "\n")


def post_info(post_dir):
    name = os.path.basename(post_dir)
    texts = {}
    for p in platforms():
        t = read_text(os.path.join(post_dir, p["id"] + ".md"))
        if t:
            texts[p["id"]] = t
    return {"name": name, "memo": read_text(os.path.join(post_dir, "memo.txt")),
            "title": read_text(os.path.join(post_dir, "title.txt")),
            "campaign": read_text(os.path.join(post_dir, "campaign.txt")).strip(),
            "photos": gen.photo_names(post_dir), "texts": texts}


def list_posts():
    if not os.path.isdir(POSTS):
        return []
    out = []
    for n in sorted(os.listdir(POSTS), reverse=True):
        d = os.path.join(POSTS, n)
        if not os.path.isdir(d):
            continue
        memo = read_text(os.path.join(d, "memo.txt")).strip()
        out.append({"name": n, "memo": memo.splitlines()[0][:60] if memo else "",
                    "campaign": read_text(os.path.join(d, "campaign.txt")).strip(),
                    "platforms": [p["id"] for p in platforms() if os.path.isfile(os.path.join(d, p["id"] + ".md"))],
                    "photos": len(gen.photo_names(d))})
    return out


# ---------- 글 만들기 · 다듬기 ----------

def fixed_tags(plat, cfg):
    """늘 붙이는 해시태그 — 해시태그를 쓰는 플랫폼에만."""
    return gen.parse_tags(cfg.get("fixed_tags", "")) if plat.get("hashtags") else []


def gen_one(job, post_dir, plat, cfg, s, mode, note):
    memo = read_text(os.path.join(post_dir, "memo.txt"))
    title = read_text(os.path.join(post_dir, "title.txt"))
    tags = fixed_tags(plat, cfg)
    camp = campaign_for(post_dir)
    photos = gen.photo_names(post_dir)
    prompt = gen.build_prompt(plat, memo, title, photos, gen.load_voice(VOICE), cfg["voice_note"], tags, camp, cfg.get("kids"),
                              photo_mode=mode)
    r = ai.run(s, prompt, post_dir, photos=photos if mode == "attached" else ())
    if r["text"]:
        r["text"] = gen.apply_campaign(gen.ensure_tags(r["text"], tags), camp, plat)
        save_result(post_dir, plat["id"], r["text"], r["session_id"], "", s["engine"])
    with LOCK:
        JOBS[job][plat["id"]] = {"status": "done" if r["text"] else "error", "text": r["text"], "error": r["error"],
                                 "note": note if r["text"] else ""}
    log("gen", os.path.basename(post_dir), plat["id"], "ok" if r["text"] else "error: " + r["error"][:200])


def photo_plan(post_dir, s):
    """고른 AI 가 사진을 못 보면 — 메모가 있으면 메모만으로 쓰고 알려 주고, 사진뿐이면 막는다. (사진 보는 법, 알릴 말)"""
    mode = ai.photo_mode(s)
    if mode != "none" or not gen.photo_names(post_dir):
        return mode, ""
    if not read_text(os.path.join(post_dir, "memo.txt")).strip():
        raise ValueError("지금 고른 AI(%s · %s)는 사진을 못 봐요 — 메모를 적어 주거나, ⚙️ 설정에서 사진을 보는 AI·비전 모델을 골라 주세요."
                         % (ai.NAMES[s["engine"]], ai.model_of(s)))
    return mode, "%s 모델은 사진을 못 봐서 메모만으로 썼어요." % ai.model_of(s)


def start_gen(post_dir, pids):
    cfg = load_cfg()
    s = ai.settings(cfg)
    why = ai.not_ready(s)
    if why:
        raise ValueError(why)
    plats = [p for p in (platform(x) for x in pids) if p]
    if not plats:
        raise ValueError("플랫폼을 하나 이상 고르세요.")
    mode, note = photo_plan(post_dir, s)
    job = secrets.token_hex(6)
    with LOCK:
        JOBS[job] = {p["id"]: {"status": "running", "text": "", "error": ""} for p in plats}
    for p in plats:
        threading.Thread(target=gen_one, args=(job, post_dir, p, cfg, s, mode, note), daemon=True).start()
    return job


def refine(post_dir, plat, instruction, current):
    cfg = load_cfg()
    s = ai.settings(cfg)
    why = ai.not_ready(s)
    if why:
        raise ValueError(why)
    rows = history(post_dir, plat["id"])
    sid = ""
    if s["engine"] == "claude":     # 세션 이어받기는 claude 만(다른 AI 로 쓴 글이면 새로)
        sid = next((r.get("session_id") for r in reversed(rows) if r.get("session_id")
                    and r.get("engine", "claude") == "claude"), "")
    camp = campaign_for(post_dir)
    r = {"text": "", "error": "", "session_id": ""}
    if sid:
        r = ai.run(s, gen.build_refine_prompt(plat, instruction, current, campaign=camp, kids=cfg.get("kids")), post_dir, resume_id=sid, timeout=180)
    if not r["text"]:      # 세션이 없거나 이어받기에 실패하면 규칙·말투를 다시 붙여 새로
        r = ai.run(s, gen.build_refine_prompt(plat, instruction, current, standalone=True,
                                              voice_texts=gen.load_voice(VOICE), voice_note=cfg["voice_note"], campaign=camp,
                                              kids=cfg.get("kids")),
                   post_dir, timeout=180)
    if r["text"]:
        r["text"] = gen.apply_campaign(gen.ensure_tags(r["text"], fixed_tags(plat, cfg)), camp, plat)
        save_result(post_dir, plat["id"], r["text"], r["session_id"], instruction, s["engine"])
    log("refine", os.path.basename(post_dir), plat["id"], "ok" if r["text"] else "error: " + r["error"][:200])
    return r


# ---------- 열기 ----------

def open_folder(path):
    if IS_WIN:
        os.startfile(path)  # noqa: S606 — 내 데이터 폴더만 연다
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


def make_shortcuts():
    """시작 메뉴·바탕 화면에 '글 도우미' 바로가기(지금 exe 를 가리킨다). 만든 곳 목록, 실패면 []."""
    if not IS_WIN:
        return []
    exe = sys.executable
    ps = ("$s = New-Object -ComObject WScript.Shell; $made = @(); "
          "foreach ($dir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) { "
          "  $l = $s.CreateShortcut((Join-Path $dir '글 도우미.lnk')); $l.TargetPath = $env:PK_EXE; "
          "  $l.WorkingDirectory = Split-Path $env:PK_EXE; $l.IconLocation = $env:PK_EXE + ',0'; "
          "  $l.Description = '사진·메모로 블로그·인스타 글 쓰기'; $l.Save(); $made += $dir }; $made -join '|'")
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           capture_output=True, timeout=30, env=dict(os.environ, PK_EXE=exe),
                           creationflags=gen.CREATE_NO_WINDOW)
        out = p.stdout.decode("utf-8", "replace").strip()
        if p.returncode != 0 or not out:
            log("바로가기 실패", p.stderr.decode("utf-8", "replace")[-300:])
            return []
        log("바로가기", out)
        return out.split("|")
    except (OSError, subprocess.TimeoutExpired) as e:
        log("바로가기 실패", e)
        return []


def first_run_shortcuts():
    """exe 를 처음 켰을 때 한 번 바로가기를 만들어 둔다(지우면 다시 만들지 않는다 — 설정에서 다시 만들기)."""
    cfg = load_cfg()
    if not FROZEN or cfg.get("shortcuts_made"):
        return
    if make_shortcuts():
        cfg["shortcuts_made"] = True
        os.makedirs(DATA, exist_ok=True)
        write_text(CFG, json.dumps(cfg, ensure_ascii=False, indent=2))


# ---------- 데이터 폴더 · 백업 · 성장 기록 ----------

def busy():
    with LOCK:
        return any(v["status"] == "running" for j in JOBS.values() for v in j.values())


def data_status():
    return {"dir": DATA, "default": HOME, "is_default": os.path.normcase(DATA) == os.path.normcase(HOME),
            "clouds": store.cloud_folders(), "company_onedrive": store.company_onedrive(), "backups": BACKUPS}


def daily_backup():
    try:
        made = store.auto_backup(DATA, BACKUPS)
        if made:
            log("자동 백업", made)
    except OSError as e:
        log("자동 백업 실패", e)


def pick_folder():
    """윈도우 폴더 고르기 창(PC 화면에 뜬다). 고른 경로, 취소면 ''."""
    if not IS_WIN:
        return ""
    ps = ("Add-Type -AssemblyName System.Windows.Forms; [Console]::OutputEncoding = [Text.Encoding]::UTF8; "
          "$o = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}; "
          "$d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = '글 도우미 데이터를 둘 폴더를 고르세요 (OneDrive·구글 드라이브 폴더 추천)'; "
          "$d.ShowNewFolderButton = $true; if ($d.ShowDialog($o) -eq 'OK') { $d.SelectedPath }")
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           capture_output=True, timeout=600, creationflags=gen.CREATE_NO_WINDOW)
        return p.stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def move_data(picked):
    """데이터 폴더를 picked 로. 거기 데이터가 이미 있으면 그걸 쓰고(다른 PC 와 함께), 없으면 지금 데이터를 복사한다.
    원래 자리의 데이터는 지우지 않는다."""
    if busy():
        raise ValueError("글을 만드는 중이에요. 끝난 뒤에 옮겨 주세요.")
    if not picked or not os.path.isdir(picked):
        raise ValueError("폴더를 찾을 수 없어요.")
    dst = store.target_dir(picked)
    if os.path.normcase(os.path.abspath(dst)) == os.path.normcase(os.path.abspath(DATA)):
        raise ValueError("지금 쓰고 있는 폴더예요.")
    if store.has_data(dst):
        used, n = True, 0
    else:
        used, n = False, store.copy_data(DATA, dst)
    old = DATA
    store.save_location(HOME, dst)
    set_data(dst)
    log("데이터 폴더 옮김", old, "→", dst, "기존 데이터 사용" if used else "%d개 복사" % n)
    return {"dir": dst, "used_existing": used, "copied": n, "old": old}


def growth():
    cfg = load_cfg()
    names = [n.strip() for n in re.split(r"[,·/]", (cfg.get("kids") or {}).get("names", "")) if n.strip()]
    rows = []
    if os.path.isdir(POSTS):
        for n in os.listdir(POSTS):
            d = os.path.join(POSTS, n)
            if os.path.isdir(d):
                e = store.growth_entry(n, read_text(os.path.join(d, "memo.txt")), gen.photo_names(d))
                if e:
                    rows.append(e)
    rows.sort(key=lambda e: (e["month"], e["name"]))
    return {"names": names[:2], "entries": rows}


def compose_growth(picked):
    """고른 성장 기록으로 새 글 — 모은 메모 + 기록마다 대표 사진 한 장(개월 순, 10장까지)."""
    g = growth()
    entries = [e for e in g["entries"] if e["name"] in set(picked or [])]
    if not entries:
        raise ValueError("모을 기록을 골라 주세요.")
    memo = store.compose_memo(entries, g["names"] or ["첫째", "둘째"])
    d = gen.new_post_dir(POSTS, "성장 기록 모음")
    write_text(os.path.join(d, "memo.txt"), memo)
    write_text(os.path.join(d, "title.txt"), "")
    write_text(os.path.join(d, "campaign.txt"), "")
    order = []
    for i, e in enumerate([e for e in entries if e["photo"]][:gen.MAX_PHOTOS], 1):
        src = os.path.join(POSTS, e["name"], "photos", e["photo"])
        name = "%02d-%s" % (i, e["photo"])
        try:
            shutil.copy2(src, os.path.join(d, "photos", name))
            order.append(name)
        except OSError:
            pass
    gen.save_photo_order(d, order)
    return os.path.basename(d)


def open_window(url):
    """Edge 앱 창(따로 둔 프로필). 없으면 기본 브라우저."""
    if IS_WIN:
        cands = [os.path.join(b, "Microsoft", "Edge", "Application", "msedge.exe")
                 for b in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")) if b]
        exe = next((c for c in cands if os.path.isfile(c)), None)
        if exe:
            subprocess.Popen([exe, "--app=" + url, "--user-data-dir=" + os.path.join(LOCALDATA, "edge"), "--window-size=1180,820"])
            return
    webbrowser.open(url)


# ---------- HTTP ----------

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = APP

    def log_message(self, *a):
        pass

    phone = False                  # 폰 서버(PhoneHandler)면 참

    def send(self, code, body, ctype="application/json; charset=utf-8", headers=()):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def host_ok(self):
        return self.headers.get("Host", "") in ("127.0.0.1:%d" % self.server.server_port, "localhost:%d" % self.server.server_port)

    def page_token(self):
        return TOKEN

    def post_ok(self):
        return self.host_ok() and self.headers.get("X-Token") == TOKEN

    def body_bytes(self, limit=30 * 1024 * 1024):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("파일이 너무 큽니다(30MB 까지).")
        return self.rfile.read(n) if n else b""

    def body_json(self):
        b = self.body_bytes(2 * 1024 * 1024)
        return json.loads(b.decode("utf-8")) if b else {}

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {"error": "host"})
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        try:
            if u.path == "/":
                html = read_text(os.path.join(gen.RES, "ui.html")).replace("__TOKEN__", self.page_token()) \
                    .replace("__PHONE__", "true" if self.phone else "false")
                return self.send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if u.path == "/api/phone":
                return self.send(200, phone_status())
            if u.path == "/api/phone/qr.svg":
                if not PHONE["srv"]:
                    return self.send(404, {"error": "폰에서 쓰기가 꺼져 있어요."})
                import qr
                return self.send(200, qr.svg(phone_url()).encode("utf-8"), "image/svg+xml")
            if u.path == "/icon.png":
                with open(os.path.join(gen.RES, "icon.png"), "rb") as f:
                    return self.send(200, f.read(), "image/png")
            if u.path == "/api/ping":
                LAST_PING[0] = time.time()
                return self.send(200, {"app": APP})
            if u.path == "/api/state":
                cfg = load_cfg()
                voice = sorted(n for n in os.listdir(VOICE) if n.endswith(".txt")) if os.path.isdir(VOICE) else []
                return self.send(200, {"ai": ai.status(cfg, full=False),
                                       "platforms": platforms(), "config": cfg, "templates": gen.load_templates(),
                                       "frozen": FROZEN,
                                       "voice": [{"name": n, "text": read_text(os.path.join(VOICE, n))} for n in voice]})
            if u.path == "/api/ai":                     # ⚙️ 설정의 AI 고르기 — 엔진마다 깔렸는지·사진 보는지
                return self.send(200, ai.status(load_cfg()))
            if u.path == "/api/job":
                with LOCK:
                    j = JOBS.get(q.get("id", ""))
                    return self.send(200 if j else 404, j if j else {"error": "작업을 찾을 수 없습니다."})
            if u.path == "/api/posts":
                return self.send(200, list_posts())
            if u.path == "/api/growth":
                return self.send(200, growth())
            if u.path == "/api/data":
                return self.send(200, data_status())
            if u.path == "/api/backup.zip":                 # 백업 파일 받기 — 브라우저가 내려받기로 저장
                os.makedirs(BACKUPS, exist_ok=True)
                photos = q.get("photos") == "1"
                name = "PostKit-backup-%s%s.zip" % (datetime.now().strftime("%Y%m%d-%H%M"), "" if photos else "-nophoto")
                path = os.path.join(BACKUPS, "download.zip")
                store.make_zip(DATA, path, photos=photos)
                size = os.path.getsize(path)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", 'attachment; filename="%s"' % name)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                os.remove(path)
                return
            if u.path == "/api/backups":                    # 자동 백업 목록
                fs = sorted((f for f in os.listdir(BACKUPS) if f.endswith(".zip")), reverse=True) if os.path.isdir(BACKUPS) else []
                return self.send(200, [{"name": f, "size": os.path.getsize(os.path.join(BACKUPS, f))} for f in fs])
            if u.path == "/api/age":                        # 아기 개월 수(설정의 생일 기준)
                bd = (load_cfg().get("kids") or {}).get("birthday", "")
                return self.send(200, {"age": gen.baby_age(bd, q.get("on") or datetime.now().strftime("%Y-%m-%d"))})
            if u.path == "/api/items":
                if q.get("kind") not in ITEMS:
                    raise ValueError("없는 목록입니다.")
                return self.send(200, load_items(q["kind"]))
            if u.path == "/api/post":
                return self.send(200, post_info(post_path(q.get("name", ""))))
            if u.path == "/api/photo":
                d = post_path(q.get("name", ""))
                n = q.get("file", "")
                p = os.path.join(d, "photos", n)
                if not NAME_RE.match(n) or not gen.inside(d, p) or not os.path.isfile(p):
                    return self.send(404, {"error": "사진이 없습니다."})
                ext = os.path.splitext(n)[1].lower().lstrip(".")
                with open(p, "rb") as f:
                    return self.send(200, f.read(), "image/" + ("jpeg" if ext in ("jpg", "jpeg") else ext))
            return self.send(404, {"error": "없는 길입니다."})
        except ValueError as e:
            return self.send(400, {"error": str(e)})

    def do_POST(self):
        if not self.post_ok():
            return self.send(403, {"error": "토큰이 맞지 않습니다 — 창을 새로 고침하세요."})
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        try:
            if u.path == "/api/photo":                  # 사진 한 장 — 몸통이 파일 그대로
                d = post_path(q.get("name", ""))
                n = os.path.basename(q.get("file", ""))
                if not NAME_RE.match(n) or not n.lower().endswith(gen.PHOTO_EXT):
                    raise ValueError("사진 파일(jpg·png·webp·gif)만 넣을 수 있습니다.")
                data = self.body_bytes()
                base, ext = os.path.splitext(n)
                p, i = os.path.join(d, "photos", n), 2
                while os.path.exists(p):
                    p, i = os.path.join(d, "photos", "%s-%d%s" % (base, i, ext)), i + 1
                with open(p, "wb") as f:
                    f.write(data)
                date = gen.process_photo(p)             # 크면 줄이고, 찍은 날짜를 읽는다
                return self.send(200, {"file": os.path.basename(p), "date": date, "date_text": gen.date_text(date)})
            if u.path == "/api/restore":                # 백업에서 되살리기 — 몸통이 zip 그대로. 먼저 지금 상태를 백업해 둔다
                if busy():
                    raise ValueError("글을 만드는 중이에요. 끝난 뒤에 해 주세요.")
                os.makedirs(BACKUPS, exist_ok=True)
                up = os.path.join(BACKUPS, "upload.zip")
                left = int(self.headers.get("Content-Length") or 0)
                if left > 4 * 1024 ** 3:
                    raise ValueError("파일이 너무 커요.")
                with open(up, "wb") as f:
                    while left > 0:
                        chunk = self.rfile.read(min(left, 1024 * 1024))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                try:
                    with zipfile.ZipFile(up) as z:
                        store.check_zip(z)                      # 먼저 검사하고
                    before = os.path.join(BACKUPS, "before-restore-%s.zip" % datetime.now().strftime("%Y%m%d-%H%M%S"))
                    store.make_zip(DATA, before, photos=True)
                    n = store.restore_zip(up, DATA)
                except zipfile.BadZipFile:
                    raise ValueError("zip 파일이 아니에요.")
                finally:
                    os.remove(up)
                log("백업에서 되살림", n, "개, 이전 상태:", before)
                return self.send(200, {"restored": n, "before": before})
            b = self.body_json()
            if u.path == "/api/data/pick":
                return self.send(200, {"path": pick_folder()})
            if u.path == "/api/data/move":
                return self.send(200, move_data(b.get("path", "")))
            if u.path == "/api/growth/compose":
                return self.send(200, {"name": compose_growth(b.get("names"))})
            if u.path == "/api/post/new":
                os.makedirs(POSTS, exist_ok=True)
                d = gen.new_post_dir(POSTS, b.get("memo", ""))
                write_text(os.path.join(d, "memo.txt"), b.get("memo", ""))
                write_text(os.path.join(d, "title.txt"), b.get("title", ""))
                write_text(os.path.join(d, "campaign.txt"), str(b.get("campaign") or ""))
                return self.send(200, {"name": os.path.basename(d)})
            if u.path == "/api/post/save":
                d = post_path(b.get("name", ""))
                write_text(os.path.join(d, "memo.txt"), b.get("memo", ""))
                write_text(os.path.join(d, "title.txt"), b.get("title", ""))
                if "campaign" in b:
                    write_text(os.path.join(d, "campaign.txt"), str(b.get("campaign") or ""))
                return self.send(200, {"ok": True})
            if u.path == "/api/items/save":
                if b.get("kind") not in ITEMS:
                    raise ValueError("없는 목록입니다.")
                return self.send(200, save_item(b["kind"], b.get("item")))
            if u.path == "/api/items/delete":
                if b.get("kind") not in ITEMS:
                    raise ValueError("없는 목록입니다.")
                delete_item(b["kind"], b.get("id", ""))
                return self.send(200, {"ok": True})
            if u.path == "/api/photo/delete":
                d = post_path(b.get("name", ""))
                p = os.path.join(d, "photos", os.path.basename(b.get("file", "")))
                if gen.inside(d, p) and os.path.isfile(p):
                    os.remove(p)
                return self.send(200, {"ok": True})
            if u.path == "/api/photo/order":
                d = post_path(b.get("name", ""))
                have = set(gen.photo_names(d))
                gen.save_photo_order(d, [n for n in b.get("files") or [] if n in have])
                return self.send(200, {"photos": gen.photo_names(d)})
            if u.path == "/api/gen":
                d = post_path(b.get("name", ""))
                return self.send(200, {"job": start_gen(d, b.get("platforms") or [])})
            if u.path == "/api/refine":
                d = post_path(b.get("name", ""))
                plat = platform(b.get("platform", ""))
                if not plat or not (b.get("instruction") or "").strip():
                    raise ValueError("어떻게 다듬을지 적어 주세요.")
                return self.send(200, refine(d, plat, b["instruction"], b.get("text", "")))
            if u.path == "/api/text":                   # 직접 고친 글 저장
                d = post_path(b.get("name", ""))
                if not platform(b.get("platform", "")):
                    raise ValueError("플랫폼이 올바르지 않습니다.")
                write_text(os.path.join(d, b["platform"] + ".md"), b.get("text", ""))
                return self.send(200, {"ok": True})
            if u.path == "/api/voice":
                text = (b.get("text") or "").strip()
                if not text:
                    raise ValueError("글을 붙여 넣으세요.")
                os.makedirs(VOICE, exist_ok=True)
                n = "%s-%s.txt" % (datetime.now().strftime("%Y%m%d-%H%M%S"), gen.safe_slug(text, 16))
                write_text(os.path.join(VOICE, n), text)
                return self.send(200, {"name": n})
            if u.path == "/api/voice/delete":
                p = os.path.join(VOICE, os.path.basename(b.get("name", "")))
                if gen.inside(VOICE, p) and os.path.isfile(p):
                    os.remove(p)
                return self.send(200, {"ok": True})
            if u.path == "/api/config":
                cfg = load_cfg()
                for k in ("voice_note", "default_platforms", "write_urls", "fixed_tags", "kids"):
                    if k in b:
                        cfg[k] = b[k]
                if "ai" in b:
                    cfg["ai"] = ai.clean_settings(b["ai"])
                os.makedirs(DATA, exist_ok=True)
                write_text(CFG, json.dumps(cfg, ensure_ascii=False, indent=2))
                return self.send(200, cfg)
            if u.path == "/api/phone":
                if b.get("on"):
                    phone_start()
                else:
                    phone_stop()
                return self.send(200, phone_status())
            if u.path == "/api/shortcuts":
                if not FROZEN:
                    raise ValueError("바로가기는 PostKit.exe 로 실행했을 때만 만들 수 있어요.")
                made = make_shortcuts()
                if not made:
                    raise ValueError("바로가기를 만들지 못했어요 — app.log 를 보세요.")
                return self.send(200, {"made": made})
            if u.path == "/api/open":
                if self.phone:                          # 폰에선 PC 를 건드리지 않는다 — 글쓰기 주소만 돌려줘 폰에서 연다
                    plat = platform(b.get("platform", ""))
                    url = (plat or {}).get("write_url", "")
                    if b.get("what") != "write" or not url.startswith("https://"):
                        raise ValueError("폰에서는 쓸 수 없는 기능이에요." if b.get("what") != "write" else "글쓰기 주소가 없어요.")
                    return self.send(200, {"url": url})
                if b.get("what") == "folder":
                    d = post_path(b.get("name", ""))
                    open_folder(os.path.join(d, "photos"))
                elif b.get("what") == "write":
                    plat = platform(b.get("platform", ""))
                    url = (plat or {}).get("write_url", "")
                    if not url.startswith("https://"):
                        raise ValueError("글쓰기 주소가 없습니다 — 카페는 ⚙ 에서 카페 글쓰기 주소를 넣어 주세요.")
                    webbrowser.open(url)            # 평소 브라우저 — 로그인돼 있는 곳
                elif b.get("what") == "data":
                    os.makedirs(DATA, exist_ok=True)
                    open_folder(DATA)
                return self.send(200, {"ok": True})
            return self.send(404, {"error": "없는 길입니다."})
        except ValueError as e:
            return self.send(400, {"error": str(e)})


# ---------- 폰에서 쓰기 ----------
# 켤 때만 이 PC 의 집 네트워크 주소(예: 192.168.0.5:8653)에 따로 연다. 켤 때마다 새 PIN, 5번 틀리면 5분 잠금.
# 폰은 PIN 으로 받은 세션(쿠키)으로만 들어오고, PC 를 건드리는 길(폴더 열기·바로가기·폰 설정)은 막는다.

PHONE = {"srv": None, "ip": "", "port": 8653, "pin": "", "sessions": set(), "fails": 0, "lock_until": 0.0}
PHONE_ONLY_PC = {"/api/phone", "/api/phone/qr.svg", "/api/shortcuts", "/api/data", "/api/data/pick", "/api/data/move",
                 "/api/backup.zip", "/api/backups", "/api/restore"}
LOGIN_HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>글 도우미</title><link rel="icon" href="/icon.png"><link rel="apple-touch-icon" href="/icon.png"><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;font:16px/1.5 -apple-system,"Apple SD Gothic Neo",sans-serif;color:#2f2b45;
background:radial-gradient(600px 400px at 0 0,#fde9f3,transparent 60%),radial-gradient(600px 400px at 100% 100%,#e6f1ff,transparent 60%),#f7f4fc}
.b{background:#fff;border-radius:20px;padding:28px 24px;width:min(320px,88vw);text-align:center;box-shadow:0 8px 22px rgba(110,90,170,.16)}
img{width:56px;height:56px;border-radius:16px}h1{font-size:19px;margin:10px 0 4px}p{color:#8781a0;font-size:13px;margin:0 0 16px}
input{width:100%;box-sizing:border-box;font-size:28px;letter-spacing:10px;text-align:center;padding:10px;border:2px solid #ebe4f6;border-radius:14px;outline:none}
input:focus{border-color:#8a72ee}button{margin-top:14px;width:100%;padding:12px;border:0;border-radius:999px;font-size:16px;font-weight:bold;color:#fff;
background:linear-gradient(135deg,#8a72ee,#ef8fbf)}#e{color:#e05a76;font-size:13px;min-height:20px;margin-top:10px}</style></head><body>
<form class="b" id="f"><img src="/icon.png" alt=""><h1>글 도우미</h1><p>PC 화면에 보이는 6자리 PIN 을 넣으세요</p>
<input id="p" inputmode="numeric" autocomplete="one-time-code" maxlength="6" autofocus><button>들어가기</button><div id="e"></div></form>
<script>document.getElementById("f").onsubmit=async e=>{e.preventDefault();
const r=await fetch("/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({pin:document.getElementById("p").value})});
if(r.ok)return location.reload();const d=await r.json().catch(()=>({}));document.getElementById("e").textContent=d.error||"PIN 이 맞지 않아요."};</script></body></html>"""


def lan_ip():
    """이 PC 의 네트워크 주소(밖으로 나가는 길의 주소 — 실제로 보내지는 않는다)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def phone_url():
    return "http://%s:%d/" % (PHONE["ip"], PHONE["port"])


def phone_status():
    on = bool(PHONE["srv"])
    return {"on": on, "url": phone_url() if on else "", "pin": PHONE["pin"] if on else ""}


def phone_start():
    if PHONE["srv"]:
        return
    ip = lan_ip()
    if not ip or ip.startswith("127."):
        raise ValueError("네트워크에 연결돼 있지 않아요 — 와이파이·랜선을 확인하세요.")
    try:
        srv = Server((ip, 8653), PhoneHandler)
    except OSError:
        srv = Server((ip, 0), PhoneHandler)          # 8653 을 다른 프로그램이 쓰면 빈 포트로
    PHONE.update(srv=srv, ip=ip, port=srv.server_port, pin="%06d" % secrets.randbelow(10 ** 6), sessions=set(), fails=0, lock_until=0.0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log("폰에서 쓰기 켬", phone_url())


def phone_stop():
    srv = PHONE["srv"]
    PHONE.update(srv=None, pin="", sessions=set())
    if srv:
        srv.shutdown()
        srv.server_close()
        log("폰에서 쓰기 끔")


class PhoneHandler(Handler):
    phone = True

    def host_ok(self):
        return self.headers.get("Host", "") == "%s:%d" % (PHONE["ip"], PHONE["port"])

    def session(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "pk" and v in PHONE["sessions"]:
                return v
        return ""

    def page_token(self):
        return self.session()

    def post_ok(self):
        s = self.session()
        return self.host_ok() and bool(s) and self.headers.get("X-Token") == s

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {"error": "host"})
        path = urllib.parse.urlparse(self.path).path
        if path in PHONE_ONLY_PC:
            return self.send(403, {"error": "PC 에서만 쓸 수 있어요."})
        if not self.session() and path != "/icon.png":
            if path == "/":
                return self.send(200, LOGIN_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return self.send(401, {"error": "PIN 으로 다시 들어와 주세요."})
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/login":
            return self.login()
        if path in PHONE_ONLY_PC:
            return self.send(403, {"error": "PC 에서만 쓸 수 있어요."})
        return super().do_POST()

    def login(self):
        if not self.host_ok():
            return self.send(403, {"error": "host"})
        now = time.time()
        if now < PHONE["lock_until"]:
            return self.send(429, {"error": "여러 번 틀려서 잠겼어요. %d분 뒤에 다시 해 보세요." % (int(PHONE["lock_until"] - now) // 60 + 1)})
        try:
            pin = str(self.body_json().get("pin", "")).strip()
        except ValueError:
            pin = ""
        if PHONE["pin"] and secrets.compare_digest(pin, PHONE["pin"]):
            tok = secrets.token_urlsafe(24)
            PHONE["sessions"].add(tok)
            PHONE["fails"] = 0
            log("폰 들어옴", self.client_address[0])
            return self.send(200, {"ok": True}, headers=[("Set-Cookie", "pk=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200" % tok)])
        PHONE["fails"] += 1
        if PHONE["fails"] >= 5:
            PHONE.update(fails=0, lock_until=now + 300)
            log("폰 PIN 5번 틀림 — 5분 잠금", self.client_address[0])
        return self.send(403, {"error": "PIN 이 맞지 않아요."})


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def already_running(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % port, timeout=2) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP
    except Exception:
        return False


def watchdog(srv):
    """창이 닫혀 신호가 45초 끊기면(처음 2분은 기다림) 끝낸다."""
    while True:
        time.sleep(5)
        last = LAST_PING[0]
        if (last and time.time() - last > 45) or (not last and time.time() - STARTED > 120):
            with LOCK:
                busy = any(v["status"] == "running" for j in JOBS.values() for v in j.values())
            if not busy:
                log("창이 닫혀 끝냅니다")
                srv.shutdown()
                return


def main():
    os.makedirs(POSTS, exist_ok=True)
    os.makedirs(VOICE, exist_ok=True)
    port = PORT
    try:
        srv = Server(("127.0.0.1", port), Handler)
    except OSError:
        if already_running(port):           # 이미 떠 있으면 창만 하나 더
            open_window("http://127.0.0.1:%d/" % port)
            return
        srv = Server(("127.0.0.1", 0), Handler)     # 다른 프로그램이 쓰면 빈 포트로
        port = srv.server_port
    url = "http://127.0.0.1:%d/" % port
    log("시작", url)
    threading.Thread(target=watchdog, args=(srv,), daemon=True).start()
    threading.Thread(target=first_run_shortcuts, daemon=True).start()
    threading.Thread(target=daily_backup, daemon=True).start()
    if "--no-window" not in sys.argv:
        open_window(url)
    else:
        print(url, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
