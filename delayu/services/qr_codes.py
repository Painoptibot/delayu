"""QR-коды ссылок на карточки (SVG через reportlab, без отдельного пакета qrcode)."""
from __future__ import annotations

from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm


def qr_svg_for_url(url: str, *, size_mm: float = 32) -> bytes:
    size = size_mm * mm
    drawing = Drawing(size, size)
    drawing.add(
        QrCodeWidget(
            value=url[:800],
            barWidth=size,
            barHeight=size,
            x=0,
            y=0,
        )
    )
    return renderSVG.drawToString(drawing).encode("utf-8")
