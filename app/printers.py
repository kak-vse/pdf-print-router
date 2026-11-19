"""Принтеры Windows и печать через SumatraPDF CLI."""

import json
import os
import shutil
import subprocess
import sys

from .jobs import DUPLEX_TO_SUMATRA

IS_WINDOWS = sys.platform.startswith("win")

SUMATRA_CANDIDATES = [
    os.environ.get("SUMATRA_PDF", ""),
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\SumatraPDF\SumatraPDF.exe"),
]

# Стандартные форматы для передачи в драйвер (имена Windows)
WINDOWS_PAPER_NAMES = {
    "A0": "A0", "A1": "A1", "A2": "A2", "A3": "A3", "A4": "A4",
    "A5": "A5", "A6": "A6", "Letter": "Letter", "Legal": "Legal",
    "Tabloid": "Tabloid",
}


# ---------- свойства драйвера принтера (как «Свойства» в Foxit Reader) ----------

# Биты полей DEVMODE
_DM_ORIENTATION = 0x00000001
_DM_PAPERSIZE = 0x00000002
_DM_PAPERLENGTH = 0x00000004
_DM_PAPERWIDTH = 0x00000008
_DM_COPIES = 0x00000100
_DM_COLOR = 0x00000800
_DM_DUPLEX = 0x00001000
# Режимы DocumentPropertiesW
_DM_IN_BUFFER = 0x08
_DM_IN_PROMPT = 0x04
_DM_OUT_BUFFER = 0x02
_IDOK = 1

_DUPLEX_FROM_DEVMODE = {1: "none", 2: "long", 3: "short"}
_COLOR_FROM_DEVMODE = {1: "mono", 2: "color"}


def _read_default_devmode(h):
    """DEVMODE по умолчанию: сначала per-user (уровень 9), затем общий."""
    import win32print
    try:
        dm = win32print.GetPrinter(h, 9).get("pDevMode")
        if dm is not None:
            return dm
    except Exception:
        pass
    return win32print.GetPrinter(h, 2).get("pDevMode")


def printer_properties_dialog(hwnd, printer_name):
    """Открывает диалог свойств драйвера принтера (как кнопка «Свойства» в Foxit).

    При OK настройки сохраняются как личные умолчания пользователя
    (PRINTER_INFO_9 — без прав администратора), поэтому при следующем
    открытии диалог показывает их, а не заводские. Возвращает dict
    с настройками: paper_mm, orientation, copies, duplex, color
    (None — отмена или ошибка).
    """
    if not IS_WINDOWS:
        return None
    import win32print
    try:
        h = win32print.OpenPrinter(printer_name)
    except Exception:
        return None
    try:
        dm = _read_default_devmode(h)
        if dm is None:
            return None
        rc = win32print.DocumentProperties(
            hwnd, h, printer_name, dm, dm,
            _DM_IN_BUFFER | _DM_IN_PROMPT | _DM_OUT_BUFFER)
        if rc != _IDOK:
            return None
        # сохранить выбор пользователя как его личные умолчания
        try:
            win32print.SetPrinter(h, 9, {"pDevMode": dm}, 0)
        except Exception:
            pass
        fields = dm.Fields
        out = {}
        if (fields & _DM_PAPERWIDTH) and (fields & _DM_PAPERLENGTH):
            # PaperWidth/PaperLength — в десятых долях миллиметра
            out["paper_mm"] = (dm.PaperWidth / 10.0, dm.PaperLength / 10.0)
            if fields & _DM_PAPERSIZE and dm.PaperSize >= 0x100:
                # 0x100+ — пользовательская форма сервера печати
                out["custom_form"] = True
        if fields & _DM_ORIENTATION:
            out["orientation"] = "landscape" if dm.Orientation == 2 else "portrait"
        if fields & _DM_COPIES and dm.Copies > 1:
            out["copies"] = dm.Copies
        if fields & _DM_DUPLEX:
            out["duplex"] = _DUPLEX_FROM_DEVMODE.get(dm.Duplex)
        if fields & _DM_COLOR:
            out["color"] = _COLOR_FROM_DEVMODE.get(dm.Color)
        return out
    except Exception:
        return None
    finally:
        win32print.ClosePrinter(h)


