"""Загрузка PDF, определение формата страниц, рендер превью (PyMuPDF)."""

import pymupdf as fitz  # PyMuPDF

MM_PER_PT = 25.4 / 72.0

# Стандартные форматы (мм, книжная ориентация)
STANDARD_PAPERS = {
    "A6": (105, 148), "A5": (148, 210), "A4": (210, 297), "A3": (297, 420),
    "A2": (420, 594), "A1": (594, 841), "A0": (841, 1189),
    "Letter": (215.9, 279.4), "Legal": (215.9, 355.6), "Tabloid": (279.4, 431.8),
}

TOLERANCE_MM = 2.0


class PdfDocument:
    def __init__(self, path):
        self.path = path
        self.doc = fitz.open(path)
        if self.doc.needs_pass:
            from .i18n import tr
            raise ValueError(tr("PDF защищён паролем"))
        # Пользовательские форматы {имя: (w_mm, h_mm)} — назначает главное окно
        self.extra_papers = {}

    @property
    def page_count(self):
        return self.doc.page_count

    def page_size_mm(self, index):
        """(ширина, высота) страницы в мм с учётом /Rotate."""
        page = self.doc[index]
        rect = page.rect  # rect уже учитывает rotation
        return rect.width * MM_PER_PT, rect.height * MM_PER_PT

    def _known_papers(self):
        known = dict(STANDARD_PAPERS)
        known.update(self.extra_papers)
        return known

    def detect_paper(self, index):
        """Возвращает (метка, w_mm, h_mm). Метка — 'A4' или '100×150 мм' для нестандарта."""
        from .i18n import tr
        w, h = self.page_size_mm(index)
        short, long_ = min(w, h), max(w, h)
        for name, (sw, sh) in self._known_papers().items():
            if abs(short - sw) <= TOLERANCE_MM and abs(long_ - sh) <= TOLERANCE_MM:
                orient = tr("альбомная") if w > h else tr("книжная")
                return f"{name} ({orient})", w, h
        return f"{short:.0f}×{long_:.0f} {tr('мм')}", w, h

    def paper_group_key(self, index):
        """Ключ группировки для авторазбивки: размер без ориентации."""
        from .i18n import tr
        w, h = self.page_size_mm(index)
        short, long_ = min(w, h), max(w, h)
        for name, (sw, sh) in self._known_papers().items():
            if abs(short - sw) <= TOLERANCE_MM and abs(long_ - sh) <= TOLERANCE_MM:
                return name, sw, sh
        return f"{short:.0f}×{long_:.0f} {tr('мм')}", short, long_

    def thumbnail_png(self, index, max_px=180):
        """PNG-байты превью страницы (для QPixmap)."""
        page = self.doc[index]
        rect = page.rect
        zoom = max_px / max(rect.width, rect.height)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")

    def preview_png(self, index, max_px=900):
        page = self.doc[index]
        rect = page.rect
        zoom = max_px / max(rect.width, rect.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")

    def close(self):
        self.doc.close()
