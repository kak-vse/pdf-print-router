#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless smoke-тест GUI (QT_QPA_PLATFORM=offscreen) и ядра."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.main_window import MainWindow, parse_page_ranges, ranges_string  # noqa: E402
from app.pdf_document import PdfDocument  # noqa: E402

TEST_PDF = sys.argv[1] if len(sys.argv) > 1 else None

# --- парсеры диапазонов ---
assert parse_page_ranges("1-3,7", 10) == [0, 1, 2, 6]
assert parse_page_ranges("5", 10) == [4]
assert parse_page_ranges("", 10) == []
assert ranges_string([0, 1, 2, 6]) == "1-3,7"
assert ranges_string([4]) == "5"
try:
    parse_page_ranges("3-1", 10)
    raise SystemExit("ожидали ValueError для '3-1'")
except ValueError:
    pass
try:
    parse_page_ranges("99", 10)
    raise SystemExit("ожидали ValueError для '99'")
except ValueError:
    pass
print("[ok] парсеры диапазонов")

# --- парсер меток форматов '297×840 мм' ---
from app.main_window import parse_paper_label  # noqa: E402

assert parse_paper_label("297×840 мм") == (297.0, 840.0)
assert parse_paper_label("210x297") == (210.0, 297.0)
assert parse_paper_label("100,5×150 мм") == (100.5, 150.0)
assert parse_paper_label("A4") is None
assert parse_paper_label("текст") is None
print("[ok] парсер меток форматов")

# --- ручной масштаб в процентах ---
from app.jobs import _scaled_transform, MM_TO_PT  # noqa: E402
from pypdf import PdfWriter  # noqa: E402

writer = PdfWriter()
page = writer.add_blank_page(width=210 * MM_TO_PT, height=297 * MM_TO_PT)  # A4
t = _scaled_transform(page, 210 * MM_TO_PT, 297 * MM_TO_PT, "percent", 0, 50.0)
# страница 50% должна занять четверть площади: масштаб 0.5 в матрице
assert abs(t.ctm[0] - 0.5) < 1e-6, t.ctm
t = _scaled_transform(page, 210 * MM_TO_PT, 297 * MM_TO_PT, "percent", 0, 150.0)
assert abs(t.ctm[0] - 1.5) < 1e-6, t.ctm
print("[ok] масштаб в процентах (50% и 150%)")

# --- пользовательские форматы в определении формата страниц ---
from app.pdf_document import STANDARD_PAPERS  # noqa: E402

papers = dict(STANDARD_PAPERS)
papers["Рулон 610"] = (610.0, 914.0)
assert "Рулон 610" in papers
print("[ok] пользовательские форматы")

# --- автоповорот: альбомная страница поворачивается на книжном листе ---
import tempfile  # noqa: E402
from app.jobs import PrintJob, build_job_pdf, build_job_pdfs, content_needs_rotation  # noqa: E402

assert content_needs_rotation("auto", True, 420, 297) is True
assert content_needs_rotation("auto", False, 420, 297) is False
assert content_needs_rotation("portrait", True, 420, 297) is True
assert content_needs_rotation("portrait", True, 210, 297) is False
assert content_needs_rotation("landscape", True, 210, 297) is True
assert content_needs_rotation("landscape", True, 420, 297) is False
assert content_needs_rotation("landscape", False, 210, 297) is False

_tmp = tempfile.mkdtemp()
_w = PdfWriter()
_w.add_blank_page(width=210 * MM_TO_PT, height=297 * MM_TO_PT)   # книжная
_p2 = _w.add_blank_page(width=210 * MM_TO_PT, height=297 * MM_TO_PT)
_p2.rotation = 90                                                 # альбомная
_src = os.path.join(_tmp, "mixed_orient.pdf")
with open(_src, "wb") as _f:
    _w.write(_f)

job = PrintJob(name="t", pages=[0, 1], paper="A4",
               paper_mm=(210.0, 297.0), orientation="auto")
parts = build_job_pdfs(_src, job, _tmp, "t")
assert len(parts) == 1 and parts[0][2] == "portrait", parts

# обе страницы — на книжном листе; у повёрнутой страницы контент стоит вертикально
import pymupdf  # noqa: E402
_out = pymupdf.open(parts[0][0])
assert _out.page_count == 2
for _p in _out:
    assert _p.rect.width < _p.rect.height        # лист всегда книжный
print("[ok] автоповорот: лист книжный, альбомный контент поворачивается")

# --- альбомный лист (плоттер): книжный контент поворачивается на 90° ---
job_ls = PrintJob(name="t", pages=[0], paper="A4", paper_mm=(210.0, 297.0),
                  orientation="landscape")
parts_ls = build_job_pdfs(_src, job_ls, _tmp, "tls")
assert parts_ls[0][2] == "landscape"
_out_ls = pymupdf.open(parts_ls[0][0])
_p = _out_ls[0]
assert _p.rect.width > _p.rect.height            # лист альбомный
# книжная A4 (595x842pt) после поворота: 842x595 — займёт весь альбомный лист
assert abs(_p.rect.width - 297 * MM_TO_PT) < 1 and abs(_p.rect.height - 210 * MM_TO_PT) < 1
print("[ok] альбомный лист: книжный контент повёрнут, габариты точные")

