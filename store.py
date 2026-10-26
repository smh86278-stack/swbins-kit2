# -*- coding: utf-8 -*-
"""데이터 폴더 · 백업 · 성장 기록 — 화면(app.py)과 따로 시험할 수 있게 여기 모은다.

데이터 폴더는 기본이 %APPDATA%\\PostKit(맥은 ~/Library/Application Support/PostKit — default_dirs).
「데이터 폴더 옮기기」를 하면 그 자리를 기본 폴더의 location.json 에 적어 두고
다음부터 그 폴더를 쓴다(OneDrive 같은 곳에 두면 백업·여러 PC 공유가 저절로 된다).
"""
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime

KNOWN = ("config.json", "campaigns.json", "ledger.json", "voice", "posts")    # 데이터 폴더에 있는 것 — 백업·되살리기는 이것만
PHOTO_DIR = "photos"


# ---------- 데이터 폴더 ----------

def default_dirs(app="PostKit", environ=None, platform=None, home=None, fallback=""):
    """(데이터, 로컬, 로그) 기본 폴더 — OS 마다.
    윈도우: %APPDATA%\\PostKit · %LOCALAPPDATA%\\PostKit(자동 백업·창 프로필) · 로그도 로컬
    맥: ~/Library/Application Support/PostKit · ~/Library/Application Support/PostKit-local · ~/Library/Logs/PostKit
    그 밖(리눅스): ~/.local/share/PostKit · ~/.local/state/PostKit"""
    environ = os.environ if environ is None else environ
    platform = platform or sys.platform
    home = home or os.path.expanduser("~")
    if platform == "win32":
        data = os.path.join(environ.get("APPDATA") or fallback or home, app)
        local = os.path.join(environ.get("LOCALAPPDATA") or fallback or home, app)
        return data, local, local
    if platform == "darwin":
        lib = os.path.join(home, "Library")
        return (os.path.join(lib, "Application Support", app), os.path.join(lib, "Application Support", app + "-local"),
                os.path.join(lib, "Logs", app))
    share = environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    state = environ.get("XDG_STATE_HOME") or os.path.join(home, ".local", "state")
    return os.path.join(share, app), os.path.join(state, app), os.path.join(state, app)


def load_location(home):
    """옮겨 둔 데이터 폴더(없으면 '')."""
    try:
        with open(os.path.join(home, "location.json"), encoding="utf-8") as f:
            p = json.load(f).get("data_dir", "")
        return p if p and os.path.isdir(p) else ""
    except (OSError, ValueError, AttributeError):
        return ""


def save_location(home, path):
    """path 가 기본 자리(home)면 기록을 지운다."""
    os.makedirs(home, exist_ok=True)
    loc = os.path.join(home, "location.json")
    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(home)):
        if os.path.exists(loc):
            os.remove(loc)
        return
    with open(loc, "w", encoding="utf-8") as f:
        json.dump({"data_dir": path}, f, ensure_ascii=False)


def has_data(d):
    return os.path.isdir(d) and any(os.path.exists(os.path.join(d, k)) for k in KNOWN)


def target_dir(picked):
    """고른 폴더 → 실제 데이터 폴더. 이미 데이터가 있거나 이름이 PostKit 이면 그대로, 아니면 그 안에 PostKit."""
    picked = os.path.abspath(picked)
    if has_data(picked) or os.path.basename(picked).lower() == "postkit":
        return picked
    return os.path.join(picked, "PostKit")


def copy_data(src, dst):
    """src 의 데이터를 dst 로 복사(dst 에 이미 있는 파일은 덮어쓴다). 복사한 파일 수."""
    n = 0
    os.makedirs(dst, exist_ok=True)
    for k in KNOWN:
        s = os.path.join(src, k)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(dst, k))
            n += 1
        elif os.path.isdir(s):
            for root, _, files in os.walk(s):
                rel = os.path.relpath(root, src)
                os.makedirs(os.path.join(dst, rel), exist_ok=True)
                for f in files:
                    if f.endswith(".tmp"):
                        continue
                    shutil.copy2(os.path.join(root, f), os.path.join(dst, rel, f))
                    n += 1
    return n


