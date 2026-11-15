# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 背景：深蓝圆角方块 + 竖向渐变
bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
bd = ImageDraw.Draw(bg)
top = (13, 30, 50)
bot = (18, 62, 96)
for y in range(S):
    t = y / (S - 1)
    c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,)
    bd.line([(0, y), (S, y)], fill=c)
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
img.paste(bg, (0, 0), mask)

d = ImageDraw.Draw(img)
cyan = (79, 195, 247, 255)
ice = (170, 232, 255, 255)

def arrow(y, x0, x1, color, up=True):
    w = int(S * 0.075)
    d.line([(x0, y), (x1, y)], fill=color, width=w)
    h = int(S * 0.11)
    if up:
        d.polygon([(x1 + h * 0.6, y), (x1 - h * 0.4, y - h), (x1 - h * 0.4, y + h)], fill=color)
    else:
        d.polygon([(x0 - h * 0.6, y), (x0 + h * 0.4, y - h), (x0 + h * 0.4, y + h)], fill=color)

arrow(int(S * 0.395), int(S * 0.22), int(S * 0.66), cyan, up=True)
arrow(int(S * 0.605), int(S * 0.78), int(S * 0.34), ice, up=False)

# 两端的小圆点，像两个设备
r = int(S * 0.035)
d.ellipse([int(S * 0.20) - r, int(S * 0.605) - r, int(S * 0.20) + r, int(S * 0.605) + r], fill=cyan)
d.ellipse([int(S * 0.80) - r, int(S * 0.395) - r, int(S * 0.80) + r, int(S * 0.395) + r], fill=ice)

img.resize((256, 256), Image.LANCZOS).save("lanbeam.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.resize((256, 256), Image.LANCZOS).save("lanbeam.png")
print("icon ok")
