"""Print da tela para a Ceci olhar (só quando você aperta o atalho; nada vai para o disco)."""
import base64

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QCursor, QGuiApplication

MAX_W = 1600   # largura do print que vai para a IA (dá pra ler texto sem pesar)
QUALITY = 75


def grab():
    """(JPEG em base64, geometria da tela capturada) da tela onde está o mouse."""
    scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    img = scr.grabWindow(0).toImage()
    if img.width() > MAX_W:
        img = img.scaledToWidth(MAX_W, Qt.SmoothTransformation)
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPG", QUALITY)
    return base64.b64encode(bytes(data)).decode(), scr.geometry()
