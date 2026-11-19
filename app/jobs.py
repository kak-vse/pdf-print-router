"""Модель заданий печати и построение PDF под формат бумаги (pypdf)."""

import os
from dataclasses import dataclass, field, asdict

from pypdf import PdfWriter, Transformation
from pypdf import PageObject

MM_TO_PT = 72.0 / 25.4

ORIENTATIONS = ("auto", "portrait", "landscape")
SCALE_MODES = ("fit", "fill", "none", "percent")
DUPLEX_MODES = ("none", "long", "short")
COLOR_MODES = ("auto", "color", "mono")

DUPLEX_TO_SUMATRA = {"none": "simplex", "long": "duplex", "short": "duplexshort"}


@dataclass
class PrintJob:
    name: str
    pages: list                     # 0-based индексы страниц в порядке печати
    printer: str = ""
    paper: str = "A4"               # имя формата Windows (A4, Letter...) или метка '100×150 мм'
    paper_mm: tuple = (210.0, 297.0)  # книжная ориентация (короткая, длинная стороны)
    orientation: str = "auto"
    scale: str = "fit"
    scale_percent: float = 100.0   # используется при scale == "percent"
    auto_rotate: bool = True       # автоповорот содержимого на 90° под книжный лист
    auto_center: bool = True       # центрировать содержимое на листе
    margins_mm: float = 5.0
    duplex: str = "none"
    copies: int = 1
    color: str = "auto"

    def to_dict(self):
        d = asdict(self)
        d["paper_mm"] = list(self.paper_mm)
        return d

    @staticmethod
    def from_dict(d):
        d = dict(d)
        d["paper_mm"] = tuple(d["paper_mm"])
        return PrintJob(**d)

    def summary(self):
        n = len(self.pages)
        return (f"{self.name}: стр. {n} шт. → {self.printer or '(принтер не выбран)'}, "
                f"{self.paper}, {self.orientation}, дуплекс={self.duplex}, "
                f"копий={self.copies}")


def auto_split(document, printer_map=None):
    """Группирует страницы по формату бумаги → список PrintJob.

    printer_map: {метка_формата: имя_принтера}, например {'A4': 'HP LaserJet'}.
    """
    printer_map = printer_map or {}
    groups = {}  # key -> (paper_name, paper_mm, [pages])
    order = []
    for i in range(document.page_count):
        name, sw, sh = document.paper_group_key(i)
        if name not in groups:
            groups[name] = (name, (sw, sh), [])
            order.append(name)
        groups[name][2].append(i)

    jobs = []
    for name in order:
        paper_name, paper_mm, pages = groups[name]
        jobs.append(PrintJob(
            name=f"{paper_name} ({len(pages)} стр.)",
            pages=pages,
            printer=printer_map.get(paper_name, ""),
            paper=paper_name,
            paper_mm=paper_mm,
        ))
    return jobs


def _page_size_pt(page):
    """(w, h) страницы в пунктах с учётом /Rotate."""
    w = float(page.mediabox.width)
    h = float(page.mediabox.height)
    if int(page.get("/Rotate", 0)) % 180:
        w, h = h, w
    return w, h


def sheet_landscape(orientation):
    """Ориентация листа: альбомная только при явном выборе «Альбомная».

    «Авто» и «Книжная» собирают книжный лист (бумага в офисные принтеры
    подаётся книжно); «Альбомная» — для плоттеров с рулоном, где длинная
    сторона должна лечь поперёк рулона (печать идёт через GDI).
    """
    return orientation == "landscape"


def content_needs_rotation(orientation, auto_rotate, w, h):
    """Нужно ли поворачивать содержимое на 90° («Автоповорот» как в Foxit).

    Поворот выполняется, когда пропорции контента не совпадают
    с пропорциями листа: альбомный контент на книжном листе и наоборот.
    При auto_rotate=False содержимое вписывается без поворота.
    """
    if not auto_rotate:
        return False
    content_landscape = w > h
    if sheet_landscape(orientation):
        return not content_landscape
    return content_landscape


