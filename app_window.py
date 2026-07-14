from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
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
from takeoff_workbench.formatting import format_quantity
from takeoff_workbench.ingest.file_index import find_pdfs
from takeoff_workbench.ingest.package_ingest import ingest_pdfs
from takeoff_workbench.ingest.pdf_ingest import ingest_pdf
from takeoff_workbench.dev.hot_reload_controller import HotReloadController
from rendering.page_render_cache import PageRenderCache
from rendering.pdf_page_renderer import RenderedPage, _bucket_px
from takeoff_workbench.recent_project import read_recent_project, write_recent_project
from takeoff_workbench.review.review_actions import (
    accept_candidate,
    create_manual_candidates_from_region,
    reject_candidate,
)
from widgets.page_viewer import PageViewer


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
        self.visible_candidates: list[dict] = []
        self._page_render_cache = PageRenderCache()
        self._build_ui()
        self._build_actions()
        self._build_hot_reload_timer()
        self._update_window_title()
        QTimer.singleShot(0, self.open_recent_project_on_launch)

    def _build_ui(self) -> None:
        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        self.hot_reload_banner = QLabel("")
        self.hot_reload_banner.setVisible(False)
        self.hot_reload_banner.setAlignment(Qt.AlignCenter)
        self.hot_reload_banner.setStyleSheet(
            "QLabel { background: #fff2a8; color: #4f3b00; border-bottom: 1px solid #d8b640; "
            "font-weight: 600; padding: 8px 12px; }"
        )
        shell_layout.addWidget(self.hot_reload_banner)
        root = QSplitter(Qt.Horizontal)
        shell_layout.addWidget(root, 1)
        self.setCentralWidget(shell)

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
        center_layout.addWidget(self.viewer, 1)
        self.region_label = QLabel("Click once to start the red selection window. Move the mouse, then click once to confirm it.")
        center_layout.addWidget(self.region_label)
        center_layout.addWidget(QLabel("Evidence Details"))
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        center_layout.addWidget(self.detail_text, 0)
        root.addWidget(center)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.candidate_header = QLabel("Candidates on Selected Page (0)")
        right_layout.addWidget(self.candidate_header)
        self.candidate_table = QTableWidget(0, 5)
        self.candidate_table.setHorizontalHeaderLabels(
            ["Status", "Material", "Shape", "Qty", "Source Text"]
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
        self.clear_candidates_button = QPushButton("Clear Page Candidates")
        self.clear_candidates_button.clicked.connect(self.clear_current_page_candidates)
        buttons.addWidget(self.clear_candidates_button)
        right_layout.addLayout(buttons)
        right_layout.addWidget(QLabel("Notes"))
        self.notes_edit = QLineEdit()
        right_layout.addWidget(self.notes_edit)
        root.addWidget(right)
        root.setSizes([260, 760, 420])

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _build_hot_reload_timer(self) -> None:
        self._hot_reload_controller = HotReloadController(
            self.hot_reload_banner,
            app_root=Path(__file__).resolve().parent,
        )
        self._hot_reload_controller.start()

    def _build_actions(self) -> None:
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)

        new_project = QAction("New Project", self)
        new_project.triggered.connect(self.new_project)
        toolbar.addAction(new_project)

        open_project = QAction("Open Project", self)
        open_project.triggered.connect(self.open_db)
        toolbar.addAction(open_project)

        save_project_as = QAction("Save Project As", self)
        save_project_as.triggered.connect(self.save_project_as)
        toolbar.addAction(save_project_as)

        open_pdf = QAction("Open PDFs", self)
        open_pdf.triggered.connect(self.open_pdf)
        toolbar.addAction(open_pdf)

        open_folder = QAction("Open Folder", self)
        open_folder.triggered.connect(self.open_pdf_folder)
        toolbar.addAction(open_folder)

        remove_pdf = QAction("Remove PDF", self)
        remove_pdf.triggered.connect(self.remove_current_pdf)
        toolbar.addAction(remove_pdf)

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
            removed_stale = db.remove_documents_not_in_paths(project_db, pdfs)
        except Exception as exc:
            QMessageBox.critical(self, "PDF ingest failed", str(exc))
            return
        self.db_path = project_db
        self._remember_current_project()
        self.current_pdf = pdfs[0]
        stale_note = f", removed {len(removed_stale)} stale PDF(s)" if removed_stale else ""
        self.status_bar.showMessage(
            f"Indexed {len(pdfs)} selected PDF(s): {total_pages} page(s), {failed_pages} failed{stale_note}"
        )
        self.refresh_from_db()

    def open_pdf_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open folder containing PDFs")
        if not folder:
            return
        pdfs = find_pdfs(folder)
        if not pdfs:
            QMessageBox.information(self, "No PDFs found", "That folder does not contain PDF files.")
            return
        project_db = self.db_path or (Path(folder) / "takeoff_package.takeoff.sqlite")
        try:
            results = ingest_pdfs(pdfs, db_path=project_db, cache_dir=project_db.parent / "_cache")
        except Exception as exc:
            QMessageBox.critical(self, "PDF ingest failed", str(exc))
            return
        self.db_path = project_db
        self._remember_current_project()
        self.current_pdf = pdfs[0]
        total_pages = sum(result.page_count for result in results)
        failed_pages = sum(result.failed_pages for result in results)
        self.status_bar.showMessage(f"Indexed folder: {len(pdfs)} PDF(s), {total_pages} page(s), {failed_pages} failed")
        self.refresh_from_db()

    def new_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Create Takeoff project",
            "",
            "Takeoff project (*.takeoff.sqlite);;SQLite DB (*.sqlite *.db)",
        )
        if not path:
            return
        project_db = db.ensure_project_suffix(path)
        try:
            db.init_db(project_db)
            db.log_event(project_db, "project_created", f"Project created: {project_db}")
        except Exception as exc:
            QMessageBox.critical(self, "Project create failed", str(exc))
            return
        self.db_path = project_db
        self._remember_current_project()
        self.current_page = None
        self.current_pdf = None
        self.pages = []
        self.candidates = []
        self.visible_candidates = []
        self.refresh_from_db()
        self.status_bar.showMessage(f"Project file ready: {project_db}")

    def open_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Takeoff project",
            "",
            "Takeoff project (*.takeoff.sqlite);;SQLite DB (*.sqlite *.db)",
        )
        if not path:
            return
        self.db_path = Path(path)
        self._remember_current_project()
        self.refresh_from_db()

    def save_project_as(self) -> None:
        if not self.db_path:
            self.new_project()
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Takeoff project as",
            str(self.db_path.with_name(f"{self.db_path.stem}_copy.takeoff.sqlite")),
            "Takeoff project (*.takeoff.sqlite);;SQLite DB (*.sqlite *.db)",
        )
        if not path:
            return
        try:
            saved = db.backup_project_db(self.db_path, path)
        except Exception as exc:
            QMessageBox.critical(self, "Project save failed", str(exc))
            return
        self.db_path = saved
        self._remember_current_project()
        self.refresh_from_db()
        self.status_bar.showMessage(f"Project saved as {saved}")

    def open_recent_project_on_launch(self) -> None:
        if self.db_path or os.environ.get("TAKEOFF_OPEN_RECENT_PROJECT", "1") == "0":
            return
        recent = read_recent_project(state_file=self._recent_project_state_path())
        if not recent:
            self.status_bar.showMessage("Open a PDF or project DB to begin.")
            return
        self.db_path = recent
        try:
            self.refresh_from_db()
        except Exception as exc:
            self.db_path = None
            self._update_window_title()
            self.status_bar.showMessage(f"Recent project could not be opened: {exc}")
            return
        self.status_bar.showMessage(f"Reopened recent project: {recent}")

    def remove_current_pdf(self) -> None:
        if not self.db_path or not self.current_page:
            QMessageBox.information(self, "No PDF selected", "Select a page from the PDF you want to remove.")
            return
        document_id = int(self.current_page["document_id"])
        document_name = self.current_page.get("document_name") or self.current_page.get("document_path") or "selected PDF"
        answer = QMessageBox.question(
            self,
            "Remove PDF from project",
            (
                f"Remove {document_name} from this takeoff project?\n\n"
                "This removes its indexed pages, regions, candidates, and reviewed lines from the project DB. "
                "It does not delete the PDF file from disk."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        removed = db.remove_document(self.db_path, document_id)
        if not removed:
            QMessageBox.information(self, "PDF not found", "That PDF was not found in the project DB.")
            return
        self.status_bar.showMessage(f"Removed {removed.get('display_name') or removed.get('path')} from project.")
        self.refresh_from_db()

    def clear_current_page_candidates(self) -> None:
        if not self.db_path or not self.current_page:
            QMessageBox.information(self, "No page selected", "Select the page whose candidates you want to clear.")
            return
        page_label = f"{self.current_page.get('document_name')} p{self.current_page.get('page_number')}"
        answer = QMessageBox.question(
            self,
            "Clear page candidates",
            (
                f"Clear all candidates and reviewed lines for {page_label}?\n\n"
                "This keeps the PDF page and extracted source text, but removes candidate rows and red saved regions."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        counts = db.clear_candidates_for_page(self.db_path, int(self.current_page["id"]))
        self.viewer.clear_selection()
        self.refresh_from_db()
        self._render_current_page()
        self.status_bar.showMessage(
            f"Cleared {counts['candidates']} candidate(s), {counts['takeoff_lines']} reviewed line(s), "
            f"and {counts['regions']} region(s) from {page_label}."
        )

    def refresh_from_db(self) -> None:
        if not self.db_path:
            self.status_bar.showMessage("Open a PDF or project DB to begin.")
            self._update_window_title()
            return
        selected_page_id = int(self.current_page["id"]) if self.current_page else None
        self.pages = db.list_pages(self.db_path)
        self.candidates = db.list_candidates(self.db_path)
        if not self.pages:
            self.current_page = None
        self._populate_pages(selected_page_id)
        self._populate_candidates()
        if not self.pages:
            self.viewer.clear_selection()
            self.detail_text.setPlainText("")
        self._update_window_title()
        self.status_bar.showMessage(f"Loaded {len(self.pages)} page(s), {len(self.candidates)} candidate(s)")

    def _populate_pages(self, selected_page_id: int | None = None) -> None:
        self.page_list.clear()
        selected_row = 0
        for page in self.pages:
            label = f"{page['document_name']} - p{page['page_number']} - {page['page_type']}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, page["id"])
            self.page_list.addItem(item)
            if selected_page_id is not None and int(page["id"]) == selected_page_id:
                selected_row = self.page_list.count() - 1
        if self.pages:
            self.page_list.setCurrentRow(selected_row)

    def _populate_candidates(self) -> None:
        if self.current_page:
            page_id = int(self.current_page["id"])
            self.visible_candidates = [
                candidate for candidate in self.candidates if int(candidate.get("page_id") or 0) == page_id
            ]
            page_label = f"{self.current_page['document_name']} p{self.current_page['page_number']}"
            self.candidate_header.setText(f"Candidates on Selected Page ({len(self.visible_candidates)}) - {page_label}")
        else:
            self.visible_candidates = []
            self.candidate_header.setText("Candidates on Selected Page (0)")
        self.candidate_table.setRowCount(len(self.visible_candidates))
        for row, candidate in enumerate(self.visible_candidates):
            values = [
                candidate.get("candidate_status"),
                candidate.get("normalized_family") or candidate.get("raw_material_phrase"),
                candidate.get("normalized_shape") or candidate.get("raw_shape_phrase"),
                format_quantity(candidate.get("parsed_quantity")),
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
        self._populate_candidates()

    def _render_current_page(self) -> None:
        if not self.current_page:
            return
        pdf_path = Path(self.current_page["document_path"])
        page_number = int(self.current_page["page_number"])
        try:
            rendered = self._render_page_cached(pdf_path, page_number)
            self.viewer.set_page(
                rendered.pixmap,
                rendered.page_width,
                rendered.page_height,
                rendered.render_scale,
            )
            self.viewer.set_persisted_regions(db.list_regions_for_page(self.db_path, int(self.current_page["id"])))
        except Exception as exc:
            self.detail_text.setPlainText(f"Unable to render page: {exc}")
            return
        page_detail = db.get_page(self.db_path, int(self.current_page["id"])) if self.db_path else {}
        text = "\n".join(block.get("text", "") for block in page_detail.get("text_blocks", []))
        self.detail_text.setPlainText(text)
        self.region_label.setText(
            "Click once to start the red selection window, move, then click once to confirm. "
            "Use the scroll wheel to zoom; middle-click resets to fit."
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
            candidate_ids = create_manual_candidates_from_region(
                self.db_path,
                page_id=int(self.current_page["id"]),
                bbox=region,
                audit_dir=Path(self.db_path).resolve().parent / "_audit",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Manual candidate failed", str(exc))
            return
        if candidate_ids:
            self.status_bar.showMessage(f"Created {len(candidate_ids)} candidate(s) from manual region.")
        else:
            self.status_bar.showMessage("No new candidates created; overlapping duplicate rows were skipped.")
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

    def _render_page_cached(self, pdf_path: Path, page_number: int) -> RenderedPage:
        viewport = self.viewer.viewport().size()
        vw = _bucket_px(max(viewport.width(), 960))
        vh = _bucket_px(max(viewport.height(), 720))
        return self._page_render_cache.get_or_render(pdf_path, page_number, vw, vh)

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

    def _update_window_title(self) -> None:
        if self.db_path:
            self.setWindowTitle(f"Takeoff Workbench - {self.db_path.name}")
        else:
            self.setWindowTitle("Takeoff Workbench")

    def _remember_current_project(self) -> None:
        if not self.db_path:
            return
        try:
            write_recent_project(self.db_path, state_file=self._recent_project_state_path())
        except OSError as exc:
            self.status_bar.showMessage(f"Could not save recent project setting: {exc}")

    def _recent_project_state_path(self) -> Path:
        runtime = Path(os.environ.get("TAKEOFF_RUNTIME_DIR", "_runtime"))
        if not runtime.is_absolute():
            runtime = Path(__file__).resolve().parent / runtime
        return runtime / "recent_project.json"

