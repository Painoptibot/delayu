"""QR для топливного пропуска (SVG)."""
from __future__ import annotations

from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm

from delayu.models_fuel import FuelPermit
from delayu.services.fuel import build_qr_payload


def qr_svg_for_permit(permit: FuelPermit, *, size_mm: float = 40) -> bytes:
    payload = permit.qr_payload or build_qr_payload(permit)
    size = size_mm * mm
    drawing = Drawing(size, size)
    drawing.add(
        QrCodeWidget(
            value=payload[:1200],
            barWidth=size,
            barHeight=size,
            x=0,
            y=0,
        )
    )
    return renderSVG.drawToString(drawing).encode("utf-8")
