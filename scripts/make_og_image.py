"""
Genera la imagen para compartir la web (static/zyra/og-image-v2.png, 1200×630).

Es la que muestran WhatsApp, Telegram, LinkedIn o X al pegar el enlace de Zyra: el logo de la
aplicación centrado sobre el fondo oscuro de la web. Solo hay que volver a ejecutarla si cambia el
logo; al cambiar el diseño, usa un nombre de archivo nuevo (y actualízalo en `base.html` y
`core/seo.py`) para que WhatsApp y Facebook no sirvan la versión guardada en su caché:

    python scripts/make_og_image.py
"""
from pathlib import Path

from PIL import Image

STATIC = Path(__file__).resolve().parent.parent / "static" / "zyra"
SIZE = (1200, 630)
BG = "#0A0B09"
LOGO_HEIGHT = 470


def main():
    """Pega el logo centrado sobre el fondo oscuro de Zyra."""
    image = Image.new("RGB", SIZE, BG)
    logo = Image.open(STATIC / "logo.png").convert("RGBA")
    logo = logo.crop(logo.getbbox())
    ratio = LOGO_HEIGHT / logo.height
    logo = logo.resize((round(logo.width * ratio), LOGO_HEIGHT), Image.LANCZOS)
    image.paste(logo, ((SIZE[0] - logo.width) // 2, (SIZE[1] - logo.height) // 2), logo)
    image.save(STATIC / "og-image-v2.png", optimize=True)


if __name__ == "__main__":
    main()