def get_printer_papers(printer_name):
    """Список форматов бумаги, поддерживаемых драйвером: [(имя, w_mm, h_mm)]."""
    if not IS_WINDOWS:
        return []
    import ctypes
    from ctypes import wintypes

    DC_PAPERNAMES = 16
    DC_PAPERSIZE = 3
    winspool = ctypes.WinDLL("winspool.drv")
    n = winspool.DeviceCapabilitiesW(printer_name, None, DC_PAPERNAMES,
                                     None, None)
    if n <= 0:
        return []
    names_buf = ctypes.create_unicode_buffer(64 * n)
    if winspool.DeviceCapabilitiesW(printer_name, None, DC_PAPERNAMES,
                                    names_buf, None) <= 0:
        return []
    sizes = (wintypes.POINT * n)()
    winspool.DeviceCapabilitiesW(printer_name, None, DC_PAPERSIZE, sizes, None)
    papers = []
    for i in range(n):
        name = names_buf[i * 64:(i + 1) * 64].split("\x00")[0].strip()
        # POINT в 0.1 мм
        w, h = sizes[i].x / 10.0, sizes[i].y / 10.0
        if name and w > 0 and h > 0:
            papers.append((name, round(w, 1), round(h, 1)))
    return papers


def list_printers():
    """Список имён принтеров. На Windows: win32print, запасной вариант — PowerShell."""
    if not IS_WINDOWS:
        return []
    try:
        import win32print
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return sorted(p[2] for p in win32print.EnumPrinters(flags))
    except ImportError:
        pass
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Printer | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=30)
        return sorted(l.strip() for l in out.stdout.splitlines() if l.strip())
    except Exception:
        return []


def default_printer():
    if not IS_WINDOWS:
        return ""
    try:
        import win32print
        return win32print.GetDefaultPrinter()
    except Exception:
        return ""


def find_sumatra(configured=None):
    if configured and os.path.isfile(configured):
        return configured
    exe = shutil.which("SumatraPDF.exe") or shutil.which("sumatrapdf")
    if exe:
        return exe
    for path in SUMATRA_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    return None


def sumatra_settings_string(job, resolved_orientation):
    parts = []
    paper = WINDOWS_PAPER_NAMES.get(job.paper)
    if paper:
        parts.append(f"paper={paper}")
    elif job.paper_mm and job.paper_mm[0] > 0 and job.paper_mm[1] > 0:
        # Нестандартный/пользовательский формат — передаём размер напрямую
        # (SumatraPDF 3.2+ понимает paper=<ширина>x<высота><единицы>).
        w, h = job.paper_mm
        parts.append(f"paper={w:g}x{h:g}mm")
    # Страницы уже собраны точно под формат и повёрнуты как надо —
    # запрещаем Sumatra её авто-поворот и масштабные сюрпризы.
    parts.append("fit")
    parts.append("disable-auto-rotation")
    parts.append(resolved_orientation)
    parts.append(DUPLEX_TO_SUMATRA[job.duplex])
    if job.copies > 1:
        parts.append(f"copies={job.copies}")
    if job.color == "mono":
        parts.append("monochrome")
    elif job.color == "color":
        parts.append("color")
    return ",".join(parts)


def print_job(sumatra_path, pdf_path, job, resolved_orientation, dry_run=False):
    """Отправляет задание на печать. Возвращает (ok, сообщение)."""
    if not job.printer:
        return False, "не выбран принтер"
    cmd = [sumatra_path, "-print-to", job.printer,
           "-print-settings", sumatra_settings_string(job, resolved_orientation),
           "-silent", "-exit-on-print", pdf_path]
    if dry_run:
        return True, "dry-run: " + subprocess.list2cmdline(cmd)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return False, "таймаут (принтер не отвечает?)"
    if res.returncode == 0:
        return True, "отправлено на печать"
    return False, f"код {res.returncode}: {(res.stdout + res.stderr).strip()}"


def job_to_manifest_entry(job, resolved_orientation, file_name):
    return {
        "file": file_name, "name": job.name, "printer": job.printer,
        "paper": WINDOWS_PAPER_NAMES.get(job.paper),
        "paper_mm": list(job.paper_mm),
        "orientation": resolved_orientation,
        "duplex": DUPLEX_TO_SUMATRA[job.duplex],
        "copies": job.copies, "color": job.color,
        "pages_out": len(job.pages),
    }


def save_manifest(path, source_name, entries):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"source": source_name, "jobs": entries}, f,
                  ensure_ascii=False, indent=2)