# поворот на 90° в трансформации: матрица поворота на 270° + масштаб 1.0
_t = _scaled_transform(PdfWriter().add_blank_page(
    width=297 * MM_TO_PT, height=210 * MM_TO_PT),   # альбомная A4
    210 * MM_TO_PT, 297 * MM_TO_PT, "fit", 0, rotate90=True)
# после поворота габариты 210×297 мм = вписывается в книжный A4 со scale 1.0
assert abs(_t.ctm[0]) < 1e-6, _t.ctm          # cos(270°)=0 → контент повёрнут
assert abs(_t.ctm[1] + 1.0) < 1e-6, _t.ctm    # sin(270°)=-1, масштаб ровно 1.0
print("[ok] поворот контента в трансформации")

# --- строка настроек Sumatra: запрет авто-поворота ---
from app.printers import sumatra_settings_string  # noqa: E402
_settings = sumatra_settings_string(job, "portrait")
assert "disable-auto-rotation" in _settings
assert "portrait" in _settings
print("[ok] настройки Sumatra (disable-auto-rotation)")

# --- автоцентрирование выключено: контент прижат к углу с полем ---
from app.jobs import _scaled_transform  # noqa: E402
page = PdfWriter().add_blank_page(width=100, height=100)
t = _scaled_transform(page, 200, 200, "none", 10, center=False)
assert abs(t.ctm[4] - 10) < 1e-6, t.ctm          # слева поле 10pt
assert abs(t.ctm[5] - (200 - 10 - 100)) < 1e-6   # сверху поле 10pt
print("[ok] автоцентрирование (вкл/выкл)")

if not TEST_PDF:
    print("[skip] PDF для GUI-теста не передан")
    sys.exit(0)

app = QApplication([])
win = MainWindow()
win.show()

win.document = PdfDocument(TEST_PDF)
win.jobs.clear()
win.refresh_jobs_table()
win.populate_pages()
assert win.page_list.count() == win.document.page_count
print(f"[ok] миниатюр загружено: {win.page_list.count()}")

win.do_auto_split()
assert win.jobs_table.rowCount() == len(win.jobs) > 0
print(f"[ok] авторазбивка: {len(win.jobs)} заданий "
      f"({', '.join(j.paper for j in win.jobs)})")

# выделение страниц -> редактор -> новое задание
win.page_list.selectAll()
win.fill_pages_from_selection()
assert win.ed_pages.text() == f"1-{win.document.page_count}"
jobs_before = len(win.jobs)
win.ed_name.setText("тестовое задание")
win.add_job()
assert len(win.jobs) == jobs_before + 1
print("[ok] ручное задание создано из выделенных страниц")

# превью размещения обновляется и показывает страницу
win._update_placement_preview()
assert win.lbl_scale.text().startswith("Масштаб:")
assert "Страница 1 из" in win.lbl_pagenav.text()
assert not win.place_preview.page_pixmap.isNull()
pm = win.place_preview.grab()
assert not pm.isNull()
print(f"[ok] превью размещения рендерится ({pm.width()}x{pm.height()})")

# выбор задания в таблице подгружает его в редактор
win.jobs_table.selectRow(0)
assert win.ed_name.text() == win.jobs[0].name
print("[ok] редактор подгружает выбранное задание")

# удаление
win.jobs_table.selectRow(len(win.jobs) - 1)
win.delete_selected_job()
assert len(win.jobs) == jobs_before
print("[ok] удаление задания")

# ---------- интернационализация ----------
from app.i18n import tr, set_language, get_language

set_language("en")
assert tr("Книжная") == "Portrait"
assert tr("Альбомная") == "Landscape"
assert tr("Нечто несуществующее") == "Нечто несуществующее"  # fallback
set_language("ru")
assert tr("Книжная") == "Книжная"
print("[ok] tr(): переводы и fallback")

# переключение языка на лету в работающем окне
idx_en = win.cb_language.findData("en")
assert idx_en >= 0
win.cb_language.setCurrentIndex(idx_en)
assert get_language() == "en"
assert win.editor_box.title() == "Print job"
assert win.jobs_box.title() == "Jobs"
assert win.cb_orient.itemText(1) == "Portrait"
assert win.cb_duplex.itemText(0) == "None"
assert win.jobs_table.horizontalHeaderItem(0).text() == "Name"
assert win.lbl_scale.text().startswith("Scale:")
assert "Page 1 of" in win.lbl_pagenav.text()
# подписи миниатюр тоже перевелись
assert "portrait" in win.page_list.item(0).text()
print("[ok] окно переключено на английский на лету")

# обратно на русский
win.cb_language.setCurrentIndex(win.cb_language.findData("ru"))
assert win.editor_box.title() == "Задание печати"
assert win.cb_orient.itemText(1) == "Книжная"
assert win.lbl_scale.text().startswith("Масштаб:")
print("[ok] окно переключено обратно на русский")

# язык сохранился в настройках
assert win.settings.get("language") == "ru"
print("[ok] язык сохраняется в настройках")

print("ВСЕ ПРОВЕРКИ ПРОШЛИ")
