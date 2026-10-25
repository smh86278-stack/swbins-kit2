# -*- coding: utf-8 -*-
"""AI 고르기 — Claude Code(기본) · Codex(ChatGPT) · Gemini CLI · 로컬 AI(Ollama). 표준 라이브러리만.

API 키는 쓰지 않는다 — 각 CLI 에 이 PC 사용자가 직접 로그인해 둔 것을 그대로 띄울 뿐, 토큰을 읽거나 저장하지 않는다.
Ollama 는 이 PC 안(127.0.0.1:11434)이라 키가 없다.

설정 config.json 의 "ai": {"engine": "claude" | "codex" | "gemini" | "ollama", "models": {엔진: 모델 이름}}
모델 이름이 비면 그 CLI 의 기본 모델(Ollama 는 qwen3:8b).

사진 보기 — 엔진마다 다르다:
  claude : 글 폴더에서 띄우고 Read 도구로 ./photos/ 를 연다(지금까지 그대로, gen.run).
  codex  : codex exec --image 로 사진 파일을 붙인다. 샌드박스 read-only.
  gemini : 글 폴더에서 띄우고 read_file 도구로 ./photos/ 를 연다(읽기 도구는 묻지 않고 돈다,
           --approval-mode default 라 파일 쓰기·명령은 헤드리스에서 빠진다). 버전에 따라 안 될 수 있다.
  ollama : 모델이 비전 모델(/api/show 의 capabilities 에 vision)일 때만 사진을 base64 로 붙인다.
           qwen3 같은 글 전용 모델이면 사진은 못 보고 메모만으로 쓴다.
다듬기 이어받기(세션)는 claude 만 — 다른 엔진은 규칙·말투·지금 글을 다시 붙여 새로 부른다.
명령줄 옵션은 codex-cli 0.63 `codex exec --help`, Gemini CLI docs/cli/cli-reference.md(2026-10) 기준.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

import gen

ENGINES = ("claude", "codex", "gemini", "ollama")
NAMES = {"claude": "Claude Code", "codex": "Codex (ChatGPT)", "gemini": "Gemini CLI", "ollama": "로컬 AI (Ollama)"}
INSTALL = {"claude": "Claude Code 설치(npm install -g @anthropic-ai/claude-code) → 명령 창(맥은 터미널)에서 claude 를 한 번 실행해 로그인",
           "codex": "npm install -g @openai/codex → 명령 창(맥은 터미널)에서 codex login (ChatGPT 계정)",
           "gemini": "npm install -g @google/gemini-cli → 명령 창(맥은 터미널)에서 gemini 를 한 번 실행해 구글 계정으로 로그인",
           "ollama": "https://ollama.com 에서 받아 설치 → 명령 창(맥은 터미널)에서 ollama pull qwen3:8b"}
PHOTOS = {"claude": "사진 봐요", "codex": "사진 봐요(파일 첨부)", "gemini": "사진 봐요(파일 읽기 도구 — 버전에 따라 안 될 수 있어요)",
          "ollama": "비전 모델(gemma3·qwen2.5vl·llava 등)일 때만 사진 봐요 — qwen3 같은 글 전용 모델은 메모만으로 써요"}
OLLAMA_URL = "http://127.0.0.1:11434"          # 이 PC 안에서만. 시험은 이 값을 가짜 서버로 바꾼다
OLLAMA_MODEL = "qwen3:8b"
THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def settings(cfg):
    s = dict((cfg or {}).get("ai") or {})
    engine = s.get("engine") if s.get("engine") in ENGINES else "claude"
    models = {e: str(m).strip() for e, m in (s.get("models") or {}).items() if e in ENGINES and str(m or "").strip()}
    return {"engine": engine, "models": models}


def clean_settings(v):
    """화면에서 온 값 → 저장할 값(모르는 엔진·이상한 모델 이름은 버린다)."""
    s = settings({"ai": v if isinstance(v, dict) else {}})
    s["models"] = {e: m[:80] for e, m in s["models"].items() if re.fullmatch(r"[\w.:/\-]+", m)}
    return s


def model_of(s):
    m = s["models"].get(s["engine"], "")
    return m or (OLLAMA_MODEL if s["engine"] == "ollama" else "")


def exe(engine):
    """CLI 실행 파일(목록). npm 으로 깔면 codex.cmd 처럼 .cmd 다. 없으면 None."""
    if engine == "claude":
        return gen.find_claude()
    path = gen.which(engine)          # 맥 앱은 PATH 가 짧아서 흔히 깔리는 곳까지 본다
    return [path] if path else None


def _shell(path):
    # .cmd(npm 설치)는 cmd.exe 를 거쳐야 뜬다. 인자는 단순한 것만, 프롬프트는 표준 입력으로.
    return os.name == "nt" and not str(path).lower().endswith(".exe")


def _http(path, body=None, timeout=5):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(OLLAMA_URL + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ollama_models(timeout=1.5):
    """켜진 Ollama 에 받아 둔 모델 이름들 — 꺼져 있거나 없으면 None."""
    try:
        return [m.get("name") for m in _http("/api/tags", timeout=timeout).get("models") or []]
    except (OSError, ValueError):
        return None


def _has_model(models, want):
    return any(m == want or (":" not in want and m.split(":")[0] == want) or m == want + ":latest" for m in models or [])


def ollama_vision(model):
    """그 모델이 사진을 보는지 — /api/show 의 capabilities. 알 수 없으면 False(못 본다고 친다)."""
    try:
        return "vision" in (_http("/api/show", {"model": model}).get("capabilities") or [])
    except (OSError, ValueError):
        return False


def can_see(s):
    """지금 고른 AI 가 사진을 볼 수 있는지."""
    return ollama_vision(model_of(s)) if s["engine"] == "ollama" else True


def status(cfg, full=True):
    """화면용 — 고른 엔진·준비됐는지·엔진마다 깔렸는지. full=False 면 고른 것만(가볍게)."""
    s = settings(cfg)
    rows = []
    for e in (ENGINES if full else (s["engine"],)):
        row = {"id": e, "name": NAMES[e], "install": INSTALL[e], "photos": PHOTOS[e]}
        if e == "ollama":
            models = ollama_models()
            want = s["models"].get("ollama") or OLLAMA_MODEL
            row["installed"] = _has_model(models, want)
            row["models"] = models or []
            if models is not None and not row["installed"]:
                row["install"] = "Ollama 는 켜져 있어요 — 명령 창에서 ollama pull %s" % want
            if row["installed"]:
                row["vision"] = ollama_vision(want)
        else:
            path = exe(e)
            row["installed"] = bool(path)
            row["path"] = path[0] if path else ""
        rows.append(row)
    cur = next(r for r in rows if r["id"] == s["engine"])
    return dict(s, name=NAMES[s["engine"]], model=model_of(s), ready=cur["installed"], hint=cur["install"],
                engines=rows if full else [])


def not_ready(s):
    """고른 AI 를 쓸 수 없으면 그 까닭(쓸 수 있으면 '')."""
    e = s["engine"]
    if e == "ollama":
        models = ollama_models()
        if models is None:
            return "로컬 AI(Ollama)가 꺼져 있거나 없어요 — " + INSTALL["ollama"]
        if not _has_model(models, model_of(s)):
            return "Ollama 에 %s 모델이 없어요 — 명령 창에서 ollama pull %s" % (model_of(s), model_of(s))
        return ""
    if not exe(e):
        return gen.NO_CLAUDE if e == "claude" else "%s 를 찾지 못했어요 — %s" % (NAMES[e], INSTALL[e])
    return ""


def photo_mode(s, seeable=None):
    """build_prompt 에 넘길 사진 보는 법."""
    e = s["engine"]
    if e == "ollama":
        return "attached" if (can_see(s) if seeable is None else seeable) else "none"
    return {"claude": "Read", "codex": "attached", "gemini": "read_file"}[e]


def _fail(msg):
    return {"text": "", "session_id": "", "error": msg}


def _run_cli(argv, prompt, cwd, timeout, name):
    # 윈도우는 콘솔 창 없이, 맥·리눅스는 새 프로세스 그룹으로(멈추면 node 자식까지 같이 끈다)
    kw = {"creationflags": gen.CREATE_NO_WINDOW} if gen.IS_WIN else {"start_new_session": True}
    try:
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             cwd=cwd, env=gen.cli_env(), shell=_shell(argv[0]), **kw)
    except OSError as e:
        return None, "%s 를 띄우지 못했어요: %s" % (name, e)
    try:
        out, err = p.communicate(prompt.encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        if gen.IS_WIN:      # .cmd 면 cmd.exe 아래 node 까지 같이 끈다
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=gen.CREATE_NO_WINDOW)
        else:
            try:
                os.killpg(p.pid, 9)
            except OSError:
                p.kill()
        p.communicate()
        return None, "시간이 너무 오래 걸려 멈췄습니다(%d초)." % timeout
    if p.returncode != 0:
        return None, "%s 실행 실패 (rc=%s): %s" % (name, p.returncode, (err or out).decode("utf-8", "replace").strip()[-600:])
    return out.decode("utf-8", "replace"), ""


def _codex(prompt, workdir, photos, model, timeout):
    path = exe("codex")[0]
    tmp = tempfile.mkdtemp(prefix="postkit-codex-")
    out_file = os.path.join(tmp, "answer.md")
    argv = [path, "exec", "--cd", workdir, "--sandbox", "read-only", "--skip-git-repo-check", "--color", "never",
            "-o", out_file] + (["-m", model] if model else [])
    if photos:              # --image 는 값을 여러 개 받으니 맨 끝에. 프롬프트는 인자 없이 표준 입력으로
        argv += ["--image"] + [os.path.join(workdir, "photos", n) for n in photos]
    try:
        out, err = _run_cli(argv, prompt, workdir, timeout, NAMES["codex"])
        if err:
            return _fail(err)
        if os.path.isfile(out_file):
            with open(out_file, encoding="utf-8", errors="replace") as f:
                out = f.read()
        return {"text": gen.clean_text(out), "session_id": "", "error": "" if out.strip() else "Codex 가 빈 답을 줬어요."}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _gemini(prompt, workdir, model, timeout):
    path = exe("gemini")[0]
    argv = [path, "-p", "Follow the instructions given on standard input and reply with the post text only.",
            "--approval-mode", "default", "-o", "text"] + (["-m", model] if model else [])
    out, err = _run_cli(argv, prompt, workdir, timeout, NAMES["gemini"])
    if err:
        return _fail(err)
    return {"text": gen.clean_text(out), "session_id": "", "error": "" if out.strip() else "Gemini 가 빈 답을 줬어요."}


def _ollama(prompt, workdir, photos, model, timeout):
    msg = {"role": "user", "content": prompt}
    if photos:
        imgs = []
        for n in photos:
            with open(os.path.join(workdir, "photos", n), "rb") as f:
                imgs.append(base64.b64encode(f.read()).decode("ascii"))
        msg["images"] = imgs
    body = {"model": model, "messages": [msg], "stream": False, "options": {"temperature": 0.7, "num_ctx": 16384}}
    try:
        d = _http("/api/chat", body, timeout=timeout)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        if e.code == 404:
            return _fail("Ollama 에 %s 모델이 없어요 — 명령 창에서 ollama pull %s" % (model, model))
        return _fail("Ollama 오류 %s: %s" % (e.code, detail))
    except (OSError, ValueError) as e:       # URLError·시간 초과도 여기
        return _fail("Ollama 에 연결하지 못했어요(%s) — Ollama 를 켜 두세요." % getattr(e, "reason", e))
    if d.get("error"):
        return _fail("Ollama 오류: %s" % d["error"])
    text = gen.clean_text(THINK_RE.sub("", (d.get("message") or {}).get("content") or ""))
    return {"text": text, "session_id": "", "error": "" if text else "Ollama 가 빈 답을 줬어요."}


def run(s, prompt, workdir, photos=(), resume_id=None, timeout=300):
    """고른 AI 로 글 한 번 → {text, session_id, error}. photos 는 붙일 사진 이름(attached 방식일 때만 쓴다)."""
    e = s["engine"]
    model = model_of(s)
    if e == "claude":
        return gen.run(prompt, workdir, resume_id=resume_id, timeout=timeout, model=model)
    why = not_ready(s) if e != "ollama" else ""
    if why:
        return _fail(why)
    photos = list(photos)     # 몇 장 붙일지는 부르는 쪽(설정 photo_max)이 정한다
    if e == "codex":
        return _codex(prompt, workdir, photos, model, timeout)
    if e == "gemini":
        return _gemini(prompt, workdir, model, timeout)
    return _ollama(prompt, workdir, photos, model, max(timeout, 600))     # 로컬은 느리다
