"""
Genera la imagen para compartir la web (static/zyra/og-image.png, 1200×630).

Es la que muestran WhatsApp, Telegram, LinkedIn o X al pegar el enlace de Zyra. Se dibuja con las
fuentes de la propia web y el logo; solo hay que volver a ejecutarla si cambia el diseño:

    python scripts/make_og_image.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

STATIC = Path(__file__).resolve().parent.parent / "static" / "zyra"
SIZE = (1200, 630)
BG, LIME, TEXT, MUTED = "#0A0B09", "#B4F100", "#F4F4F4", "#A3A3A3"


def main():
    """Dibuja el logo, el nombre y el lema sobre el fondo oscuro de Zyra."""
    image = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 14, SIZE[1]), fill=LIME)
    logo = Image.open(STATIC / "logo.png").convert("RGBA").resize((220, 220))
    image.paste(logo, (90, 130), logo)
    name = ImageFont.truetype(str(STATIC / "fonts" / "Syncopate-BoldItalic.ttf"), 92)
    title = ImageFont.truetype(str(STATIC / "fonts" / "Archivo-ExtraBold.ttf"), 50)
    text = ImageFont.truetype(str(STATIC / "fonts" / "Archivo-Regular.ttf"), 34)
    draw.text((350, 130), "ZYRA", font=name, fill=LIME)
    draw.text((350, 262), "App para gestionar", font=title, fill=TEXT)
    draw.text((350, 322), "equipos de pádel", font=title, fill=TEXT)
    draw.text((90, 440), "Convocatorias · parejas · resultados · estadísticas", font=text, fill=TEXT)
    draw.text((90, 495), "Gratis para capitanes y clubes", font=text, fill=MUTED)
    image.save(STATIC / "og-image.png", optimize=True)


if __name__ == "__main__":
    main()
