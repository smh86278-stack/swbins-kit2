# -*- coding: utf-8 -*-
"""앱 스모크 시험 — 앱(소스 또는 빌드한 exe·.app)을 창 없이 띄워 화면·API 가 뜨는지 본다. CI 용(unittest 가 줍지 않게 test_ 가 아님).

    python tests/smoke.py [--shot 파일.png] [--os mac|win] -- <띄울 명령…>
    예) python tests/smoke.py --shot shot.png -- python app.py --no-window
        python tests/smoke.py -- dist/PostKit.app/Contents/MacOS/PostKit --no-window

- 데이터는 임시 폴더(POSTKIT_DATA)로 — 실제 데이터를 건드리지 않는다. 포트는 앱 기본 8650.
- --shot 이면 Playwright(크로미엄)로 첫 화면을 찍는다(pip install playwright && python -m playwright install chromium).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

URL = "http://127.0.0.1:8650/"     # 앱이 다른 포트를 알리면(8650 이 아직 안 풀렸을 때 빈 포트로 뜬다) 그 주소로 바꾼다


def follow(proc):
    """앱 출력을 그대로 보이며, --no-window 가 찍는 주소를 URL 로 삼는다(윈도우 창 없는 exe 는 출력이 없어 8650 그대로)."""
    global URL
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip()
        print(line, flush=True)
        if line.startswith("http://127.0.0.1:"):
            URL = line.strip()


def get(path, timeout=3):
    with urllib.request.urlopen(URL.rstrip("/") + path, timeout=timeout) as r:
        return r.status, r.read()


def wait_up(proc, secs=90):
    end = time.time() + secs
    while time.time() < end:
        if proc.poll() is not None:
            raise SystemExit("앱이 먼저 끝났습니다(rc=%s)" % proc.returncode)
        try:
            return json.loads(get("/api/state")[1].decode("utf-8"))
        except OSError:
            time.sleep(1)
    raise SystemExit("앱이 %d초 안에 뜨지 않았습니다" % secs)


def shoot(path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1180, "height": 820}, locale="ko-KR")
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL)
        page.wait_for_selector("nav button[data-tab]")
        page.wait_for_timeout(1500)
        page.screenshot(path=path)
        b.close()
    if errors:
        raise SystemExit("화면 스크립트 오류: %s" % errors)


def stop(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":         # 한 파일 exe 는 부트로더 아래 자식이 실제 앱 — 같이 끈다
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main(argv):
    if "--" not in argv:
        raise SystemExit(__doc__)
    opts, cmd = argv[:argv.index("--")], argv[argv.index("--") + 1:]
    shot = opts[opts.index("--shot") + 1] if "--shot" in opts else ""
    want_os = opts[opts.index("--os") + 1] if "--os" in opts else ""
    try:
        get("/api/state", timeout=1)
        raise SystemExit("8650 에 이미 글 도우미가 떠 있습니다 — 끄고 다시 하세요(실제 데이터를 건드리지 않게)")
    except OSError:
        pass
    data = tempfile.mkdtemp(prefix="postkit-smoke-")
    env = dict(os.environ, POSTKIT_DATA=data, PYTHONUTF8="1")
    proc = subprocess.Popen(cmd, env=env, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    threading.Thread(target=follow, args=(proc,), daemon=True).start()
    try:
        st = wait_up(proc)
        print("state:", {k: st.get(k) for k in ("os", "frozen")}, "AI:", st["ai"]["name"], "준비" if st["ai"]["ready"] else "없음")
        assert len(st["platforms"]) >= 4, st["platforms"]
        if want_os:
            assert st.get("os") == want_os, st.get("os")
        code, html = get("/")
        assert code == 200 and "글 도우미".encode("utf-8") in html and b"__TOKEN__" not in html, "첫 화면이 이상합니다"
        assert get("/icon.png")[0] == 200
        assert get("/api/ai")[0] == 200
        assert get("/api/data")[0] == 200
        if shot:
            shoot(shot)
            print("찍었습니다:", shot)
        print("스모크 통과")
    finally:
        stop(proc)
        shutil.rmtree(data, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1:])
