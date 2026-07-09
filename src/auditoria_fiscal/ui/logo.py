"""Logomarca JB Fraga Contabilidade embutida (JPEG em base64).

Embutida no codigo para o PyInstaller nao precisar de --add-data e o icone
funcionar igual no .py e no .exe. Para trocar a logo, regenere o base64.
"""

from __future__ import annotations

import base64

from PySide6.QtGui import QIcon, QPixmap

_LOGO_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/7QCEUGhvdG9zaG9wIDMuMAA4QklNBAQAAAAAAGgcAigAYkZC"
    "TUQwYTAwMGFiODAxMDAwMGYyMDIwMDAwMzgwNDAwMDA2YzA0MDAwMGZkMDQwMDAwNTYwNzAwMDAw"
    "ODBhMDAwMDYyMGEwMDAwYzMwYTAwMDA1YTBiMDAwMDY4MGUwMDAwAP/bAIQABQYGCwgLCwsLCw0L"
    "CwsNDg4NDQ4ODw0ODg4NDxAQEBEREBAQEA8TEhMPEBETFBQTERMWFhYTFhUVFhkWGRYWEgEFBQUK"
    "BwoICQkICwgKCAsKCgkJCgoMCQoJCgkMDQsKCwsKCw0MCwsICwsMDAwNDQwMDQoLCg0MDQ0MExQT"
    "ExOc/8IAEQgAlgCWAwEiAAIRAQMRAf/EAIMAAQACAwEBAAAAAAAAAAAAAAAFBwEDBgQCEAABAgMD"
    "BwcJBgcBAAAAAAABAgMABBESITEQEzJBUWFxBSIwQoGR0RQgI0BSobHB8DRgcoKSsiQzQ1BzwvHh"
    "EQEAAQMCBQIGAwEAAAAAAAABEQAhMUFRYXGBkaEQwSAwQLHR8FDh8WD/2gAMAwEAAgADAAAAAblA"
    "AAAY1/LaPoAAApq5aaLlAAA5+eivP9ymI70/LRBa+m1bfbnXs93nDIBTVy00XKAACFmdWvV9Yebf"
    "5fqPm+Nk8/frlsZ9mkPrACmrlpouUAAGiG6Bq+vP6GhjTz3WZ+frI3/AACmrlpouUhyYcrK5SqNi"
    "DqUZAsdihtOMz6Bng5qTJJHe02QmfZnHupq5aaxm5eL7Ti84i+24nu8uZ8Jl2/KdZyeHTcL6ZDKN"
    "mJWvCe7riu1+XxHc1MnK2VWlhZemmrlpr5zcvEdvpy5uZ9erGI7zTfxnPtgJjThu4DuvXnGiDZPv"
    "2YlTkuq+2M6oLogpq5aaLlAAAAAAAAApq5aaLlAAAAAAAAApq5aaLlU0LlU0LlU0LlU0LlU0LlU0"
    "LlU0LlU0LlU0LlpoP//aAAgBAQABBQL1y0PUecyQawpNqGFQ66p9fSk0jP24bhTtINswyyGglVrp"
    "XxbVHWvtS2JNIlb09IUVLjliE1hTdYNQvyZS+mcXYDCC4TjDzIdDLq2VeoFEAU9aTNpUvJOzPkzb"
    "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"
)


def pixmap(largura: int = 0) -> QPixmap:
    """QPixmap da logo; com largura > 0, redimensiona suavemente."""
    pm = QPixmap()
    pm.loadFromData(base64.b64decode(_LOGO_JPEG_B64), "JPEG")
    if largura and not pm.isNull():
        from PySide6.QtCore import Qt
        pm = pm.scaledToWidth(largura, Qt.SmoothTransformation)
    return pm


def icone() -> QIcon:
    return QIcon(pixmap())
