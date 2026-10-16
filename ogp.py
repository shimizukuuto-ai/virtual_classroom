import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = os.path.join(os.path.dirname(__file__), "static", "fonts")
BG_DIR = os.path.join(os.path.dirname(__file__), "static", "ogp_bg")

W, H = 1200, 630


def _font(name, size):
    path = os.path.join(FONT_DIR, name)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _bg(name="default.png", w=W, h=H):
    path = os.path.join(BG_DIR, name)
    if os.path.exists(path):
        img = Image.open(path).convert("RGB").resize((w, h))
        return img
    # fallback: dark gradient
    img = Image.new("RGB", (w, h), (30, 41, 59))
    return img


def _wrap(text, font, max_w, draw):
    lines = []
    for para in (text or "").split("\n"):
        line = ""
        for ch in para:
            test = line + ch
            if draw.textlength(test, font=font) > max_w:
                lines.append(line)
                line = ch
            else:
                line = test
        if line:
            lines.append(line)
    return lines


def class_card(cls, teacher_name, student_count):
    """クラスのOGP画像を生成してBytesIOで返す。"""
    img = _bg()
    d = ImageDraw.Draw(img)

    # 半透明黒帯
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, H - 260), (W, H)], fill=(15, 23, 42, 200))
    od.rectangle([(0, 0), (W, 130)], fill=(15, 23, 42, 200))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)

    f_title = _font("NotoSansJP-Bold.ttf", 64)
    f_sub = _font("NotoSansJP-Regular.ttf", 32)
    f_meta = _font("NotoSansJP-Regular.ttf", 26)

    # タイトル（上）
    d.text((60, 40), "Virtual Classroom", font=f_sub, fill=(148, 163, 184))

    # クラス名（下帯）
    title_lines = _wrap(cls["title"], f_title, W - 120, d)[:2]
    y = H - 220
    for line in title_lines:
        d.text((60, y), line, font=f_title, fill=(255, 255, 255))
        y += 78

    # 科目
    d.text((60, y + 6), cls["subject"], font=f_sub, fill=(251, 191, 36))

    # 先生・人数
    d.text((60, H - 60), f"Teacher: {teacher_name}", font=f_meta, fill=(203, 213, 225))
    d.text((W - 260, H - 60), f"{student_count} students", font=f_meta, fill=(203, 213, 225))

    out = BytesIO()
    img.save(out, "PNG", optimize=True)
    out.seek(0)
    return out


def profile_card(user, stats):
    """プロフィールOGP。"""
    img = _bg()
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, 0), (W, H)], fill=(15, 23, 42, 180))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)

    f_name = _font("NotoSansJP-Bold.ttf", 76)
    f_sub = _font("NotoSansJP-Regular.ttf", 30)
    f_stat = _font("NotoSansJP-Bold.ttf", 44)
    f_label = _font("NotoSansJP-Regular.ttf", 22)

    d.text((60, 60), "Virtual Classroom", font=f_sub, fill=(148, 163, 184))
    d.text((60, 130), user["name"], font=f_name, fill=(255, 255, 255))

    if user.get("title"):
        d.text((60, 230), user["title"], font=f_sub, fill=(251, 191, 36))

    # 統計
    stats_data = [
        ("Helpful", stats.get("helpful", 0)),
        ("Answers", stats.get("answers", 0)),
        ("Taught", stats.get("taught", 0)),
        ("Joined", stats.get("joined", 0)),
    ]
    x = 60
    for label, val in stats_data:
        d.text((x, H - 220), str(val), font=f_stat, fill=(255, 255, 255))
        d.text((x, H - 160), label, font=f_label, fill=(148, 163, 184))
        x += 260

    d.text((60, H - 70), "virtual-classroom-sg.onrender.com", font=f_label, fill=(100, 116, 139))

    out = BytesIO()
    img.save(out, "PNG", optimize=True)
    out.seek(0)
    return out