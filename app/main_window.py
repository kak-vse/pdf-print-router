"""Главное окно PDF Print Router."""

import os
import re
import tempfile

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QAction, QPixmap, QIcon, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QListWidget, QListWidgetItem, QLabel,
    QGroupBox, QFormLayout, QLineEdit, QComboBox, QSpinBox, QPushButton,
    QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem, QFileDialog,
    QMessageBox, QProgressDialog, QDialog, QDialogButtonBox, QHeaderView,
    QPlainTextEdit, QAbstractItemView, QToolBar, QDoubleSpinBox, QCheckBox,
    QInputDialog, QSizePolicy,
)

from . import APP_NAME
from .pdf_document import PdfDocument, STANDARD_PAPERS
from .jobs import (PrintJob, auto_split, build_job_pdf, build_job_pdfs,
                   content_needs_rotation, sheet_landscape)
from .printers import (list_printers, default_printer, find_sumatra, print_job,
                       job_to_manifest_entry, save_manifest,
                       get_printer_papers, printer_properties_dialog)
from .settings import Settings
from .i18n import tr, LANGUAGES, set_language, get_language

ORIENTATION_LABELS = [("auto", "Авто"), ("portrait", "Книжная"),
                      ("landscape", "Альбомная")]
SCALE_LABELS = [("fit", "Вписать"), ("fill", "Заполнить"),
                ("none", "100% (без масштаба)"), ("percent", "Свой процент")]
DUPLEX_LABELS = [("none", "Нет"), ("long", "По длинной стороне"),
                 ("short", "По короткой стороне")]
COLOR_LABELS = [("auto", "Авто"), ("color", "Цвет"), ("mono", "Монохром")]


_PAPER_LABEL_RE = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*[×xX]\s*(\d+(?:[.,]\d+)?)\s*(мм|mm)?$")


def parse_paper_label(text):
    """'297×840 мм' -> (297.0, 840.0) или None, если не разобрать."""
    m = _PAPER_LABEL_RE.match(text.strip())
    if not m:
        return None
    w = float(m.group(1).replace(",", "."))
    h = float(m.group(2).replace(",", "."))
    if w <= 0 or h <= 0:
        return None
    return w, h


def parse_page_ranges(text, total):
    """'1-3,7' -> [0,1,2,6]. Пустая строка -> []."""
    text = text.strip()
    if not text:
        return []
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
            if a < 1 or b > total or a > b:
                raise ValueError(tr("Некорректный диапазон «{part}» (всего страниц: {total})").format(part=part, total=total))
            out.extend(range(a - 1, b))
        else:
            n = int(part)
            if n < 1 or n > total:
                raise ValueError(tr("Некорректная страница {n} (всего: {total})").format(n=n, total=total))
            out.append(n - 1)
    return out


def ranges_string(indices):
    """[0,1,2,6] -> '1-3,7'."""
    if not indices:
        return ""
    indices = sorted(set(indices))
    parts, start, prev = [], indices[0], indices[0]
    for i in indices[1:] + [None]:
        if i is None or i != prev + 1:
            parts.append(str(start + 1) if start == prev else f"{start + 1}-{prev + 1}")
            if i is not None:
                start = i
        if i is not None:
            prev = i
    return ",".join(parts)


