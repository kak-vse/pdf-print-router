# -*- coding: utf-8 -*-
"""Проверка: как драйвер трактует DMPAPER_USER с разной dmOrientation."""
import glob
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.gdi_print as g
from app.jobs import PrintJob, build_job_pdfs

PRINTER = "PDFCreator"
SPOOL = os.path.expandvars(r"%LOCALAPPDATA%\Temp\PDFCreator\spool\*.PS")
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "test_mixed.pdf")


def snap():
    return set(glob.glob(SPOOL))


def wait_new(before, wait=30):
    deadline = time.time() + wait
    while time.time() < deadline:
        new = sorted(snap() - before)
        if new:
            p = new[-1]
            try:
                s1 = os.path.getsize(p)
                with open(p, "rb"):
                    pass
                time.sleep(1.0)
                if s1 == os.path.getsize(p) and s1 > 0:
                    return p
            except OSError:
                pass
        time.sleep(0.5)
    return None


def print_with_orientation(orient_val, paper_mm):
    """Печать с принудительной dmOrientation (1=portrait, 2=landscape)."""
    job = PrintJob(name="t", pages=[1], printer=PRINTER,
                   paper_mm=(min(paper_mm), max(paper_mm)),
                   orientation="landscape")
    with tempfile.TemporaryDirectory() as tmp:
        part = build_job_pdfs(SRC, job, tmp)[0][0]

        # подменяем _patch_devmode, чтобы выставить нужную ориентацию
        orig = g._patch_devmode
        def patched(buf, form_id, mm, copies, duplex, color):
            orig(buf, form_id, mm, copies, duplex, color)
            import struct
            struct.pack_into("<h", buf, g._OFF_ORIENTATION, orient_val)
        g._patch_devmode = patched
        try:
            before = snap()
            ok, msg = g.print_pdf_gdi(PRINTER, part, job, paper_mm=paper_mm,
                                      doc_name=f"orient{orient_val}")
        finally:
            g._patch_devmode = orig
    print(f"orientation={orient_val}: ok={ok} {msg}")
    ps = wait_new(before)
    if ps:
        import re
        data = open(ps, "rb").read()
        m = re.findall(rb"(\d+)\s+(\d+)\s+0 0 1\s*\n", data)
        print("  custom size в PS:", m[:2], os.path.basename(ps))
        return ps
    return None


p1 = print_with_orientation(1, (420.0, 297.0))
p2 = print_with_orientation(2, (420.0, 297.0))
print("PS files:", p1, p2)
