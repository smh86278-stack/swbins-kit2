# -*- coding: utf-8 -*-
"""GitHub 릴리스 올리기 — 커밋해 둔 상태에서 exe 를 빌드하고 태그·릴리스·DungiLog.exe 첨부까지.

    python release.py v0.3.1 notes.md          (notes.md = 릴리스 본문, 한국어 그대로)
    python release.py v0.3.1 notes.md --no-build   (dist\\DungiLog.exe 를 그대로 올림)

- 이 파이썬으로 build.py 를 돌린다 → Pillow·PyInstaller 가 있는 파이썬으로 실행할 것.
- 토큰은 `git credential fill`(GCM)에서 꺼내 이 프로세스 안에서만 쓴다 — 화면·파일에 남기지 않는다.
- 커밋 안 한 변경이 있거나 태그가 이미 있으면 멈춘다. CLAUDE.md 「git · 릴리스」 의 순서를 코드로 옮긴 것.
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dist", "DungiLog.exe")
OWNER = "smh86278-stack"


def git(*args, **kw):
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, encoding="utf-8", check=True, **kw).stdout


def repo_name():
    url = git("remote", "get-url", "origin").strip()
    m = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$", url)
    if not m:
        raise SystemExit("origin 이 GitHub 저장소가 아닙니다: " + url)
    return m.group(1)


def token():
    out = git("credential", "fill", input="protocol=https\nhost=github.com\nusername=%s\n\n" % OWNER)
    pw = dict(l.split("=", 1) for l in out.splitlines() if "=" in l).get("password")
    if not pw:
        raise SystemExit("git 자격 증명에서 GitHub 토큰을 찾지 못했습니다")
    return pw


def api(url, tok, data=None, ctype=None):
    h = {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if ctype:
        h["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit("GitHub HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300]))


def main(argv):
    if len(argv) < 2 or not re.fullmatch(r"v\d+\.\d+\.\d+", argv[0]):
        raise SystemExit(__doc__)
    tag, notes = argv[0], argv[1]
    body = open(notes, encoding="utf-8").read()
    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise SystemExit("커밋 안 한 변경이 있습니다 — 먼저 커밋하세요(빌드는 작업 폴더를, 태그는 커밋을 가리킨다)")
    if tag in git("tag", "--list", tag).split():
        raise SystemExit("태그가 이미 있습니다: " + tag)
    if "--no-build" not in argv:
        subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "build.py")], cwd=HERE, check=True)
    if not os.path.isfile(EXE):
        raise SystemExit("exe 가 없습니다: " + EXE)
    git("tag", "-a", tag, "-m", tag)
    git("push", "origin", "main")
    git("push", "origin", tag)
    tok = token()
    rel = api("https://api.github.com/repos/%s/releases" % repo_name(), tok,
              json.dumps({"tag_name": tag, "name": tag, "body": body}, ensure_ascii=False).encode("utf-8"),
              "application/json; charset=utf-8")
    with open(EXE, "rb") as f:
        asset = api(rel["upload_url"].split("{")[0] + "?name=DungiLog.exe", tok, f.read(), "application/octet-stream")
    print("릴리스:", rel["html_url"])
    print("첨부:", asset["name"], asset["size"], asset["state"])


if __name__ == "__main__":
    main(sys.argv[1:])