def _mac_cloud(home):
    """맥 클라우드 폴더 — ~/Library/CloudStorage(OneDrive·구글 드라이브) · iCloud Drive. [(이름, 경로, 회사 OneDrive 인가)]"""
    out = []
    cs = os.path.join(home, "Library", "CloudStorage")
    for n in (sorted(os.listdir(cs)) if os.path.isdir(cs) else []):
        p = os.path.join(cs, n)
        if not os.path.isdir(p):
            continue
        if n == "OneDrive-Personal":
            out.append(("OneDrive(개인)", p, False))
        elif n.startswith("OneDrive-"):                 # OneDrive-<회사 이름> 은 회사 것
            out.append(("OneDrive(회사)", p, True))
        elif n.startswith("GoogleDrive-"):
            for sub in ("내 드라이브", "My Drive"):
                if os.path.isdir(os.path.join(p, sub)):
                    out.append(("구글 드라이브", os.path.join(p, sub), False))
    icloud = os.path.join(home, "Library", "Mobile Documents", "com~apple~CloudDocs")
    if os.path.isdir(icloud):
        out.append(("iCloud Drive", icloud, False))
    return out


def cloud_folders(platform=None, home=None):
    """개인 OneDrive · 구글 드라이브(맥은 iCloud Drive 도) 폴더(있는 것만). 회사 OneDrive 는 일부러 빼고 따로 알린다."""
    platform = platform or sys.platform
    if platform == "darwin":
        return [{"name": n, "path": p} for n, p, company in _mac_cloud(home or os.path.expanduser("~")) if not company]
    out = []
    if platform != "win32":
        return out
    personal = os.environ.get("OneDriveConsumer") or ""
    if personal and os.path.isdir(personal):
        out.append({"name": "OneDrive(개인)", "path": personal})
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        for sub in ("내 드라이브", "My Drive"):
            p = "%s:\\%s" % (letter, sub)
            if os.path.isdir(p):
                out.append({"name": "구글 드라이브", "path": p})
    return out


def company_onedrive(platform=None, home=None):
    if (platform or sys.platform) == "darwin":
        return next((p for _, p, company in _mac_cloud(home or os.path.expanduser("~")) if company), "")
    return os.environ.get("OneDriveCommercial") or ""


# ---------- 백업 ----------

def _walk_backup(src, photos):
    """(실제 경로, zip 안 이름) — KNOWN 만, 임시 파일 빼고, photos=False 면 사진 폴더 빼고."""
    for k in KNOWN:
        s = os.path.join(src, k)
        if os.path.isfile(s):
            yield s, k
        elif os.path.isdir(s):
            for root, dirs, files in os.walk(s):
                if not photos and PHOTO_DIR in dirs and k == "posts":
                    dirs.remove(PHOTO_DIR)
                for f in files:
                    if f.endswith(".tmp"):
                        continue
                    p = os.path.join(root, f)
                    yield p, os.path.relpath(p, src).replace(os.sep, "/")


def make_zip(src, zip_path, photos=True):
    """데이터 폴더를 zip 으로. 넣은 파일 수."""
    n = 0
    tmp = zip_path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("postkit-backup.json", json.dumps({"made": datetime.now().isoformat(timespec="seconds"), "photos": photos}))
        for p, name in _walk_backup(src, photos):
            z.write(p, name)
            n += 1
    os.replace(tmp, zip_path)
    return n


def check_zip(zf):
    """되살릴 zip 이 우리 백업인지, 이상한 경로(절대 경로·..)가 없는지. 넣을 이름 목록."""
    names = zf.namelist()
    if "postkit-backup.json" not in names:
        raise ValueError("둥이로그(글 도우미) 백업 파일이 아니에요.")
    out = []
    for n in names:
        if n == "postkit-backup.json" or n.endswith("/"):
            continue
        parts = n.replace("\\", "/").split("/")
        if n.startswith(("/", "\\")) or ":" in n or ".." in parts or parts[0] not in KNOWN:
            raise ValueError("백업 파일 안에 이상한 경로가 있어요: %s" % n)
        out.append(n)
    return out


