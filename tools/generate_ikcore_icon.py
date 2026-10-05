from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "IkCore.ico")
OUT.parent.mkdir(parents=True, exist_ok=True)

SIZE = 1024
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

margin = 42
d.rounded_rectangle(
    (margin, margin, SIZE - margin, SIZE - margin),
    radius=150,
    fill=(250, 250, 250, 255),
    outline=(222, 222, 222, 255),
    width=5,
)

def load_font(candidates, size):
    for p in candidates:
        try:
            return ImageFont.truetype(p, size=size)
        except OSError:
            pass
    return ImageFont.truetype("DejaVuSans.ttf", size=size)

top_font = load_font([
    r"C:\Windows\Fonts\seguisb.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
], 360)

bottom_font = load_font([
    r"C:\Windows\Fonts\seguili.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
], 245)

def centered(text, y, font):
    box = d.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    d.text(((SIZE - width) / 2, y), text, font=font, fill=(18, 18, 18, 255))

centered("Ik", 115, top_font)
centered("Core", 560, bottom_font)

img.save(OUT, format="ICO", sizes=[
    (16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)
])
img.resize((512, 512), Image.Resampling.LANCZOS).save(OUT.with_suffix(".png"))

print(f"Ik Core icon written to {OUT}")
