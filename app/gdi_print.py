"""Прямая печать PDF через Win32 GDI с собственным DEVMODE.

Нужна там, где SumatraPDF бессильна: размер и ориентация формы бумаги
драйвер берёт только из DEVMODE (плоттеры с рулоном — длинная сторона
поперёк рулона). DEVMODE передаётся при создании DC, поэтому прав
администратора и изменения настроек принтера не требуется.

Форма бумаги подбирается по размеру из списка форм драйвера
(DeviceCapabilities); если точного совпадения нет — передаются
DMPAPER_USER и явные размеры (плоттерные драйверы их принимают).
"""

import ctypes
import struct
from ctypes import wintypes

import numpy as np

_winspool = ctypes.WinDLL("winspool.drv")
_gdi32 = ctypes.WinDLL("gdi32")

# Поля DEVMODE (биты dmFields)
_DM_ORIENTATION = 0x00000001
_DM_PAPERSIZE = 0x00000002
_DM_PAPERLENGTH = 0x00000004
_DM_PAPERWIDTH = 0x00000008
_DM_COPIES = 0x00000100
_DM_COLOR = 0x00000800
_DM_DUPLEX = 0x00001000

_DUPLEX_TO_DM = {"none": 1, "long": 2, "short": 3}
_COLOR_TO_DM = {"mono": 1, "color": 2}

# GetDeviceCaps
_LOGPIXELSX = 88
_LOGPIXELSY = 90
_HORZRES = 8
_VERTRES = 10

_DIB_RGB_COLORS = 0
_SRCCOPY = 0x00CC0020


class _PRINTER_DEFAULTS(ctypes.Structure):
    _fields_ = [("pDatatype", ctypes.c_wchar_p),
                ("pDevMode", ctypes.c_void_p),
                ("DesiredAccess", wintypes.DWORD)]


class _DOCINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_int),
                ("lpszDocName", ctypes.c_wchar_p),
                ("lpszOutput", ctypes.c_wchar_p),
                ("lpszDatatype", ctypes.c_wchar_p),
                ("fwType", wintypes.DWORD)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


def _open_printer(name):
    h = ctypes.c_void_p()
    pd = _PRINTER_DEFAULTS(None, None, 0x08)  # PRINTER_ACCESS_USE
    if not _winspool.OpenPrinterW(name, ctypes.byref(h), ctypes.byref(pd)):
        raise RuntimeError(f"Не удалось открыть принтер «{name}»")
    return h


def _get_devmode(h, name):
    """Текущий DEVMODE принтера (сырой буфер, как база для правок)."""
    size = _winspool.DocumentPropertiesW(0, h, name, None, None, 0)
    if size <= 0:
        raise RuntimeError("DocumentProperties: не удалось получить размер DEVMODE")
    buf = ctypes.create_string_buffer(size)
    rc = _winspool.DocumentPropertiesW(0, h, name, buf, None, 2)  # DM_OUT_BUFFER
    if rc < 0:
        raise RuntimeError("DocumentProperties: не удалось получить DEVMODE")
    return buf


def get_printer_forms(printer_name):
    """Формы драйвера: [(paper_id, имя, w_mm, h_mm)]."""
    DC_PAPERS = 2
    DC_PAPERNAMES = 16
    DC_PAPERSIZE = 3
    n = _winspool.DeviceCapabilitiesW(printer_name, None, DC_PAPERS,
                                      None, None)
    if n <= 0:
        return []
    ids = (wintypes.WORD * n)()
    _winspool.DeviceCapabilitiesW(printer_name, None, DC_PAPERS, ids, None)
    names_buf = ctypes.create_unicode_buffer(64 * n)
    _winspool.DeviceCapabilitiesW(printer_name, None, DC_PAPERNAMES,
                                  names_buf, None)
    sizes = (wintypes.POINT * n)()
    _winspool.DeviceCapabilitiesW(printer_name, None, DC_PAPERSIZE, sizes, None)
    forms = []
    for i in range(n):
        name = names_buf[i * 64:(i + 1) * 64].split("\x00")[0].strip()
        w, h = sizes[i].x / 10.0, sizes[i].y / 10.0
        if name and w > 0 and h > 0:
            forms.append((int(ids[i]), name, round(w, 1), round(h, 1)))
    return forms


def _find_form_id(forms, w_mm, h_mm, tol=1.5):
    """ID формы с размерами w×h мм (без учёта ориентации)."""
    for pid, _name, fw, fh in forms:
        if abs(fw - w_mm) <= tol and abs(fh - h_mm) <= tol:
            return pid
    return None


# Смещения полей в DEVMODEW (dmDeviceName = 32 WCHAR = 64 байта)
_OFF_FIELDS = 72
_OFF_ORIENTATION = 76
_OFF_PAPERSIZE = 78
_OFF_PAPERLENGTH = 80
_OFF_PAPERWIDTH = 82
_OFF_COPIES = 86
_OFF_COLOR = 92
_OFF_DUPLEX = 94