def restore_zip(zip_path, dst):
    """백업을 데이터 폴더에 풀어 넣는다(같은 이름은 덮어쓰고, 백업에 없는 파일은 그대로 둔다). 푼 파일 수."""
    with zipfile.ZipFile(zip_path) as z:
        names = check_zip(z)
        for n in names:
            out = os.path.join(dst, *n.split("/"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as r, open(out, "wb") as w:
                shutil.copyfileobj(r, w)
    return len(names)


def auto_backup(src, backups, keep=7, today=None):
    """하루 한 번 사진 빼고 백업, 최근 keep 개만 남긴다. 만든 파일(이미 있으면 '')."""
    if not has_data(src):
        return ""
    os.makedirs(backups, exist_ok=True)
    day = (today or datetime.now()).strftime("%Y%m%d")
    path = os.path.join(backups, "auto-%s.zip" % day)
    if os.path.exists(path):
        return ""
    make_zip(src, path, photos=False)
    olds = sorted(f for f in os.listdir(backups) if re.match(r"auto-\d{8}\.zip$", f))
    for f in olds[:-keep]:
        os.remove(os.path.join(backups, f))
    return path


# ---------- 성장 기록 ----------

def parse_memo(memo):
    """'항목: 값' 줄 → {항목: 값} (값이 빈 줄은 뺀다)."""
    out = {}
    for line in (memo or "").splitlines():
        k, sep, v = line.partition(":")
        if sep and k.strip() and v.strip() and len(k.strip()) <= 30:       # 틀 항목 이름은 길어야 20자 남짓
            out[k.strip()] = v.strip()
    return out


def month_of(age_text):
    """'생후 5개월 (163일)' → 5 (없으면 None)."""
    m = re.search(r"(\d+)\s*개월", age_text or "")
    return int(m.group(1)) if m else None


def growth_entry(name, memo, photos):
    """육아 글 하나 → 성장 기록 한 줄(개월 수가 없으면 None)."""
    f = parse_memo(memo)
    for k in list(f):                                   # '첫째(애칭):' 처럼 덧붙인 것도
        for base in ("첫째", "둘째"):
            if k.startswith(base) and base not in f:
                f[base] = f[k]
    age = f.get("개월 수", "")
    month = month_of(age)
    if month is None:
        return None
    return {"name": name, "age": age, "month": month, "date": f.get("날짜", ""),
            "scene": f.get("오늘의 장면", ""), "first": f.get("첫째", ""), "second": f.get("둘째", ""),
            "new": f.get("새로 한 것(뒤집기·이유식·첫걸음 등)", "") or f.get("새로 한 것", ""),
            "funny": f.get("웃겼던 순간", ""), "photo": photos[0] if photos else ""}


def compose_memo(entries, names=("첫째", "둘째")):
    """고른 성장 기록들 → 모아서 쓰는 글의 메모."""
    entries = sorted(entries, key=lambda e: (e["month"], e["name"]))
    a, b = (list(names) + ["첫째", "둘째"])[:2]
    head = "주제: %s·%s 생후 %d개월부터 %d개월까지 성장 기록을 돌아보는 글\n" % (a, b, entries[0]["month"], entries[-1]["month"])
    head += "쓰는 법: 개월 순서대로 짧게 짚고, 마지막에 지금 느끼는 마음 한두 문장. 아래 기록에 없는 일은 쓰지 않는다.\n"
    lines = []
    for e in entries:
        bits = [x for x in (e["scene"], e["first"] and "%s: %s" % (a, e["first"]), e["second"] and "%s: %s" % (b, e["second"]),
                            e["new"] and "새로 한 것: " + e["new"], e["funny"] and "웃겼던 순간: " + e["funny"]) if x]
        lines.append("- %s%s — %s" % (e["age"], " (%s)" % e["date"] if e["date"] else "", " / ".join(bits) or "(기록 없음)"))
    return head + "\n" + "\n".join(lines) + "\n\n지금 마음: "