def _scaled_transform(page, target_w, target_h, mode, margin_pt,
                      scale_percent=100.0, center=True, rotate90=False):
    page.transfer_rotation_to_content()
    box = page.mediabox
    w, h = float(box.width), float(box.height)
    if w <= 0 or h <= 0:
        raise ValueError("Пустой mediabox страницы")
    left, bottom = float(box.left), float(box.bottom)

    if rotate90:
        # поворот на 90° (Transformation().rotate(270)): (x,y) -> (y,-x)
        # габариты контента после поворота и их минимумы
        rw, rh = h, w
        rx0, ry0 = bottom, -(left + w)
    else:
        rw, rh = w, h
        rx0, ry0 = left, bottom

    avail_w, avail_h = target_w - 2 * margin_pt, target_h - 2 * margin_pt
    if mode == "fit":
        s = min(avail_w / rw, avail_h / rh)
    elif mode == "fill":
        s = max(avail_w / rw, avail_h / rh)
    elif mode == "percent":
        # Ручной масштаб в процентах от исходного размера страницы
        s = max(scale_percent, 1.0) / 100.0
    else:  # none — исходный размер
        s = 1.0

    if center:
        tx = (target_w - rw * s) / 2.0 - rx0 * s
        ty = (target_h - rh * s) / 2.0 - ry0 * s
    else:
        # прижать к левому верхнему углу с учётом полей
        # (ось Y в PDF направлена вверх)
        tx = margin_pt - rx0 * s
        ty = target_h - margin_pt - rh * s - ry0 * s

    t = Transformation()
    if rotate90:
        t = t.rotate(270)
    return t.scale(s).translate(tx, ty)


def build_job_pdf(source_path, job, out_path):
    """Строит PDF задания: страницы масштабированы и размещены на листе.

    Книжная ориентация — лист (короткая × длинная сторона), альбомное
    содержимое поворачивается на 90° (офисные принтеры, печать через
    SumatraPDF). Альбомная — лист (длинная × короткая), для плоттеров
    с рулоном; печать идёт через GDI с явным DEVMODE.
    Возвращает (путь, число_страниц, 'portrait'|'landscape').
    """
    doc = PdfWriter(clone_from=source_path)

    sw_mm, sh_mm = job.paper_mm  # книжная ориентация (короткая, длинная)
    if sheet_landscape(job.orientation):
        tw = max(sw_mm, sh_mm) * MM_TO_PT
        th = min(sw_mm, sh_mm) * MM_TO_PT
        orient_out = "landscape"
    else:
        tw = min(sw_mm, sh_mm) * MM_TO_PT
        th = max(sw_mm, sh_mm) * MM_TO_PT
        orient_out = "portrait"

    margin_pt = job.margins_mm * MM_TO_PT
    writer = PdfWriter()
    for idx in job.pages:
        src = doc.pages[idx]
        pw, ph = _page_size_pt(src)
        rotate90 = content_needs_rotation(
            job.orientation, job.auto_rotate, pw, ph)
        t = _scaled_transform(src, tw, th, job.scale, margin_pt,
                              job.scale_percent, job.auto_center, rotate90)
        dst = PageObject.create_blank_page(width=tw, height=th)
        dst.merge_transformed_page(src, t)
        writer.add_page(dst)

    # Дуплекс: добиваем до чётного числа, чтобы копии не съезжали на один лист
    if job.duplex in ("long", "short") and len(job.pages) % 2 == 1:
        writer.add_blank_page(width=tw, height=th)

    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path, len(writer.pages), orient_out


def build_job_pdfs(source_path, job, tmpdir, base="job"):
    """Строит PDF задания для печати.

    Возвращает [(путь, число_страниц, ориентация), ...] — сейчас всегда
    одна часть в книжной ориентации; список оставлен для совместимости.
    """
    path = os.path.join(tmpdir, f"{base}.pdf")
    _, pages_out, orient = build_job_pdf(source_path, job, path)
    return [(path, pages_out, orient)]
