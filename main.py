#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF Print Router — точка входа."""

import sys

from PySide6.QtWidgets import QApplication

from app import APP_NAME
from app.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        window.load_pdf_path = sys.argv[1]  # открытие через «Открыть с помощью»
        _open_initial(window, sys.argv[1])
    sys.exit(app.exec())


def _open_initial(window, path):
    try:
        import os
        from app.pdf_document import PdfDocument
        window.document = PdfDocument(path)
        window.setWindowTitle(f"{os.path.basename(path)} — {APP_NAME}")
        window.jobs.clear()
        window.refresh_jobs_table()
        window.populate_pages()
    except Exception:
        pass


if __name__ == "__main__":
    main()
