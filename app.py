# -*- coding: utf-8 -*-
"""글 도우미(PostKit) — 사진·메모를 넣으면 플랫폼별 글을 내 말투로 써 주는 앱.

    python app.py      (exe 는 build.py)

- 화면은 127.0.0.1 에만 연다. 상태를 바꾸는 POST 는 띄울 때마다 새로 만드는 토큰(X-Token)이 있어야 한다.
- 창은 Edge --app(따로 둔 프로필). 창이 닫혀 신호(/api/ping)가 끊기면 서버도 스스로 끝난다.
- 데이터는 %APPDATA%\\PostKit (config.json · voice\\*.txt · posts\\<글>\\).
- 올리기는 사람이 한다 — 여기선 복사와 글쓰기 창 열기까지만.
"""
import http.server
import json
import os
import re
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime

import gen

APP = "PostKit"
PORT = 8650
IS_WIN = sys.platform == "win32"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("POSTKIT_DATA") or os.path.join(os.environ.get("APPDATA") or HERE, APP)     # 시험할 땐 POSTKIT_DATA 로 따로
LOCALDATA = os.path.join(os.environ.get("LOCALAPPDATA") or HERE, APP)
POSTS = os.path.join(DATA, "posts")
VOICE = os.path.join(DATA, "voice")
CFG = os.path.join(DATA, "config.json")
TOKEN = secrets.token_urlsafe(24)
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


def history(post_dir, pid):
    rows = []
    for line in read_text(os.path.join(post_dir, pid + ".history.jsonl")).splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def save_result(post_dir, pid, text, session_id, instruction):
    write_text(os.path.join(post_dir, pid + ".md"), text)
    with open(os.path.join(post_dir, pid + ".history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "instruction": instruction,
                            "text": text, "session_id": session_id}, ensure_ascii=False) + "\n")


def post_info(post_dir):
    name = os.path.basename(post_dir)
    texts = {}
    for p in platforms():
        t = read_text(os.path.join(post_dir, p["id"] + ".md"))
        if t:
            texts[p["id"]] = t
    return {"name": name, "memo": read_text(os.path.join(post_dir, "memo.txt")),
            "title": read_text(os.path.join(post_dir, "title.txt")),
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
                    "platforms": [p["id"] for p in platforms() if os.path.isfile(os.path.join(d, p["id"] + ".md"))],
                    "photos": len(gen.photo_names(d))})
    return out


# ---------- 글 만들기 · 다듬기 ----------

def gen_one(job, post_dir, plat, cfg):
    memo = read_text(os.path.join(post_dir, "memo.txt"))
    title = read_text(os.path.join(post_dir, "title.txt"))
    prompt = gen.build_prompt(plat, memo, title, gen.photo_names(post_dir), gen.load_voice(VOICE), cfg["voice_note"])
    r = gen.run(prompt, post_dir)
    if r["text"]:
        save_result(post_dir, plat["id"], r["text"], r["session_id"], "")
    with LOCK:
        JOBS[job][plat["id"]] = {"status": "done" if r["text"] else "error", "text": r["text"], "error": r["error"]}
    log("gen", os.path.basename(post_dir), plat["id"], "ok" if r["text"] else "error: " + r["error"][:200])


def start_gen(post_dir, pids):
    cfg = load_cfg()
    job = secrets.token_hex(6)
    plats = [p for p in (platform(x) for x in pids) if p]
    if not plats:
        raise ValueError("플랫폼을 하나 이상 고르세요.")
    with LOCK:
        JOBS[job] = {p["id"]: {"status": "running", "text": "", "error": ""} for p in plats}
    for p in plats:
        threading.Thread(target=gen_one, args=(job, post_dir, p, cfg), daemon=True).start()
    return job


