# -*- coding: utf-8 -*-
"""글 도우미 빌드 — 윈도우는 PostKit.exe 한 파일, 맥은 PostKit.app.

    python build.py      (PyInstaller·Pillow 가 깔린 파이썬이면 된다 — pip install pyinstaller pillow)

윈도우: dist\\PostKit.exe. 더블클릭 → 앱 창(Edge --app)으로 열린다. 데이터는 %APPDATA%\\PostKit.
맥:     dist/PostKit.app (+ 배포용 dist/PostKit-mac.zip). 앱 창은 Chrome·Edge·Brave --app, 없으면 기본 브라우저.
        데이터는 ~/Library/Application Support/PostKit. 서명·공증이 없어 처음 한 번은 「열기」 허용이 필요하다(README).
        빌드한 맥의 CPU 용이다(Apple Silicon 에서 빌드하면 arm64 전용).
창을 닫으면 잠시 뒤 스스로 끝난다. AI(claude 등)는 그 PC 에 깔려 로그인돼 있어야 한다.
빌드 결과(dist·build)는 git 에 넣지 않는다.
"""
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
DIST = os.path.join(HERE, "dist")
ICO = os.path.join(HERE, "app.ico")                       # 없으면 make_icon.py 로 만든다
IS_MAC = sys.platform == "darwin"
BUNDLE_ID = "app.postkit.PostKit"


def mac_icon(tmp):
    """app.ico 의 가장 큰 그림(256) → PostKit.icns(Pillow). 안 되면 icon.png 를 그대로 넘긴다(PyInstaller 가 바꾼다)."""
    out = os.path.join(tmp, "PostKit.icns")
    try:
        from PIL import Image
        with Image.open(ICO) as im:
            im.size = max(im.info.get("sizes") or [im.size])
            im.load()
            im.convert("RGBA").resize((512, 512), Image.LANCZOS).save(out)
        return out
    except Exception as e:      # noqa: BLE001 — 아이콘이 없어도 빌드는 된다
        print("icns 만들기 실패, icon.png 로:", e)
        return os.path.join(HERE, "icon.png")


def finish_mac(app):
    """Info.plist 를 다듬고(이름·한국어·Dock 아이콘 없이) 다시 임시 서명한 뒤 zip 으로 묶는다."""
    plist = os.path.join(app, "Contents", "Info.plist")
    with open(plist, "rb") as f:
        info = plistlib.load(f)
    info.update({"CFBundleDisplayName": "글 도우미", "CFBundleName": "PostKit",
                 "CFBundleDevelopmentRegion": "ko", "NSHighResolutionCapable": True,
                 # 화면은 브라우저 창이라 이 앱이 Dock 에 뜨면 눌러도 아무 일 없는 아이콘만 남는다 — 뒤에서만 돈다
                 "LSUIElement": True})
    with open(plist, "wb") as f:
        plistlib.dump(info, f)
    # Info.plist 를 고치면 PyInstaller 가 해 둔 임시(ad-hoc) 서명이 깨진다 — Apple Silicon 은 서명이 없으면 안 뜬다
    subprocess.check_call(["codesign", "--force", "--deep", "--sign", "-", app])
    z = os.path.join(DIST, "PostKit-mac.zip")
    if os.path.exists(z):
        os.remove(z)
    subprocess.check_call(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, z])     # 심볼릭 링크·서명 그대로
    return z


def main():
    if not (os.path.isfile(ICO) and os.path.isfile(os.path.join(HERE, "icon.png"))):
        subprocess.check_call([sys.executable, os.path.join(HERE, "make_icon.py")], cwd=HERE)
    tmp = tempfile.mkdtemp(prefix="postkit-build-")
    if IS_MAC:      # 맥은 한 파일(--onefile)과 .app 조합을 PyInstaller 가 말린다 — 폴더형 .app
        look = ["--windowed", "--onedir", "--icon", mac_icon(tmp), "--osx-bundle-identifier", BUNDLE_ID]
    else:
        look = ["--onefile", "--noconsole", "--icon", ICO]
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", *look,
           "--name", "PostKit",
           "--add-data", os.path.join(HERE, "ui.html") + os.pathsep + ".",
           "--add-data", os.path.join(HERE, "platforms.json") + os.pathsep + ".",
           "--add-data", os.path.join(HERE, "templates.json") + os.pathsep + ".",
           "--add-data", os.path.join(HERE, "icon.png") + os.pathsep + ".",            # 창·화면 아이콘
           "--hidden-import", "PIL.Image",                                              # 사진 줄이기(gen.process_photo 가 함수 안에서 불러온다)
           "--hidden-import", "qr",                                                     # 폰에서 쓰기 QR(app.py 가 함수 안에서 불러온다)
           "--add-data", os.path.join(HERE, "prompts") + os.pathsep + "prompts",
           "--distpath", DIST, "--workpath", WORK, "--specpath", WORK,
           os.path.join(HERE, "app.py")]
    print(" ".join(cmd))
    try:
        subprocess.check_call(cmd, cwd=HERE)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(WORK, ignore_errors=True)
    if IS_MAC:
        app = os.path.join(DIST, "PostKit.app")
        z = finish_mac(app)
        shutil.rmtree(os.path.join(DIST, "PostKit"), ignore_errors=True)       # .app 옆에 남는 폴더형 결과(같은 내용)
        print("만들었습니다:", app, "·", z)
        return
    print("만들었습니다:", os.path.join(DIST, "PostKit.exe"))


if __name__ == "__main__":
    main()
