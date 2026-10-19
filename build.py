# -*- coding: utf-8 -*-
"""PostKit.exe 만들기 — 글 도우미 한 파일 exe.

    python build.py      (PyInstaller 가 깔린 파이썬이면 된다 — pip install pyinstaller)

결과: dist\\PostKit.exe. 더블클릭 → 앱 창(Edge --app)으로 열린다. 창을 닫으면 잠시 뒤 스스로 끝난다.
데이터는 %APPDATA%\\PostKit. claude(Claude Code)는 이 PC 에 깔려 로그인돼 있어야 한다.
빌드 결과(dist·build)는 git 에 넣지 않는다.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build")
ICO = os.path.join(HERE, "app.ico")                       # 있으면 아이콘으로


def main():
    look = ["--onefile", "--noconsole"] + (["--icon", ICO] if os.path.isfile(ICO) else [])
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", *look,
           "--name", "PostKit",
           "--add-data", os.path.join(HERE, "ui.html") + os.pathsep + ".",
           "--add-data", os.path.join(HERE, "platforms.json") + os.pathsep + ".",
           "--add-data", os.path.join(HERE, "prompts") + os.pathsep + "prompts",
           "--distpath", os.path.join(HERE, "dist"), "--workpath", WORK, "--specpath", WORK,
           os.path.join(HERE, "app.py")]
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=HERE)
    shutil.rmtree(WORK, ignore_errors=True)
    print("만들었습니다:", os.path.join(HERE, "dist", "PostKit.exe"))


if __name__ == "__main__":
    main()