def _patch_devmode(buf, form_id, paper_mm, copies, duplex, color):
    fields = struct.unpack_from("<I", buf, _OFF_FIELDS)[0]
    # Ориентация всегда «книжная»: лист уже собран в нужных габаритах,
    # форма (ширина × длина) передаётся как есть.
    struct.pack_into("<h", buf, _OFF_ORIENTATION, 1)
    fields |= _DM_ORIENTATION
    if form_id is not None:
        struct.pack_into("<h", buf, _OFF_PAPERSIZE, form_id)
        fields |= _DM_PAPERSIZE
    else:
        # формы нет в списке драйвера — передаём произвольный размер
        struct.pack_into("<h", buf, _OFF_PAPERSIZE, 0)  # DMPAPER_USER
        struct.pack_into("<h", buf, _OFF_PAPERWIDTH,
                         int(round(paper_mm[0] * 10)))
        struct.pack_into("<h", buf, _OFF_PAPERLENGTH,
                         int(round(paper_mm[1] * 10)))
        fields |= _DM_PAPERSIZE | _DM_PAPERWIDTH | _DM_PAPERLENGTH
    if copies:
        struct.pack_into("<h", buf, _OFF_COPIES, copies)
        fields |= _DM_COPIES
    if duplex in _DUPLEX_TO_DM:
        struct.pack_into("<h", buf, _OFF_DUPLEX, _DUPLEX_TO_DM[duplex])
        fields |= _DM_DUPLEX
    if color in _COLOR_TO_DM:
        struct.pack_into("<h", buf, _OFF_COLOR, _COLOR_TO_DM[color])
        fields |= _DM_COLOR
    struct.pack_into("<I", buf, _OFF_FIELDS, fields)


def _pixmap_to_bgr(pix):
    """PyMuPDF Pixmap (RGB/RGBA) → bytes BGR24, строки выровнены до 4 байт."""
    img = np.frombuffer(pix.samples, dtype=np.uint8)
    img = img.reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    bgr = img[:, :, ::-1]
    row_bytes = pix.width * 3
    pad = (4 - row_bytes % 4) % 4
    if pad:
        bgr = np.concatenate(
            [bgr, np.zeros((pix.height, pad, 3), dtype=np.uint8)], axis=1)
    return bgr.tobytes()


def print_pdf_gdi(printer_name, pdf_path, job, paper_mm, dpi_max=300,
                  doc_name="PDF Print Router"):
    """Печать PDF через GDI с явным DEVMODE.

    paper_mm — (ширина, длина) листа в мм, как подаётся в принтер
    (для альбомного листа ширина > длины). Контент в PDF должен быть
    уже собран под эти габариты. Возвращает (ok, сообщение).
    """
    import pymupdf

    h_printer = _open_printer(printer_name)
    try:
        buf = _get_devmode(h_printer, printer_name)
        forms = get_printer_forms(printer_name)
        form_id = _find_form_id(forms, paper_mm[0], paper_mm[1])
        _patch_devmode(buf, form_id, paper_mm, job.copies,
                       job.duplex, None if job.color == "auto" else job.color)

        hdc = _gdi32.CreateDCW("WINSPOOL", printer_name, None, buf)
        if not hdc:
            return False, "CreateDCW: драйвер отклонил настройки бумаги"
        try:
            dpi_x = _gdi32.GetDeviceCaps(hdc, _LOGPIXELSX)
            dpi_y = _gdi32.GetDeviceCaps(hdc, _LOGPIXELSY)
            page_w = _gdi32.GetDeviceCaps(hdc, _HORZRES)
            page_h = _gdi32.GetDeviceCaps(hdc, _VERTRES)
            if dpi_x <= 0 or page_w <= 0 or page_h <= 0:
                return False, "драйвер вернул некорректные параметры страницы"

            doc = pymupdf.open(pdf_path)
            try:
                di = _DOCINFO(ctypes.sizeof(_DOCINFO), doc_name, None, None, 0)
                if _gdi32.StartDocW(hdc, ctypes.byref(di)) <= 0:
                    return False, "StartDoc: задание не создано"
                try:
                    for page in doc:
                        zoom = min(dpi_max, dpi_x, dpi_y) / 72.0
                        pix = page.get_pixmap(
                            matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                        data = _pixmap_to_bgr(pix)
                        bmi = _BITMAPINFO()
                        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
                        bmi.bmiHeader.biWidth = pix.width
                        bmi.bmiHeader.biHeight = -pix.height  # сверху вниз
                        bmi.bmiHeader.biPlanes = 1
                        bmi.bmiHeader.biBitCount = 24
                        bmi.bmiHeader.biCompression = 0  # BI_RGB

                        if _gdi32.StartPage(hdc) <= 0:
                            return False, "StartPage: ошибка драйвера"
                        res = _gdi32.StretchDIBits(
                            hdc, 0, 0, page_w, page_h,
                            0, 0, pix.width, pix.height,
                            data, ctypes.byref(bmi),
                            _DIB_RGB_COLORS, _SRCCOPY)
                        if res in (0, -1):
                            return False, "StretchDIBits: ошибка вывода"
                        if _gdi32.EndPage(hdc) <= 0:
                            return False, "EndPage: ошибка драйвера"
                finally:
                    _gdi32.EndDoc(hdc)
            finally:
                doc.close()
        finally:
            _gdi32.DeleteDC(hdc)
    finally:
        _winspool.ClosePrinter(h_printer)
    return True, "отправлено на печать (GDI)"