class PlacementPreview(QWidget):
    """Превью размещения страницы на листе (как панель «Просмотр» в Foxit).

    Лист всегда рисуется в книжной ориентации (как подаётся бумага);
    при автоповороте альбомное содержимое показывается повёрнутым на 90°.
    Внутри области контента рисуется сама страница PDF.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(230, 300)
        self.doc_w_mm = 210.0
        self.doc_h_mm = 297.0
        self.paper_mm = (210.0, 297.0)   # книжные размеры (короткая, длинная)
        self.landscape_sheet = False     # лист альбомный (плоттер с рулоном)
        self.rotate90 = False            # содержимое повернуто на 90°
        self.scale_mode = "fit"
        self.scale_percent = 100.0
        self.margins_mm = 5.0
        self.auto_center = True
        self.page_pixmap = QPixmap()     # рендер текущей страницы

    def set_state(self, doc_w, doc_h, paper_mm, landscape_sheet, rotate90,
                  scale_mode, scale_percent, margins_mm, auto_center,
                  page_pixmap=None):
        self.doc_w_mm = doc_w
        self.doc_h_mm = doc_h
        self.paper_mm = tuple(paper_mm)
        self.landscape_sheet = landscape_sheet
        self.rotate90 = rotate90
        self.scale_mode = scale_mode
        self.scale_percent = scale_percent
        self.margins_mm = margins_mm
        self.auto_center = auto_center
        if page_pixmap is not None:
            self.page_pixmap = page_pixmap
        self.update()

    def _paper_wh(self):
        sw, sh = self.paper_mm
        if self.landscape_sheet:
            return max(sw, sh), min(sw, sh)
        return min(sw, sh), max(sw, sh)

    def _content_mm(self):
        """(scale, x, y, w, h) размещения контента в мм от левого верха листа."""
        tw, th = self._paper_wh()
        m = self.margins_mm
        aw, ah = tw - 2 * m, th - 2 * m
        w, h = self.doc_w_mm, self.doc_h_mm
        if self.rotate90:
            w, h = h, w
        if self.scale_mode == "fit":
            s = min(aw / w, ah / h)
        elif self.scale_mode == "fill":
            s = max(aw / w, ah / h)
        elif self.scale_mode == "percent":
            s = max(self.scale_percent, 1.0) / 100.0
        else:
            s = 1.0
        cw, ch = w * s, h * s
        if self.auto_center:
            x, y = (tw - cw) / 2, (th - ch) / 2
        else:
            x, y = m, m
        return s, x, y, cw, ch

    def effective_scale(self):
        return self._content_mm()[0]

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#404040"))

        tw, th = self._paper_wh()
        pad = 14
        k = min((self.width() - 2 * pad) / tw, (self.height() - 2 * pad) / th)
        ox = (self.width() - tw * k) / 2
        oy = (self.height() - th * k) / 2

        # лист бумаги
        paper_rect = QRectF(ox, oy, tw * k, th * k)
        p.setPen(QPen(QColor("#888"), 1))
        p.setBrush(QColor("white"))
        p.drawRect(paper_rect)

        # поля (пунктир)
        m = self.margins_mm
        pen = QPen(QColor("#aaaaaa"), 1, Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(ox + m * k, oy + m * k,
                          (tw - 2 * m) * k, (th - 2 * m) * k))

        # контент: сама страница PDF, повёрнутая при необходимости
        _, cx, cy, cw, ch = self._content_mm()
        target = QRectF(ox + cx * k, oy + cy * k, cw * k, ch * k)
        if not self.page_pixmap.isNull():
            p.setClipRect(paper_rect)
            if self.rotate90:
                p.save()
                p.translate(target.center())
                p.rotate(-90)  # совпадает с поворотом при печати (верх влево)
                r = QRectF(-target.height() / 2, -target.width() / 2,
                           target.height(), target.width())
                p.drawPixmap(r, self.page_pixmap,
                             QRectF(self.page_pixmap.rect()))
                p.restore()
            else:
                p.drawPixmap(target, self.page_pixmap,
                             QRectF(self.page_pixmap.rect()))
            p.setClipping(False)
        # рамка области контента
        p.setPen(QPen(QColor("#3366aa"), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(target)
        p.end()


class PrinterMapDialog(QDialog):
    """Привязка форматов бумаги к принтерам — любое число форматов.

    Строки можно добавлять вручную или пакетно подтянуть все форматы
    из драйвера принтера (удобно для плоттера: A1/A2 и прочие разом).
    """

    def __init__(self, parent, paper_names, printers, current_map, all_papers):
        super().__init__(parent)
        self.setWindowTitle(tr("Привязка форматов к принтерам"))
        self.setMinimumSize(680, 460)
        self._printers = printers
        self._all_papers = list(all_papers)
        self._rows = []            # [(paper_combo, printer_combo, row_widget)]
        self.new_papers = {}       # форматы из драйверов → сохранить в пользовательские

        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        for text in (tr("Формат бумаги"), tr("Принтер"), ""):
            lbl = QLabel(f"<b>{text}</b>")
            header.addWidget(lbl, 1 if text else 0)
        layout.addLayout(header)

        self._rows_box = QVBoxLayout()
        layout.addLayout(self._rows_box, 1)

        seen = set()
        for paper in list(current_map) + list(paper_names):
            if paper and paper not in seen:
                seen.add(paper)
                self._add_row(paper, current_map.get(paper, ""))

        btns = QHBoxLayout()
        btn_add = QPushButton(tr("＋ Добавить формат"))
        btn_add.clicked.connect(lambda: self._add_row("", ""))
        btn_drv = QPushButton(tr("Форматы из драйвера принтера…"))
        btn_drv.setToolTip(tr(
            "Добавить все форматы бумаги, которые поддерживает драйвер "
            "выбранного принтера, и сразу привязать их к нему"))
        btn_drv.clicked.connect(self._add_from_driver)
        btns.addWidget(btn_add)
        btns.addWidget(btn_drv)
        btns.addStretch(1)
        layout.addLayout(btns)

        layout.addWidget(QLabel(tr(
            "Используется при авторазбивке: страницы каждого формата уйдут "
            "на привязанный принтер. Форматы из драйвера также сохраняются "
            "в пользовательские и появляются в списке «Бумага».")))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_row(self, paper, printer):
        row = QHBoxLayout()
        pc = QComboBox()
        pc.setEditable(True)
        pc.addItem("")
        pc.addItems(self._all_papers)
        pc.setCurrentText(paper)
        pr = QComboBox()
        pr.setEditable(True)
        pr.addItem("")
        pr.addItems(self._printers)
        pr.setCurrentText(printer)
        btn_x = QPushButton("×")
        btn_x.setFixedWidth(28)
        btn_x.setToolTip(tr("Убрать строку"))
        row.addWidget(pc, 1)
        row.addWidget(pr, 1)
        row.addWidget(btn_x, 0)
        w = QWidget()
        w.setLayout(row)
        self._rows_box.addWidget(w)
        entry = (pc, pr, w)
        self._rows.append(entry)
        btn_x.clicked.connect(lambda: self._del_row(entry))

    def _del_row(self, entry):
        self._rows.remove(entry)
        self._rows_box.removeWidget(entry[2])
        entry[2].deleteLater()

    def _add_from_driver(self):
        if not self._printers:
            QMessageBox.information(self, APP_NAME, tr("Принтеры не найдены"))
            return
        printer, ok = QInputDialog.getItem(
            self, tr("Форматы из драйвера"), tr("Принтер:"), self._printers, 0, False)
        if not ok or not printer:
            return
        papers = get_printer_papers(printer)
        if not papers:
            QMessageBox.information(
                self, APP_NAME,
                tr("Драйвер «{printer}» не вернул список форматов бумаги").format(printer=printer))
            return
        existing = {pc.currentText().strip() for pc, _, _ in self._rows}
        added = 0
        for name, w, h in papers:
            if name in existing:
                continue
            self._add_row(name, printer)
            existing.add(name)
            self.new_papers[name] = (w, h)
            added += 1
        if not added:
            QMessageBox.information(
                self, APP_NAME, tr("Все форматы этого принтера уже в списке"))

    def result_map(self):
        out = {}
        for pc, pr, _ in self._rows:
            paper = pc.currentText().strip()
            printer = pr.currentText().strip()
            if paper and printer:
                out[paper] = printer
        return out


class CustomPapersDialog(QDialog):
    """Редактор пользовательских форматов бумаги (плоттеры, рулоны, этикетки)."""

    def __init__(self, parent, papers):
        super().__init__(parent)
        self.setWindowTitle(tr("Пользовательские форматы бумаги"))
        self.setMinimumSize(480, 320)
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Название"), tr("Ширина, мм"), tr("Высота, мм")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for name, (w, h) in papers.items():
            self._append_row(name, w, h)
        layout.addWidget(self.table)

        add_row = QHBoxLayout()
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText(tr("Например: Рулон 610×914"))
        self.sp_w = QDoubleSpinBox()
        self.sp_w.setRange(10, 5000)
        self.sp_w.setValue(610)
        self.sp_h = QDoubleSpinBox()
        self.sp_h.setRange(10, 10000)
        self.sp_h.setValue(914)
        btn_add = QPushButton(tr("Добавить"))
        btn_add.clicked.connect(self._add)
        btn_del = QPushButton(tr("Удалить выбранный"))
        btn_del.clicked.connect(self._del)
        for w_ in (self.ed_name, self.sp_w, self.sp_h, btn_add, btn_del):
            add_row.addWidget(w_)
        add_row.setStretch(0, 1)
        layout.addLayout(add_row)

        layout.addWidget(QLabel(tr(
            "Форматы сохраняются и участвуют в авторазбивке и привязке "
            "принтеров. Для рулона укажите ширину рулона и типовую длину.")))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _append_row(self, name, w, h):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(name))
        self.table.setItem(r, 1, QTableWidgetItem(f"{w:g}"))
        self.table.setItem(r, 2, QTableWidgetItem(f"{h:g}"))

    def _add(self):
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, APP_NAME, tr("Укажите название формата"))
            return
        self._append_row(name, self.sp_w.value(), self.sp_h.value())
        self.ed_name.clear()

    def _del(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def result_papers(self):
        out = {}
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0).text().strip()
            try:
                w = float(self.table.item(r, 1).text().replace(",", "."))
                h = float(self.table.item(r, 2).text().replace(",", "."))
            except (ValueError, AttributeError):
                continue
            if name and w > 0 and h > 0:
                out[name] = (w, h)
        return out


class PrinterPapersDialog(QDialog):
    """Выбор формата бумаги из списка, поддерживаемого драйвером принтера."""

    def __init__(self, parent, printer_name, papers):
        super().__init__(parent)
        self.setWindowTitle(tr("Форматы бумаги: {printer}").format(printer=printer_name))
        self.setMinimumSize(480, 400)
        layout = QVBoxLayout(self)
        self.selected = None  # (имя, w_mm, h_mm)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Формат (драйвер)"), tr("Ширина, мм"), tr("Высота, мм")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.accept)
        for name, w, h in papers:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem(f"{w:g}"))
            self.table.setItem(r, 2, QTableWidgetItem(f"{h:g}"))
        if papers:
            self.table.selectRow(0)
        layout.addWidget(self.table)

        layout.addWidget(QLabel(tr(
            "Формат будет добавлен в список «Бумага» (и в пользовательские "
            "форматы), драйвер сможет напечатать его без подгонки.")))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, APP_NAME, tr("Выберите формат в списке"))
            return
        self.selected = (self.table.item(row, 0).text(),
                         float(self.table.item(row, 1).text()),
                         float(self.table.item(row, 2).text()))
        super().accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self._doc_basename = None
        self.resize(1280, 800)
        self.settings = Settings()
        set_language(self.settings.get("language") or "ru")
        self.document = None
        self.jobs = []                # list[PrintJob]
        self.printers = list_printers()
        self._build_ui()
        if not self.printers:
            self.statusBar().showMessage(
                tr("Принтеры не найдены (это нормально при запуске не в Windows)"))

    # ---------- построение интерфейса ----------

    def _build_ui(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self._toolbar_actions = []
        for text, slot in (("Открыть PDF…", self.open_pdf),
                           ("Авторазбивка по форматам", self.do_auto_split),
                           ("Привязка принтеров…", self.edit_printer_map),
                           ("Печать всех заданий", self.print_all)):
            action = QAction(tr(text), self)
            action.triggered.connect(slot)
            toolbar.addAction(action)
            self._toolbar_actions.append((action, text))

        # выбор языка интерфейса (справа на панели инструментов)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        self.lbl_language = QLabel(tr("Язык:"))
        toolbar.addWidget(self.lbl_language)
        self.cb_language = QComboBox()
        for lang_key, lang_label in LANGUAGES:
            self.cb_language.addItem(lang_label, lang_key)
        idx = self.cb_language.findData(get_language())
        self.cb_language.setCurrentIndex(max(0, idx))
        self.cb_language.currentIndexChanged.connect(self._on_language_changed)
        toolbar.addWidget(self.cb_language)

        splitter = QSplitter(Qt.Horizontal)

        # Левая панель: миниатюры страниц
        self.page_list = QListWidget()
        self.page_list.setViewMode(QListWidget.IconMode)
        self.page_list.setIconSize(QSize(160, 160))
        self.page_list.setResizeMode(QListWidget.Adjust)
        self.page_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.page_list.setSpacing(8)
        self.page_list.itemSelectionChanged.connect(self.on_selection_changed)
        splitter.addWidget(self.page_list)

        # Правая панель: редактор задания + список заданий
        right = QSplitter(Qt.Vertical)
        right.addWidget(self._build_editor())
        right.addWidget(self._build_jobs_panel())
        right.setSizes([560, 280])

        splitter.addWidget(right)
        splitter.setSizes([430, 850])
        self.setCentralWidget(splitter)

    def _build_editor(self):
        box = QGroupBox(tr("Задание печати"))
        main_row = QHBoxLayout()

        # ---- левая колонка: просмотр размещения (как в Foxit) ----
        left = QVBoxLayout()
        self.lbl_preview_title = QLabel(tr("Просмотр размещения"))
        left.addWidget(self.lbl_preview_title)
        self.lbl_scale = QLabel(tr("Масштаб: —"))
        self.lbl_docsize = QLabel(tr("Документ: —"))
        self.lbl_papersize = QLabel(tr("Бумага: —"))
        for lbl in (self.lbl_scale, self.lbl_docsize, self.lbl_papersize):
            left.addWidget(lbl)
        self.place_preview = PlacementPreview()
        left.addWidget(self.place_preview, 1)
        nav = QHBoxLayout()
        btn_prev = QPushButton("‹")
        btn_prev.setFixedWidth(32)
        btn_prev.clicked.connect(lambda: self._place_nav(-1))
        btn_next = QPushButton("›")
        btn_next.setFixedWidth(32)
        btn_next.clicked.connect(lambda: self._place_nav(1))
        self.lbl_pagenav = QLabel(tr("Страница —"))
        self.lbl_pagenav.setAlignment(Qt.AlignCenter)
        nav.addWidget(btn_prev)
        nav.addWidget(self.lbl_pagenav, 1)
        nav.addWidget(btn_next)
        left.addLayout(nav)
        main_row.addLayout(left, 0)

        # ---- правая колонка: настройки (порядок как в диалоге Foxit) ----
        form = QFormLayout()

        printer_row = QHBoxLayout()
        self.cb_printer = QComboBox()
        self.cb_printer.setEditable(True)
        self.cb_printer.addItems(self.printers)
        dp = default_printer()
        if dp:
            self.cb_printer.setCurrentText(dp)
        btn_props = self.btn_props = QPushButton(tr("Свойства…"))
        btn_props.setToolTip(tr(
            "Открыть диалог свойств драйвера принтера (как в Foxit Reader): "
            "выбранные там формат, ориентация, копии, дуплекс и цвет "
            "подставятся в задание"))
        btn_props.clicked.connect(self.open_printer_properties)
        printer_row.addWidget(self.cb_printer, 1)
        printer_row.addWidget(btn_props)
        form.addRow(tr("Принтер:"), printer_row)

        self.sp_copies = QSpinBox()
        self.sp_copies.setRange(1, 999)
        form.addRow(tr("Копии:"), self.sp_copies)

        auto_row = QHBoxLayout()
        self.cb_autorotate = QCheckBox(tr("Автоповорот"))
        self.cb_autorotate.setChecked(True)
        self.cb_autorotate.setToolTip(tr(
            "Поворачивать альбомные страницы на 90°, чтобы они заняли "
            "весь книжный лист (как «Автоповорот» в Foxit Reader). "
            "Снимите галочку, чтобы вписывать их без поворота"))
        self.cb_autocenter = QCheckBox(tr("Автоцентрирование"))
        self.cb_autocenter.setChecked(True)
        self.cb_autocenter.setToolTip(tr(
            "Центрировать содержимое на листе (иначе — от левого верхнего угла)"))
        auto_row.addWidget(self.cb_autorotate)
        auto_row.addWidget(self.cb_autocenter)
        auto_row.addStretch(1)
        form.addRow("", auto_row)

        paper_row = QHBoxLayout()
        self.cb_paper = QComboBox()
        self.cb_paper.setEditable(True)
        self._refresh_paper_combo()
        self.cb_paper.setCurrentText("A4")
        paper_row.addWidget(self.cb_paper, 1)
        form.addRow(tr("Бумага:"), paper_row)

        paper_btn_row = QHBoxLayout()
        btn_from_printer = self.btn_from_printer = QPushButton(tr("Формат из принтера…"))
        btn_from_printer.setToolTip(tr(
            "Показать форматы бумаги, поддерживаемые драйвером "
            "выбранного принтера, и подставить один из них"))
        btn_from_printer.clicked.connect(self.pick_paper_from_printer)
        btn_custom = self.btn_custom = QPushButton(tr("Свои форматы…"))
        btn_custom.setToolTip(tr(
            "Добавить произвольные форматы бумаги (плоттеры, рулоны, этикетки)"))
        btn_custom.clicked.connect(self.edit_custom_papers)
        paper_btn_row.addWidget(btn_from_printer)
        paper_btn_row.addWidget(btn_custom)
        paper_btn_row.addStretch(1)
        form.addRow("", paper_btn_row)

        self.cb_orient = QComboBox()
        for key, label in ORIENTATION_LABELS:
            self.cb_orient.addItem(tr(label), key)
        form.addRow(tr("Ориентация:"), self.cb_orient)

        self.cb_duplex = QComboBox()
        for key, label in DUPLEX_LABELS:
            self.cb_duplex.addItem(tr(label), key)
        form.addRow(tr("Дуплекс:"), self.cb_duplex)

        self.cb_color = QComboBox()
        for key, label in COLOR_LABELS:
            self.cb_color.addItem(tr(label), key)
        form.addRow(tr("Цвет:"), self.cb_color)

        scale_row = QHBoxLayout()
        self.cb_scale = QComboBox()
        for key, label in SCALE_LABELS:
            self.cb_scale.addItem(tr(label), key)
        self.sp_scale_percent = QDoubleSpinBox()
        self.sp_scale_percent.setRange(10, 400)
        self.sp_scale_percent.setValue(100)
        self.sp_scale_percent.setSuffix(" %")
        self.sp_scale_percent.setEnabled(False)
        self.cb_scale.currentIndexChanged.connect(self._on_scale_changed)
        scale_row.addWidget(self.cb_scale, 1)
        scale_row.addWidget(self.sp_scale_percent)
        form.addRow(tr("Масштаб:"), scale_row)

        self.sp_margin = QDoubleSpinBox()
        self.sp_margin.setRange(0, 50)
        self.sp_margin.setValue(5)
        self.sp_margin.setSuffix(" " + tr("мм"))
        form.addRow(tr("Поля:"), self.sp_margin)

        self.ed_name = QLineEdit()
        form.addRow(tr("Название:"), self.ed_name)

        pages_row = QHBoxLayout()
        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText(tr("например: 1-3,7"))
        btn_from_sel = self.btn_from_sel = QPushButton(tr("← выбранные"))
        btn_from_sel.clicked.connect(self.fill_pages_from_selection)
        pages_row.addWidget(self.ed_pages, 1)
        pages_row.addWidget(btn_from_sel)
        form.addRow(tr("Страницы:"), pages_row)

        btn_row = QHBoxLayout()
        btn_add = self.btn_add_job = QPushButton(tr("Создать задание"))
        btn_add.clicked.connect(self.add_job)
        btn_upd = self.btn_upd_job = QPushButton(tr("Обновить выбранное"))
        btn_upd.clicked.connect(self.update_selected_job)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_upd)
        form.addRow(btn_row)

        main_row.addLayout(form, 1)
        box.setLayout(main_row)
        self.editor_box = box
        self._form = form

        # живое обновление превью при изменении любых настроек
        self._place_idx = 0
        self.cb_paper.currentTextChanged.connect(self._update_placement_preview)
        self.cb_orient.currentIndexChanged.connect(self._update_placement_preview)
        self.cb_scale.currentIndexChanged.connect(self._update_placement_preview)
        self.sp_scale_percent.valueChanged.connect(self._update_placement_preview)
        self.sp_margin.valueChanged.connect(self._update_placement_preview)
        self.cb_autorotate.toggled.connect(self._update_placement_preview)
        self.cb_autocenter.toggled.connect(self._update_placement_preview)
        self.ed_pages.textChanged.connect(self._update_placement_preview)
        return box

    # ---------- просмотр размещения ----------

    def _place_nav(self, delta):
        self._place_idx = max(0, self._place_idx + delta)
        self._update_placement_preview()

    def _update_placement_preview(self):
        if self.document is None:
            return
        try:
            pages = parse_page_ranges(self.ed_pages.text(),
                                      self.document.page_count)
        except ValueError:
            pages = []
        if not pages:
            row = self.page_list.currentRow()
            pages = [row if 0 <= row < self.document.page_count else 0]
        self._place_idx = min(self._place_idx, len(pages) - 1)
        idx = pages[self._place_idx]

        dw, dh = self.document.page_size_mm(idx)
        paper = self.cb_paper.currentText().strip() or "A4"
        sw, sh = self._resolve_paper_mm(paper, pages)

        orient = self.cb_orient.currentData()
        rotate90 = content_needs_rotation(
            orient, self.cb_autorotate.isChecked(), dw, dh)

        # рендер текущей страницы для превью (с кэшем)
        if getattr(self, "_thumb_cache_key", None) != idx:
            pm = QPixmap()
            pm.loadFromData(self.document.preview_png(idx, max_px=500))
            self._thumb_cache = pm
            self._thumb_cache_key = idx

        self.place_preview.set_state(
            dw, dh, (sw, sh), sheet_landscape(orient), rotate90,
            self.cb_scale.currentData(),
            self.sp_scale_percent.value(), self.sp_margin.value(),
            self.cb_autocenter.isChecked(), self._thumb_cache)

        s = self.place_preview.effective_scale()
        tw, th = self.place_preview._paper_wh()
        self.lbl_scale.setText(tr("Масштаб: {v} %").format(
            v=f"{s * 100:.2f}".replace(".", ",")))
        self.lbl_docsize.setText(tr("Документ: {w} x {h} см").format(
            w=f"{dw / 10:.1f}".replace(".", ","),
            h=f"{dh / 10:.1f}".replace(".", ",")))
        self.lbl_papersize.setText(tr("Бумага: {w} x {h} см").format(
            w=f"{tw / 10:.1f}".replace(".", ","),
            h=f"{th / 10:.1f}".replace(".", ",")))
        self.lbl_pagenav.setText(tr("Страница {i} из {n}").format(
            i=self._place_idx + 1, n=len(pages)))

    def _build_jobs_panel(self):
        box = QGroupBox(tr("Задания"))
        layout = QVBoxLayout()

        self.jobs_table = QTableWidget(0, 7)
        self._jobs_header_keys = ["Название", "Страниц", "Принтер", "Бумага",
                                  "Ориентация", "Дуплекс", "Копии"]
        self.jobs_table.setHorizontalHeaderLabels(
            [tr(k) for k in self._jobs_header_keys])
        self.jobs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.jobs_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.jobs_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.jobs_table.itemSelectionChanged.connect(self.on_job_selected)
        layout.addWidget(self.jobs_table)

        btn_row = QHBoxLayout()
        self._job_buttons = []
        for text, slot in (("Печать всех заданий", self.print_all),
                           ("Печать выбранного", self.print_selected),
                           ("Экспорт заданий…", self.export_jobs),
                           ("Удалить задание", self.delete_selected_job),
                           ("Очистить всё", self.clear_jobs)):
            b = QPushButton(tr(text))
            b.clicked.connect(slot)
            btn_row.addWidget(b)
            self._job_buttons.append((b, text))
        layout.addLayout(btn_row)

        box.setLayout(layout)
        self.jobs_box = box
        return box

    # ---------- работа с документом ----------

    def open_pdf(self):
        start_dir = self.settings.get("last_pdf_dir") or ""
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Открыть PDF"), start_dir, tr("PDF-файлы (*.pdf)"))
        if not path:
            return
        try:
            if self.document:
                self.document.close()
            self.document = PdfDocument(path)
            self.document.extra_papers = self.settings.custom_papers
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, tr("Не удалось открыть файл:\n{e}").format(e=e))
            return
        self.settings.set("last_pdf_dir", os.path.dirname(path))
        self._doc_basename = os.path.basename(path)
        self.setWindowTitle(f"{self._doc_basename} — {APP_NAME}")
        self.jobs.clear()
        self.refresh_jobs_table()
        self.populate_pages()
        self._place_idx = 0
        self._update_placement_preview()
        self.statusBar().showMessage(tr("Открыт: {name} — {n} стр.").format(
            name=os.path.basename(path), n=self.document.page_count))

    def populate_pages(self):
        self.page_list.clear()
        total = self.document.page_count
        progress = QProgressDialog(tr("Загрузка миниатюр…"), tr("Отмена"), 0, total, self)
        progress.setWindowModality(Qt.WindowModal)
        for i in range(total):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            png = self.document.thumbnail_png(i)
            pm = QPixmap()
            pm.loadFromData(png)
            label, _, _ = self.document.detect_paper(i)
            item = QListWidgetItem(QIcon(pm), f"{i + 1} · {label}")
            item.setSizeHint(QSize(180, 200))
            self.page_list.addItem(item)
        progress.setValue(total)

    def on_selection_changed(self):
        rows = sorted(i.row() for i in self.page_list.selectedIndexes())
        # Подставляем формат первой выбранной страницы в редактор
        if rows and self.document:
            label, _, _ = self.document.detect_paper(rows[0])
            base = label.split(" ")[0]
            if self.cb_paper.findText(base) >= 0:
                self.cb_paper.setCurrentText(base)
            else:
                self.cb_paper.setCurrentText(label.split(" (")[0])
        self._update_placement_preview()

    def fill_pages_from_selection(self):
        rows = sorted(i.row() for i in self.page_list.selectedIndexes())
        if rows:
            self.ed_pages.setText(ranges_string(rows))
            if not self.ed_name.text().strip():
                label, _, _ = self.document.detect_paper(rows[0])
                self.ed_name.setText(tr("{label}, стр. {ranges}").format(
                    label=label.split(' (')[0], ranges=ranges_string(rows)))

    # ---------- задания ----------

    def _job_from_editor(self):
        if self.document is None:
            raise ValueError(tr("Сначала откройте PDF"))
        pages = parse_page_ranges(self.ed_pages.text(), self.document.page_count)
        if not pages:
            raise ValueError(tr("Укажите страницы (или выделите их слева и нажмите «← выбранные»)"))
        paper = self.cb_paper.currentText().strip() or "A4"
        paper_mm = self._resolve_paper_mm(paper, pages)
        return PrintJob(
            name=self.ed_name.text().strip() or tr("Задание {n}").format(n=len(self.jobs) + 1),
            pages=pages,
            printer=self.cb_printer.currentText().strip(),
            paper=paper,
            paper_mm=paper_mm,
            orientation=self.cb_orient.currentData(),
            scale=self.cb_scale.currentData(),
            scale_percent=self.sp_scale_percent.value(),
            auto_rotate=self.cb_autorotate.isChecked(),
            auto_center=self.cb_autocenter.isChecked(),
            margins_mm=self.sp_margin.value(),
            duplex=self.cb_duplex.currentData(),
            copies=self.sp_copies.value(),
            color=self.cb_color.currentData(),
        )

    def _editor_from_job(self, job):
        self.ed_name.setText(job.name)
        self.ed_pages.setText(ranges_string(job.pages))
        self.cb_printer.setCurrentText(job.printer)
        self.cb_paper.setCurrentText(job.paper)
        self.cb_orient.setCurrentIndex(
            max(0, self.cb_orient.findData(job.orientation)))
        self.cb_scale.setCurrentIndex(max(0, self.cb_scale.findData(job.scale)))
        self.sp_scale_percent.setValue(job.scale_percent)
        self._on_scale_changed()
        self.cb_autorotate.setChecked(job.auto_rotate)
        self.cb_autocenter.setChecked(job.auto_center)
        self.cb_duplex.setCurrentIndex(max(0, self.cb_duplex.findData(job.duplex)))
        self.sp_copies.setValue(job.copies)
        self.sp_margin.setValue(job.margins_mm)
        self.cb_color.setCurrentIndex(max(0, self.cb_color.findData(job.color)))

    def add_job(self):
        try:
            job = self._job_from_editor()
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.jobs.append(job)
        self.refresh_jobs_table()

    def update_selected_job(self):
        row = self.jobs_table.currentRow()
        if row < 0 or row >= len(self.jobs):
            self.statusBar().showMessage(tr("Выберите задание в таблице"))
            return
        try:
            self.jobs[row] = self._job_from_editor()
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.refresh_jobs_table()

    def delete_selected_job(self):
        row = self.jobs_table.currentRow()
        if 0 <= row < len(self.jobs):
            del self.jobs[row]
            self.refresh_jobs_table()

    def clear_jobs(self):
        self.jobs.clear()
        self.refresh_jobs_table()

    def on_job_selected(self):
        row = self.jobs_table.currentRow()
        if 0 <= row < len(self.jobs):
            self._place_idx = 0
            self._editor_from_job(self.jobs[row])

    def refresh_jobs_table(self):
        self.jobs_table.setRowCount(len(self.jobs))
        for r, job in enumerate(self.jobs):
            values = [job.name, str(len(job.pages)),
                      job.printer or tr("(не выбран)"), job.paper,
                      tr(dict(ORIENTATION_LABELS)[job.orientation]),
                      tr(dict(DUPLEX_LABELS)[job.duplex]), str(job.copies)]
            for c, v in enumerate(values):
                self.jobs_table.setItem(r, c, QTableWidgetItem(v))

    def do_auto_split(self):
        if self.document is None:
            QMessageBox.information(self, APP_NAME, tr("Сначала откройте PDF"))
            return
        self.jobs = auto_split(self.document, self.settings.printer_map)
        self.refresh_jobs_table()
        unassigned = [j for j in self.jobs if not j.printer]
        msg = tr("Создано заданий: {n}").format(n=len(self.jobs))
        if unassigned:
            msg += tr("; без принтера: {n} — заполните вручную "
                      "или через «Привязка принтеров…»").format(n=len(unassigned))
        self.statusBar().showMessage(msg)

    def edit_printer_map(self):
        if self.document is not None:
            papers = sorted({self.document.paper_group_key(i)[0]
                             for i in range(self.document.page_count)},
                            key=lambda p: (p not in STANDARD_PAPERS, p))
        else:
            papers = list(self._all_papers())
        dlg = PrinterMapDialog(self, papers, self.printers,
                               self.settings.printer_map, self._all_papers())
        if dlg.exec() == QDialog.Accepted:
            self.settings.set_printer_map(dlg.result_map())
            if dlg.new_papers:
                # форматы из драйверов → в пользовательские, чтобы
                # авторазбивка узнавала их по размеру страниц
                custom = self.settings.custom_papers
                custom.update(dlg.new_papers)
                self.settings.set_custom_papers(custom)
                self._refresh_paper_combo()
                if self.document:
                    self.document.extra_papers = self.settings.custom_papers
            self.statusBar().showMessage(tr("Привязка принтеров сохранена"))

    # ---------- форматы бумаги и свойства принтера ----------

    def _on_scale_changed(self):
        self.sp_scale_percent.setEnabled(
            self.cb_scale.currentData() == "percent")

    def _all_papers(self):
        papers = dict(STANDARD_PAPERS)
        papers.update(self.settings.custom_papers)
        return papers

    def _refresh_paper_combo(self):
        current = self.cb_paper.currentText() if hasattr(self, "cb_paper") else ""
        self.cb_paper.clear()
        self.cb_paper.addItems(list(self._all_papers()))
        if current:
            self.cb_paper.setCurrentText(current)

    def _paper_name_for_size(self, w_mm, h_mm):
        """Имя известного формата по размеру или метка 'W×H мм'."""
        short, long_ = min(w_mm, h_mm), max(w_mm, h_mm)
        for name, (sw, sh) in self._all_papers().items():
            if abs(short - sw) <= 2.0 and abs(long_ - sh) <= 2.0:
                return name
        return f"{short:.0f}×{long_:.0f} {tr('мм')}"

    def _resolve_paper_mm(self, paper, pages):
        """Размер бумаги в мм: стандартные, пользовательские, 'W×H мм',
        иначе размер первой страницы задания."""
        known = self._all_papers()
        if paper in known:
            return tuple(known[paper])
        parsed = parse_paper_label(paper)
        if parsed:
            return parsed
        _, sw, sh = self.document.paper_group_key(pages[0])
        return (sw, sh)

    def open_printer_properties(self):
        printer = self.cb_printer.currentText().strip()
        if not printer:
            QMessageBox.warning(self, APP_NAME, tr("Сначала выберите принтер"))
            return
        props = printer_properties_dialog(int(self.winId()), printer)
        if props is None:
            self.statusBar().showMessage(
                tr("Диалог свойств принтера закрыт без изменений"))
            return
        applied = []
        paper_mm = props.get("paper_mm")
        if paper_mm:
            w, h = paper_mm
            paper = self._paper_name_for_size(w, h)
            if props.get("custom_form") and paper not in self._all_papers():
                # пользовательская форма сервера печати — запомним её
                custom = self.settings.custom_papers
                custom[paper] = (w, h)
                self.settings.set_custom_papers(custom)
                self._refresh_paper_combo()
            self.cb_paper.setCurrentText(paper)
            applied.append(tr("бумага {paper}").format(paper=paper))
        if props.get("orientation"):
            idx = self.cb_orient.findData(props["orientation"])
            if idx >= 0:
                self.cb_orient.setCurrentIndex(idx)
                applied.append(tr("ориентация ")
                               + tr(dict(ORIENTATION_LABELS)[props["orientation"]]).lower())
        if props.get("copies"):
            self.sp_copies.setValue(props["copies"])
            applied.append(tr("копии {n}").format(n=props["copies"]))
        if props.get("duplex"):
            idx = self.cb_duplex.findData(props["duplex"])
            if idx >= 0:
                self.cb_duplex.setCurrentIndex(idx)
                applied.append(tr("дуплекс ")
                               + tr(dict(DUPLEX_LABELS)[props["duplex"]]).lower())
        if props.get("color"):
            idx = self.cb_color.findData(props["color"])
            if idx >= 0:
                self.cb_color.setCurrentIndex(idx)
                applied.append(tr("цвет ")
                               + tr(dict(COLOR_LABELS)[props["color"]]).lower())
        self.statusBar().showMessage(
            tr("Из свойств принтера подставлено: ") + ", ".join(applied)
            if applied else
            tr("Драйвер не вернул настроек — задание не изменено"))

    def pick_paper_from_printer(self):
        printer = self.cb_printer.currentText().strip()
        if not printer:
            QMessageBox.warning(self, APP_NAME, tr("Сначала выберите принтер"))
            return
        papers = get_printer_papers(printer)
        if not papers:
            QMessageBox.information(
                self, APP_NAME,
                tr("Драйвер «{printer}» не вернул список форматов бумаги").format(printer=printer))
            return
        dlg = PrinterPapersDialog(self, printer, papers)
        if dlg.exec() == QDialog.Accepted and dlg.selected:
            name, w, h = dlg.selected
            paper = self._paper_name_for_size(w, h)
            if paper != name:
                # сохраняем под именем драйвера — узнаваемо и участвует
                # в авторазбивке/привязке
                custom = self.settings.custom_papers
                custom[name] = (w, h)
                self.settings.set_custom_papers(custom)
                self._refresh_paper_combo()
                paper = name
            self.cb_paper.setCurrentText(paper)
            self.statusBar().showMessage(
                tr("Выбран формат «{paper}» ({w}×{h} мм)").format(
                    paper=paper, w=f"{w:g}", h=f"{h:g}"))

    def edit_custom_papers(self):
        dlg = CustomPapersDialog(self, self.settings.custom_papers)
        if dlg.exec() == QDialog.Accepted:
            self.settings.set_custom_papers(dlg.result_papers())
            self._refresh_paper_combo()
            if self.document:
                self.document.extra_papers = self.settings.custom_papers
            self.statusBar().showMessage(tr("Пользовательские форматы сохранены"))

    # ---------- печать ----------

    def _check_ready(self, jobs):
        if self.document is None:
            QMessageBox.information(self, APP_NAME, tr("Сначала откройте PDF"))
            return None
        if not jobs:
            QMessageBox.information(self, APP_NAME, tr("Нет заданий для печати"))
            return None
        no_printer = [j.name for j in jobs if not j.printer]
        if no_printer:
            QMessageBox.warning(
                self, APP_NAME,
                tr("Не выбран принтер для заданий:\n") + "\n".join(no_printer))
            return None
        sumatra = find_sumatra(self.settings.get("sumatra_path"))
        if not sumatra:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Найдите SumatraPDF.exe"), r"C:\Program Files",
                "SumatraPDF (SumatraPDF.exe)")
            if not path:
                QMessageBox.warning(
                    self, APP_NAME,
                    tr("Для печати нужен SumatraPDF 3.2+\n"
                       "https://www.sumatrapdfreader.org/download-free-pdf-viewer"))
                return None
            self.settings.set("sumatra_path", path)
            sumatra = path
        return sumatra

    def _run_print(self, jobs):
        sumatra = self._check_ready(jobs)
        if not sumatra:
            return
        log = []
        progress = QProgressDialog(tr("Печать…"), tr("Отмена"), 0, len(jobs), self)
        progress.setWindowModality(Qt.WindowModal)
        tmpdir = tempfile.mkdtemp(prefix="pdfprint_")
        for i, job in enumerate(jobs):
            if progress.wasCanceled():
                log.append(tr("— отменено пользователем"))
                break
            progress.setLabelText(f"{job.name} → {job.printer}")
            progress.setValue(i)
            try:
                parts = build_job_pdfs(self.document.path, job, tmpdir,
                                       f"job{i + 1:02d}")
                for part_path, pages_out, orient in parts:
                    if orient == "landscape":
                        # плоттер/рулон: печать через GDI с явным DEVMODE —
                        # форма бумаги (длинная сторона поперёк рулона)
                        from .gdi_print import print_pdf_gdi
                        sw, sh = job.paper_mm
                        ok, msg = print_pdf_gdi(
                            job.printer, part_path, job,
                            paper_mm=(max(sw, sh), min(sw, sh)),
                            doc_name=job.name)
                    else:
                        ok, msg = print_job(sumatra, part_path, job, orient)
                    log.append(f"[{'OK' if ok else tr('ОШИБКА')}] {job.name}: {msg} "
                               f"({tr('{n} стр.').format(n=pages_out)}, {job.paper}, {orient})")
            except Exception as e:
                log.append(f"[{tr('ОШИБКА')}] {job.name}: {e}")
        progress.setValue(len(jobs))
        self._show_log(tr("Результат печати"), log)

    def _show_log(self, title, lines):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(700, 320)
        v = QVBoxLayout(dlg)
        text = QPlainTextEdit("\n".join(lines))
        text.setReadOnly(True)
        v.addWidget(text)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)
        dlg.exec()

    def print_all(self):
        self._run_print(list(self.jobs))

    def print_selected(self):
        row = self.jobs_table.currentRow()
        if 0 <= row < len(self.jobs):
            self._run_print([self.jobs[row]])

    def export_jobs(self):
        """Экспорт: PDF заданий + print_manifest.json (совместим с print_windows.py)."""
        if self.document is None or not self.jobs:
            QMessageBox.information(self, APP_NAME,
                                    tr("Откройте PDF и создайте задания"))
            return
        folder = QFileDialog.getExistingDirectory(self, tr("Папка для экспорта"))
        if not folder:
            return
        entries, log = [], []
        for i, job in enumerate(self.jobs):
            try:
                safe_name = re.sub(r"[^\w\-.]+", "_", job.name)
                fname = "{:02d}_{}.pdf".format(i + 1, safe_name)
                pdf_path = os.path.join(folder, fname)
                _, pages_out, orient = build_job_pdf(
                    self.document.path, job, pdf_path)
                entry = job_to_manifest_entry(job, orient, fname)
                entry["pages_out"] = pages_out
                entries.append(entry)
                log.append(f"[OK] {fname}")
            except Exception as e:
                log.append(f"[{tr('ОШИБКА')}] {job.name}: {e}")
        save_manifest(os.path.join(folder, "print_manifest.json"),
                      os.path.basename(self.document.path), entries)
        log.append(tr("\nМанифест сохранён: {path}").format(
            path=os.path.join(folder, 'print_manifest.json')))
        self._show_log(tr("Экспорт завершён"), log)

    # ---------- язык интерфейса ----------

    def _on_language_changed(self):
        lang = self.cb_language.currentData()
        self.settings.set("language", lang)
        set_language(lang)
        self.retranslate_ui()

    def _refill_combo(self, combo, labels):
        key = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for k, label in labels:
            combo.addItem(tr(label), k)
        combo.setCurrentIndex(max(0, combo.findData(key)))
        combo.blockSignals(False)

    def retranslate_ui(self):
        """Переводит все видимые строки главного окна на текущий язык."""
        self.setWindowTitle(
            f"{self._doc_basename} — {APP_NAME}"
            if self._doc_basename else APP_NAME)
        for action, key in self._toolbar_actions:
            action.setText(tr(key))
        self.lbl_language.setText(tr("Язык:"))

        self.editor_box.setTitle(tr("Задание печати"))
        self.jobs_box.setTitle(tr("Задания"))
        self.lbl_preview_title.setText(tr("Просмотр размещения"))

        self.btn_props.setText(tr("Свойства…"))
        self.btn_props.setToolTip(tr(
            "Открыть диалог свойств драйвера принтера (как в Foxit Reader): "
            "выбранные там формат, ориентация, копии, дуплекс и цвет "
            "подставятся в задание"))
        self.cb_autorotate.setText(tr("Автоповорот"))
        self.cb_autorotate.setToolTip(tr(
            "Поворачивать альбомные страницы на 90°, чтобы они заняли "
            "весь книжный лист (как «Автоповорот» в Foxit Reader). "
            "Снимите галочку, чтобы вписывать их без поворота"))
        self.cb_autocenter.setText(tr("Автоцентрирование"))
        self.cb_autocenter.setToolTip(tr(
            "Центрировать содержимое на листе (иначе — от левого верхнего угла)"))
        self.btn_from_printer.setText(tr("Формат из принтера…"))
        self.btn_from_printer.setToolTip(tr(
            "Показать форматы бумаги, поддерживаемые драйвером "
            "выбранного принтера, и подставить один из них"))
        self.btn_custom.setText(tr("Свои форматы…"))
        self.btn_custom.setToolTip(tr(
            "Добавить произвольные форматы бумаги (плоттеры, рулоны, этикетки)"))
        self.btn_from_sel.setText(tr("← выбранные"))
        self.btn_add_job.setText(tr("Создать задание"))
        self.btn_upd_job.setText(tr("Обновить выбранное"))
        self.ed_pages.setPlaceholderText(tr("например: 1-3,7"))
        self.sp_margin.setSuffix(" " + tr("мм"))

        for row, key in ((0, "Принтер:"), (1, "Копии:"), (3, "Бумага:"),
                         (5, "Ориентация:"), (6, "Дуплекс:"), (7, "Цвет:"),
                         (8, "Масштаб:"), (9, "Поля:"), (10, "Название:"),
                         (11, "Страницы:")):
            item = self._form.itemAt(row, QFormLayout.LabelRole)
            if item is not None and item.widget() is not None:
                item.widget().setText(tr(key))

        self._refill_combo(self.cb_orient, ORIENTATION_LABELS)
        self._refill_combo(self.cb_duplex, DUPLEX_LABELS)
        self._refill_combo(self.cb_color, COLOR_LABELS)
        self._refill_combo(self.cb_scale, SCALE_LABELS)

        self.jobs_table.setHorizontalHeaderLabels(
            [tr(k) for k in self._jobs_header_keys])
        for b, key in self._job_buttons:
            b.setText(tr(key))
        self.refresh_jobs_table()

        if self.document is not None:
            for i in range(self.page_list.count()):
                item = self.page_list.item(i)
                label, _, _ = self.document.detect_paper(i)
                item.setText(f"{i + 1} · {label}")
            self._update_placement_preview()
        else:
            self.lbl_scale.setText(tr("Масштаб: —"))
            self.lbl_docsize.setText(tr("Документ: —"))
            self.lbl_papersize.setText(tr("Бумага: —"))
            self.lbl_pagenav.setText(tr("Страница —"))

    def closeEvent(self, event):
        if self.document:
            self.document.close()
        super().closeEvent(event)
