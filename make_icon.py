# -*- coding: utf-8 -*-
"""앱 아이콘 app.ico 만들기 — 라벤더→핑크 둥근 네모에 흰 '글'. build.py 가 app.ico 가 없으면 부른다.

    python make_icon.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TOP, BOTTOM = (138, 114, 238), (239, 143, 191)          # --accent · --accent2


def font(size):
    for f in ("malgunbd.ttf", "malgun.ttf", "AppleSDGothicNeo.ttc", "NanumGothicBold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw(n=256):
    big = n * 4                                          # 크게 그려 줄여서 가장자리를 매끄럽게
    grad = Image.new("RGB", (big, big))
    gd = ImageDraw.Draw(grad)
    for y in range(big):
        t = y / (big - 1)
        gd.line([(0, y), (big, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, big - 1, big - 1], radius=big // 4.2, fill=255)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    f = font(int(big * 0.56))
    box = d.textbbox((0, 0), "글", font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((big - w) / 2 - box[0], (big - h) / 2 - box[1] - big * 0.02), "글", font=f, fill=(255, 255, 255))
    # 오른쪽 아래 작은 연필 끝(반짝) — 노란 점
    r = big * 0.075
    cx, cy = big * 0.78, big * 0.78
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 226, 120))
    return img.resize((n, n), Image.LANCZOS)


def main():
    img = draw(256)
    img.save(os.path.join(HERE, "app.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.resize((64, 64), Image.LANCZOS).save(os.path.join(HERE, "icon.png"))
    print("만들었습니다: app.ico · icon.png")


if __name__ == "__main__":
    main()
