"""Saved before/after artifacts; opening this dialog never renders or restores."""

import base64

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QColor
from qgis.PyQt.QtWidgets import QDialog, QGridLayout, QLabel, QPushButton


def pixmap(encoded):
    result = QPixmap()
    if encoded:
        try:
            result.loadFromData(base64.b64decode(encoded, validate=True))
        except (ValueError, TypeError):
            pass
    return result


def sample_icon(preview):
    samples = preview.get("samples", [])
    if not samples:
        return QIcon()
    sheet = QPixmap(76, 30 * len(samples))
    sheet.fill(QColor("#e8e6df"))
    painter = QPainter(sheet)
    painter.setPen(QColor("#45443f"))
    for index, sample in enumerate(samples):
        y = index * 30
        painter.drawPixmap(1, y + 1, pixmap(sample.get("before")))
        painter.drawText(30, y, 16, 30, Qt.AlignmentFlag.AlignCenter, "→")
        painter.drawPixmap(47, y + 1, pixmap(sample.get("after")))
    painter.end()
    return QIcon(sheet)


class PreviewDialog(QDialog):
    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Checkpoint: before / after")
        QGridLayout(self)
        self.set_record(record)

    def set_record(self, record):
        self.record_id = record["id"]
        layout = self.layout()
        while layout.count():
            widget = layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        preview = record.get("preview", {})
        heading = QLabel(record["name"] or record["description"], self)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setWordWrap(True)
        layout.addWidget(heading, 0, 0, 1, 2)
        for col, side in enumerate(("before", "after")):
            layout.addWidget(QLabel(side.title(), self), 1, col)
            label = QLabel(self)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image = pixmap(preview.get("maps", {}).get(side))
            if not image.isNull():
                image.setDevicePixelRatio(1)
                label.setPixmap(image)
                label.setMinimumSize(image.size())
            else:
                label.setText("No previous state" if side == "before" and preview.get("summary") == "Initial checkpoint"
                              else "No saved map preview")
            if image.isNull():
                label.setMinimumSize(400, 260)
            layout.addWidget(label, 2, col)
        note = QLabel(self)
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setWordWrap(True)
        note.setText(preview.get("status", "Preview unavailable: this checkpoint has no saved preview.")
                     + "\n" + preview.get("note", "New checkpoints get previews when Previews is enabled.")
                     + "\n" + preview.get("summary", ""))
        layout.addWidget(note, 3, 0, 1, 2)
        sample_text = [s["label"] for s in preview.get("samples", [])]
        if preview.get("more"):
            sample_text.append(f"+{preview['more']} other symbol changes")
        if sample_text:
            label = QLabel("Symbol samples: " + "; ".join(sample_text), self)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            layout.addWidget(label, 4, 0, 1, 2)
        close = QPushButton("Close", self)
        close.clicked.connect(self.close)
        layout.addWidget(close, 5, 1)