def refine(post_dir, plat, instruction, current):
    cfg = load_cfg()
    rows = history(post_dir, plat["id"])
    sid = next((r.get("session_id") for r in reversed(rows) if r.get("session_id")), "")
    r = {"text": "", "error": "", "session_id": ""}
    if sid:
        r = gen.run(gen.build_refine_prompt(plat, instruction, current), post_dir, resume_id=sid, timeout=180)
    if not r["text"]:      # 세션이 없거나 이어받기에 실패하면 규칙·말투를 다시 붙여 새로
        r = gen.run(gen.build_refine_prompt(plat, instruction, current, standalone=True,
                                            voice_texts=gen.load_voice(VOICE), voice_note=cfg["voice_note"]),
                    post_dir, timeout=180)
    if r["text"]:
        save_result(post_dir, plat["id"], r["text"], r["session_id"], instruction)
    log("refine", os.path.basename(post_dir), plat["id"], "ok" if r["text"] else "error: " + r["error"][:200])
    return r


# ---------- 열기 ----------

def open_folder(path):
    if IS_WIN:
        os.startfile(path)  # noqa: S606 — 내 데이터 폴더만 연다
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


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

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def host_ok(self):
        return self.headers.get("Host", "") in ("127.0.0.1:%d" % self.server.server_port, "localhost:%d" % self.server.server_port)

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
                html = read_text(os.path.join(gen.RES, "ui.html")).replace("__TOKEN__", TOKEN)
                return self.send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if u.path == "/api/ping":
                LAST_PING[0] = time.time()
                return self.send(200, {"app": APP})
            if u.path == "/api/state":
                cfg = load_cfg()
                voice = sorted(n for n in os.listdir(VOICE) if n.endswith(".txt")) if os.path.isdir(VOICE) else []
                claude = gen.find_claude()
                return self.send(200, {"claude": claude[0] if claude else "", "no_claude": gen.NO_CLAUDE,
                                       "platforms": platforms(), "config": cfg,
                                       "voice": [{"name": n, "text": read_text(os.path.join(VOICE, n))} for n in voice]})
            if u.path == "/api/job":
                with LOCK:
                    j = JOBS.get(q.get("id", ""))
                    return self.send(200 if j else 404, j if j else {"error": "작업을 찾을 수 없습니다."})
            if u.path == "/api/posts":
                return self.send(200, list_posts())
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
        if not self.host_ok() or self.headers.get("X-Token") != TOKEN:
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
                return self.send(200, {"file": os.path.basename(p)})
            b = self.body_json()
            if u.path == "/api/post/new":
                os.makedirs(POSTS, exist_ok=True)
                d = gen.new_post_dir(POSTS, b.get("memo", ""))
                write_text(os.path.join(d, "memo.txt"), b.get("memo", ""))
                write_text(os.path.join(d, "title.txt"), b.get("title", ""))
                return self.send(200, {"name": os.path.basename(d)})
            if u.path == "/api/post/save":
                d = post_path(b.get("name", ""))
                write_text(os.path.join(d, "memo.txt"), b.get("memo", ""))
                write_text(os.path.join(d, "title.txt"), b.get("title", ""))
                return self.send(200, {"ok": True})
            if u.path == "/api/photo/delete":
                d = post_path(b.get("name", ""))
                p = os.path.join(d, "photos", os.path.basename(b.get("file", "")))
                if gen.inside(d, p) and os.path.isfile(p):
                    os.remove(p)
                return self.send(200, {"ok": True})
            if u.path == "/api/gen":
                d = post_path(b.get("name", ""))
                if not gen.find_claude():
                    raise ValueError(gen.NO_CLAUDE)
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
                for k in ("voice_note", "default_platforms", "write_urls"):
                    if k in b:
                        cfg[k] = b[k]
                os.makedirs(DATA, exist_ok=True)
                write_text(CFG, json.dumps(cfg, ensure_ascii=False, indent=2))
                return self.send(200, cfg)
            if u.path == "/api/open":
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
    if "--no-window" not in sys.argv:
        open_window(url)
    else:
        print(url, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
