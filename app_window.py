from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import fitz
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from takeoff_workbench.data import db
from takeoff_workbench.export.export_csv import export_csv
from takeoff_workbench.export.export_xlsx import export_xlsx
from takeoff_workbench.ingest.file_index import find_pdfs
from takeoff_workbench.ingest.package_ingest import ingest_pdfs
from takeoff_workbench.ingest.pdf_ingest import ingest_pdf
from takeoff_workbench.review.review_actions import (
    accept_candidate,
    create_manual_candidate_from_region,
    reject_candidate,
)


class PageViewer(QWidget):
    region_selected = Signal(tuple)
    region_started = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(640, 480)
        self.setMouseTracking(True)
        self._pixmap: Optional[QPixmap] = None
        self._page_width = 1.0
        self._page_height = 1.0
        self._display_scale = 1.0
        self._selection_anchor: Optional[QPoint] = None
        self._selection_current: Optional[QPoint] = None
        self._confirmed_rect: Optional[QRect] = None
        self._last_region: Optional[tuple[float, float, float, float]] = None
        self.setFocusPolicy(Qt.StrongFocus)

    def set_page(self, pixmap: QPixmap, page_width: float, page_height: float, display_scale: float = 1.0) -> None:
        self._pixmap = pixmap
        self._page_width = max(float(page_width or 1.0), 1.0)
        self._page_height = max(float(page_height or 1.0), 1.0)
        self._display_scale = max(float(display_scale or 1.0), 0.05)
        self._last_region = None
        self._selection_anchor = None
        self._selection_current = None
        self._confirmed_rect = None
        target = self._target_rect()
        self.setMinimumSize(target.width() + 36, target.height() + 36)
        self.setMaximumSize(target.width() + 36, target.height() + 36)
        self.update()

    def selected_region(self) -> Optional[tuple[float, float, float, float]]:
        return self._last_region

    def clear_selection(self) -> None:
        self._last_region = None
        self._selection_anchor = None
        self._selection_current = None
        self._confirmed_rect = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#eef2f4"))
        if self._pixmap:
            target = self._target_rect()
            painter.drawPixmap(target, self._pixmap)
            painter.setPen(QPen(QColor("#1c6b84"), 2))
            painter.drawRect(target)
        active_rect = self._active_screen_rect()
        if active_rect:
            painter.setPen(QPen(QColor("#d24b2a"), 2, Qt.DashLine))
            painter.drawRect(active_rect)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or not self._pixmap:
            return
        point = event.position().toPoint()
        if not self._target_rect().contains(point):
            return
        if self._selection_anchor is None:
            self._selection_anchor = point
            self._selection_current = point
            self._confirmed_rect = None
            self._last_region = None
            self.region_started.emit()
        else:
            rect = QRect(self._selection_anchor, point).normalized()
            region = self._screen_rect_to_page(rect)
            self._selection_current = point
            if region:
                self._last_region = region
                self._confirmed_rect = rect
                self.region_selected.emit(region)
            self._selection_anchor = None
            self._selection_current = None
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._selection_anchor:
            point = event.position().toPoint()
            target = self._target_rect()
            x = min(max(point.x(), target.left()), target.right())
            y = min(max(point.y(), target.top()), target.bottom())
            self._selection_current = QPoint(x, y)
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        return

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.clear_selection()
        else:
            super().keyPressEvent(event)

    def _target_rect(self) -> QRect:
        if not self._pixmap:
            return QRect()
        margin = 18
        width = max(1, int(self._page_width * self._display_scale))
        height = max(1, int(self._page_height * self._display_scale))
        return QRect(margin, margin, width, height)

    def _screen_rect_to_page(self, screen_rect: QRect) -> Optional[tuple[float, float, float, float]]:
        target = self._target_rect()
        clipped = screen_rect.intersected(target)
        if clipped.width() < 5 or clipped.height() < 5:
            return None
        scale_x = self._page_width / target.width()
        scale_y = self._page_height / target.height()
        x0 = (clipped.left() - target.left()) * scale_x
        y0 = (clipped.top() - target.top()) * scale_y
        x1 = (clipped.right() - target.left()) * scale_x
        y1 = (clipped.bottom() - target.top()) * scale_y
        return (x0, y0, x1, y1)

    def _active_screen_rect(self) -> Optional[QRect]:
        if self._selection_anchor and self._selection_current:
            return QRect(self._selection_anchor, self._selection_current).normalized()
        if self._confirmed_rect:
            return self._confirmed_rect
        return None


class TakeoffMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Takeoff Workbench")
        self.resize(1360, 860)
        self.db_path: Optional[Path] = None
        self.current_page: Optional[dict] = None
        self.current_pdf: Optional[Path] = None
        self.pages: list[dict] = []
        self.candidates: list[dict] = []
        self.zoom_factor = 1.0
        self.high_resolution = True
        self._build_ui()
        self._build_actions()

    def _build_ui(self) -> None:
        root = QSplitter(Qt.Horizontal)
        self.setCentralWidget(root)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Pages"))
        self.page_list = QListWidget()
        self.page_list.currentRowChanged.connect(self._page_row_changed)
        left_layout.addWidget(self.page_list, 1)
        root.addWidget(left)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        self.viewer = PageViewer()
        self.viewer.region_started.connect(self._region_started)
        self.viewer.region_selected.connect(self._region_selected)
        self.viewer_scroll = QScrollArea()
        self.viewer_scroll.setWidget(self.viewer)
        self.viewer_scroll.setWidgetResizable(False)
        self.viewer_scroll.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.viewer_scroll, 1)
        self.region_label = QLabel("Click once to start the red selection window. Move the mouse, then click once to confirm it.")
        center_layout.addWidget(self.region_label)
        center_layout.addWidget(QLabel("Evidence Details"))
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        center_layout.addWidget(self.detail_text, 0)
        root.addWidget(center)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Candidates"))
        self.candidate_table = QTableWidget(0, 8)
        self.candidate_table.setHorizontalHeaderLabels(
            ["Status", "Page", "Material", "Shape", "Qty", "Unit", "Confidence", "Source Text"]
        )
        self.candidate_table.itemSelectionChanged.connect(self._candidate_selection_changed)
        right_layout.addWidget(self.candidate_table, 1)
        buttons = QHBoxLayout()
        self.accept_button = QPushButton("Accept")
        self.accept_button.clicked.connect(self._accept_current_candidate)
        self.reject_button = QPushButton("Reject")
        self.reject_button.clicked.connect(self._reject_current_candidate)
        self.manual_button = QPushButton("Create From Region")
        self.manual_button.clicked.connect(self._create_candidate_from_region)
        buttons.addWidget(self.accept_button)
        buttons.addWidget(self.reject_button)
        buttons.addWidget(self.manual_button)
        right_layout.addLayout(buttons)
        right_layout.addWidget(QLabel("Notes"))
        self.notes_edit = QLineEdit()
        right_layout.addWidget(self.notes_edit)
        root.addWidget(right)
        root.setSizes([260, 760, 420])

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _build_actions(self) -> None:
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)

        open_pdf = QAction("Open PDFs", self)
        open_pdf.triggered.connect(self.open_pdf)
        toolbar.addAction(open_pdf)

        open_folder = QAction("Open Folder", self)
        open_folder.triggered.connect(self.open_pdf_folder)
        toolbar.addAction(open_folder)

        open_db = QAction("Open DB", self)
        open_db.triggered.connect(self.open_db)
        toolbar.addAction(open_db)

        zoom_out = QAction("Zoom -", self)
        zoom_out.triggered.connect(self.zoom_out)
        toolbar.addAction(zoom_out)

        zoom_fit = QAction("Fit", self)
        zoom_fit.triggered.connect(self.zoom_fit)
        toolbar.addAction(zoom_fit)

        zoom_in = QAction("Zoom +", self)
        zoom_in.triggered.connect(self.zoom_in)
        toolbar.addAction(zoom_in)

        self.high_res_action = QAction("High Res", self)
        self.high_res_action.setCheckable(True)
        self.high_res_action.setChecked(True)
        self.high_res_action.triggered.connect(self.toggle_high_resolution)
        toolbar.addAction(self.high_res_action)

        refresh = QAction("Refresh", self)
        refresh.triggered.connect(self.refresh_from_db)
        toolbar.addAction(refresh)

        export_action = QAction("Export Reviewed", self)
        export_action.triggered.connect(self.export_reviewed)
        toolbar.addAction(export_action)

    def open_pdf(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Open drawing PDFs", "", "PDF files (*.pdf)")
        if not paths:
            return
        pdfs = [Path(path) for path in paths]
        project_db = self._project_db_for_pdfs(pdfs)
        try:
            if len(pdfs) == 1:
                result = ingest_pdf(pdfs[0], db_path=project_db, cache_dir=project_db.parent / "_cache")
                total_pages = result.page_count
                failed_pages = result.failed_pages
            else:
                results = ingest_pdfs(pdfs, db_path=project_db, cache_dir=project_db.parent / "_cache")
                total_pages = sum(result.page_count for result in results)
                failed_pages = sum(result.failed_pages for result in results)
        except Exception as exc:
            QMessageBox.critical(self, "PDF ingest failed", str(exc))
            return
        self.db_path = project_db
        self.current_pdf = pdfs[0]
        self.zoom_factor = 1.0
        self.status_bar.showMessage(f"Indexed {len(pdfs)} PDF(s): {total_pages} page(s), {failed_pages} failed")
        self.refresh_from_db()

    def open_pdf_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open folder containing PDFs")
        if not folder:
            return
        pdfs = find_pdfs(folder)
        if not pdfs:
            QMessageBox.information(self, "No PDFs found", "That folder does not contain PDF files.")
            return
        project_db = Path(folder) / "takeoff_package.takeoff.sqlite"
        try:
            results = ingest_pdfs(pdfs, db_path=project_db, cache_dir=project_db.parent / "_cache")
        except Exception as exc:
            QMessageBox.critical(self, "PDF ingest failed", str(exc))
            return
        self.db_path = project_db
        self.current_pdf = pdfs[0]
        self.zoom_factor = 1.0
        total_pages = sum(result.page_count for result in results)
        failed_pages = sum(result.failed_pages for result in results)
        self.status_bar.showMessage(f"Indexed folder: {len(pdfs)} PDF(s), {total_pages} page(s), {failed_pages} failed")
        self.refresh_from_db()

    def open_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Takeoff project DB", "", "SQLite DB (*.sqlite *.db)")
        if not path:
            return
        self.db_path = Path(path)
        self.refresh_from_db()

    def refresh_from_db(self) -> None:
        if not self.db_path:
            self.status_bar.showMessage("Open a PDF or project DB to begin.")
            return
        self.pages = db.list_pages(self.db_path)
        self.candidates = db.list_candidates(self.db_path)
        self._populate_pages()
        self._populate_candidates()
        self.status_bar.showMessage(f"Loaded {len(self.pages)} page(s), {len(self.candidates)} candidate(s)")

    def _populate_pages(self) -> None:
        self.page_list.clear()
        for page in self.pages:
            label = f"{page['document_name']} - p{page['page_number']} - {page['page_type']}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, page["id"])
            self.page_list.addItem(item)
        if self.pages:
            self.page_list.setCurrentRow(0)

    def _populate_candidates(self) -> None:
        self.candidate_table.setRowCount(len(self.candidates))
        for row, candidate in enumerate(self.candidates):
            values = [
                candidate.get("candidate_status"),
                candidate.get("page_number"),
                candidate.get("normalized_family") or candidate.get("raw_material_phrase"),
                candidate.get("normalized_shape") or candidate.get("raw_shape_phrase"),
                candidate.get("parsed_quantity"),
                candidate.get("normalized_unit") or candidate.get("parsed_unit"),
                candidate.get("confidence"),
                candidate.get("raw_text"),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.UserRole, candidate["id"])
                self.candidate_table.setItem(row, col, item)
        self.candidate_table.resizeColumnsToContents()

    def _page_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.pages):
            return
        self.current_page = self.pages[row]
        self._render_current_page()

    def _render_current_page(self) -> None:
        if not self.current_page:
            return
        pdf_path = Path(self.current_page["document_path"])
        page_number = int(self.current_page["page_number"])
        try:
            with fitz.open(str(pdf_path)) as doc:
                page = doc.load_page(page_number - 1)
                display_scale = self._display_scale_for_page(float(page.rect.width), float(page.rect.height))
                render_scale = self._render_scale(display_scale)
                pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
                image = QPixmap()
                image.loadFromData(pix.tobytes("png"))
                self.viewer.set_page(image, float(page.rect.width), float(page.rect.height), display_scale)
        except Exception as exc:
            self.detail_text.setPlainText(f"Unable to render page: {exc}")
            return
        page_detail = db.get_page(self.db_path, int(self.current_page["id"])) if self.db_path else {}
        text = "\n".join(block.get("text", "") for block in page_detail.get("text_blocks", []))
        self.detail_text.setPlainText(text)
        self.region_label.setText(
            f"Click once to start the red selection window, move, then click once to confirm. "
            f"Zoom: {self.zoom_factor:.2f}x"
        )

    def _region_started(self) -> None:
        self.region_label.setText("Selection started. Move the mouse to size the red window, then click once to confirm.")

    def _region_selected(self, region: tuple) -> None:
        self.region_label.setText(
            f"Confirmed region: x0={region[0]:.1f}, y0={region[1]:.1f}, x1={region[2]:.1f}, y1={region[3]:.1f}. "
            "Click Create From Region to extract evidence."
        )

    def _create_candidate_from_region(self) -> None:
        if not self.db_path or not self.current_page:
            QMessageBox.information(self, "No project", "Open a PDF or project DB first.")
            return
        region = self.viewer.selected_region()
        if not region:
            QMessageBox.information(self, "No region", "Click once on the page, move the mouse, then click again to confirm a red selection window.")
            return
        try:
            candidate_id = create_manual_candidate_from_region(
                self.db_path,
                page_id=int(self.current_page["id"]),
                bbox=region,
                audit_dir=Path(self.db_path).resolve().parent / "_audit",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Manual candidate failed", str(exc))
            return
        self.status_bar.showMessage(f"Created candidate {candidate_id} from manual region.")
        self.refresh_from_db()

    def _current_candidate_id(self) -> Optional[int]:
        row = self.candidate_table.currentRow()
        if row < 0:
            return None
        item = self.candidate_table.item(row, 0)
        return int(item.data(Qt.UserRole)) if item else None

    def _candidate_selection_changed(self) -> None:
        candidate_id = self._current_candidate_id()
        if not candidate_id:
            return
        candidate = next((c for c in self.candidates if int(c["id"]) == candidate_id), None)
        if not candidate:
            return
        self.detail_text.setPlainText(
            "\n".join(
                [
                    f"Raw text: {candidate.get('raw_text') or ''}",
                    f"Material: {candidate.get('raw_material_phrase') or ''} -> {candidate.get('normalized_family') or ''}",
                    f"Shape: {candidate.get('raw_shape_phrase') or ''} -> {candidate.get('normalized_shape') or ''}",
                    f"Dimensions: {candidate.get('raw_dimension_phrase') or ''}",
                    f"Normalization: {candidate.get('normalization_status') or ''}",
                    f"Rules: {candidate.get('normalization_rule_ids') or ''}",
                    f"Evidence: {candidate.get('image_crop_path') or ''}",
                ]
            )
        )

    def _accept_current_candidate(self) -> None:
        if not self.db_path:
            return
        candidate_id = self._current_candidate_id()
        if not candidate_id:
            return
        accept_candidate(self.db_path, candidate_id, reviewed_by=os.environ.get("USERNAME", "local"), notes=self.notes_edit.text())
        self.refresh_from_db()

    def _reject_current_candidate(self) -> None:
        if not self.db_path:
            return
        candidate_id = self._current_candidate_id()
        if not candidate_id:
            return
        reject_candidate(self.db_path, candidate_id, notes=self.notes_edit.text())
        self.refresh_from_db()

    def export_reviewed(self) -> None:
        if not self.db_path:
            QMessageBox.information(self, "No project", "Open a PDF or project DB first.")
            return
        try:
            csv_path = export_csv(self.db_path)
            xlsx_path = export_xlsx(self.db_path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.status_bar.showMessage(f"Exported {csv_path.name} and {xlsx_path.name}")

    def zoom_in(self) -> None:
        self.zoom_factor = min(self.zoom_factor * 1.25, 8.0)
        self._render_current_page()

    def zoom_out(self) -> None:
        self.zoom_factor = max(self.zoom_factor / 1.25, 0.2)
        self._render_current_page()

    def zoom_fit(self) -> None:
        self.zoom_factor = 1.0
        self._render_current_page()

    def toggle_high_resolution(self) -> None:
        self.high_resolution = self.high_res_action.isChecked()
        self._render_current_page()

    def _display_scale_for_page(self, page_width: float, page_height: float) -> float:
        viewport = self.viewer_scroll.viewport().size()
        fit_width = max(viewport.width() - 54, 100) / max(page_width, 1)
        fit_height = max(viewport.height() - 54, 100) / max(page_height, 1)
        fit_scale = min(fit_width, fit_height)
        return max(0.05, min(fit_scale * self.zoom_factor, 12.0))

    def _render_scale(self, display_scale: float) -> float:
        floor = 2.75 if self.high_resolution else 1.35
        return max(0.25, min(max(display_scale, floor), 5.0))

    def _project_db_for_pdfs(self, pdfs: list[Path]) -> Path:
        if self.db_path:
            return self.db_path
        if len(pdfs) == 1:
            return db.default_project_db_for_pdf(pdfs[0])
        try:
            common = Path(os.path.commonpath([str(pdf.parent) for pdf in pdfs]))
        except ValueError:
            common = pdfs[0].parent
        return common / "takeoff_package.takeoff.sqlite"
