"""
build/make_icon.py
==================
Genera el archivo icon.ico con el estilo NTT DATA (azul corporativo).

Uso:
    python build/make_icon.py

Requiere: Pillow  (pip install pillow)

Produce:
    build/icon.ico   — icono multisize (16, 32, 48, 64, 128, 256 px)
"""

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Instala Pillow primero:  pip install pillow")

# ── Colores NTT DATA ─────────────────────────────────────────────────
BG_COLOR     = (0,  114, 188)   # Future Blue
ACCENT_COLOR = (63, 180, 234)   # Turquoise
TEXT_COLOR   = (255, 255, 255)  # White
DARK_COLOR   = (20,  26,  36)   # Smart Navy

SIZES = [16, 32, 48, 64, 128, 256]
OUT_PATH = Path(__file__).parent / "icon.ico"


def _make_frame(size: int) -> Image.Image:
    """Dibuja el ícono en el tamaño indicado."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = max(1, size // 16)

    # Fondo redondeado (círculo inscrito)
    draw.ellipse([pad, pad, size - pad, size - pad], fill=BG_COLOR)

    # Acento — arco superior derecho
    arc_pad = size // 5
    draw.arc(
        [arc_pad, arc_pad, size - arc_pad, size - arc_pad],
        start=-60, end=60,
        fill=ACCENT_COLOR,
        width=max(1, size // 12),
    )

    # Letra "N" centrada (solo en tamaños >= 32)
    if size >= 32:
        font_size = max(10, int(size * 0.45))
        font = None
        try:
            # Intentar cargar una fuente del sistema
            from PIL import ImageFont
            for candidate in [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/calibrib.ttf",
            ]:
                if Path(candidate).exists():
                    font = ImageFont.truetype(candidate, font_size)
                    break
        except Exception:
            pass

        text = "N"
        if font:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = (size - tw) // 2 - bbox[0]
            y = (size - th) // 2 - bbox[1]
            draw.text((x, y), text, fill=TEXT_COLOR, font=font)
        else:
            # Fallback sin fuente — dibujar "N" manualmente con líneas
            m = size // 2
            t = max(2, size // 10)
            p = size // 4
            # Left vertical
            draw.line([(p, p), (p, size - p)], fill=TEXT_COLOR, width=t)
            # Right vertical
            draw.line([(size - p, p), (size - p, size - p)], fill=TEXT_COLOR, width=t)
            # Diagonal
            draw.line([(p, p), (size - p, size - p)], fill=TEXT_COLOR, width=t)

    return img


def build_ico():
    frames = []
    for s in SIZES:
        frames.append(_make_frame(s))

    # Guardar como ICO multisize
    largest = frames[-1]
    largest.save(
        str(OUT_PATH),
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=frames[:-1],
    )
    print(f"[OK] Icon saved: {OUT_PATH}  ({len(frames)} sizes: {SIZES})")


if __name__ == "__main__":
    build_ico()
