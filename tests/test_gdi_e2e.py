# -*- coding: utf-8 -*-
"""Сквозной тест GDI-печати на PDFCreator после исправления смещений DEVMODE.

Тест 1: формат Ledger (431,8x279,4 мм) — форма есть в драйвере (id 4),
        ожидаем в PS /PageSize [1224 792].
Тест 2: формат 420x297 мм — формы в драйвере нет, идёт DMPAPER_USER,
        ожидаем CreateDCW успешен и PS /PageSize [1191 842].
"""
import glob
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.jobs import PrintJob, build_job_pdfs
from app.gdi_print import print_pdf_gdi, get_printer_forms, _find_form_id

PRINTER = "PDFCreator"
SPOOL = os.path.expandvars(r"%LOCALAPPDATA%\Temp\PDFCreator\spool\*.PS")
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "test_mixed.pdf")


def spool_snapshot():
    return set(glob.glob(SPOOL))


def new_ps_files(before, wait=30):
    deadline = time.time() + wait
    while time.time() < deadline:
        new = sorted(spool_snapshot() - before)
        if new:
            # ждём, пока файл освободится и перестанет расти
            path = new[-1]
            try:
                s1 = os.path.getsize(path)
                with open(path, "rb"):
                    pass
                time.sleep(1.0)
                s2 = os.path.getsize(path)
                if s1 == s2 and s1 > 0:
                    return new
            except (PermissionError, OSError):
                pass
        time.sleep(0.5)
    return []


def analyze_ps(path):
    with open(path, "rb") as f:
        data = f.read()
    import re
    m = re.findall(rb"PageSize\s*\[?\s*(\d+)\s+(\d+)", data)
    return [(int(a), int(b)) for a, b in m]


def run_case(title, sheet_mm, expect_ps):
    print(f"\n=== {title} ===")
    job = PrintJob(
        name=title,
        pages=[1],                      # страница A3 из test_mixed.pdf
        printer=PRINTER,
        paper=f"{sheet_mm[0]}×{sheet_mm[1]} мм",
        paper_mm=(min(sheet_mm), max(sheet_mm)),
        orientation="landscape",
        scale="fit",
        auto_rotate=True,
        margins_mm=5.0,
    )
    with tempfile.TemporaryDirectory() as tmp:
        parts = build_job_pdfs(SRC, job, tmp)
        assert len(parts) == 1, f"ожидалась 1 часть, получено {len(parts)}"
        part_path, _pages_out, orient = parts[0]
        print(f"собран лист: {part_path}, ориентация={orient}")

        before = spool_snapshot()
        ok, msg = print_pdf_gdi(PRINTER, part_path, job,
                                paper_mm=(max(sheet_mm), min(sheet_mm)),
                                doc_name=title)
        print(f"print_pdf_gdi: ok={ok}, {msg}")
        if not ok:
            return False

        files = new_ps_files(before)
        if not files:
            print("ОШИБКА: новый PS в спуле не появился")
            return False
        sizes = analyze_ps(files[-1])
        print(f"PS: {os.path.basename(files[-1])}, PageSize={sizes}")
        if expect_ps in sizes:
            print(f"ОК: найден ожидаемый PageSize {expect_ps}")
            return True
        print(f"ОШИБКА: ожидался PageSize {expect_ps}")
        return False


def main():
    forms = get_printer_forms(PRINTER)
    print(f"форм в драйвере: {len(forms)}")
    ledger = _find_form_id(forms, 431.8, 279.4)
    print(f"Ledger (431.8x279.4) form id: {ledger}")
    custom = _find_form_id(forms, 420.0, 297.0)
    print(f"420x297 form id: {custom} (ожидается None)")

    r1 = run_case("GDI Ledger", (431.8, 279.4), (1224, 792))
    r2 = run_case("GDI user 420x297", (420.0, 297.0), (1191, 842))
    print("\nИТОГ:", "OK" if (r1 and r2) else "ЕСТЬ ОШИБКИ")
    return 0 if (r1 and r2) else 1


if __name__ == "__main__":
    sys.exit(main())
