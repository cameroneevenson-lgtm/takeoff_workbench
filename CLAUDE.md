# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this app does

A local Windows desktop assistant for material takeoffs from large PDF drawing packages: indexes PDFs, extracts text/vector evidence, helps identify likely material lines, normalizes messy client terminology, and exports reviewed takeoff rows with page-level evidence. **It is deliberately human-in-the-loop** — it never silently approves extracted quantities and does not rely on cloud LLMs as a source of truth. See `README.md`'s "M1 Scope" section for exactly what is and isn't implemented yet (no DXF analysis, no ML, no cloud LLM interpretation, no automatic approval — table detection is a position-based heuristic for simple BOM-style tables only).

**Local-first by design**: the companion web interface runs on localhost by default; the Cloudflare Tunnel launcher for remote review exists but is never auto-started — it requires deliberate action.

## Commands

Desktop, hot-reload dev mode:

```bat
run_takeoff_workbench.bat
```

Desktop, stable one-shot:

```bat
run_takeoff_workbench_stable.bat
```

Local companion web UI:

```bat
set TAKEOFF_COMPANION_DB=C:\path\to\project.takeoff.sqlite
set TAKEOFF_COMPANION_TOKEN=local-pin
run_companion_local.bat
```

Desktop + companion together:

```bat
run_all_local_dev.bat
```

Tests:

```bat
pytest
pytest tests/test_name.py -k test_name
```

Tests use synthetic fixtures only — never commit real client drawings, project DBs, exports, audit crops, or runtime logs (`.gitignore` already excludes the common cases).

Key env vars (full list in `README.md`): `TAKEOFF_HOT_RELOAD`, `TAKEOFF_OPEN_RECENT_PROJECT`, `TAKEOFF_COMPANION_{DB,HOST,PORT,TOKEN,READONLY}`.

## Architecture

Code lives under the `takeoff_workbench/` package, organized by pipeline stage rather than by UI:
- `ingest/` — PDF/DXF file ingestion, project file indexing, per-page thumbnail caching (`pdf_ingest.py`, `dxf_ingest.py`, `file_index.py`, `page_cache.py`, `package_ingest.py`)
- `extract/` — evidence extraction: `pdf_text_extract.py`, `pdf_vector_extract.py`, `pdf_table_detect.py` (the position-based BOM heuristic), `title_block_extract.py`, `ocr_fallback.py` (PyMuPDF OCR for pages without embedded text), `dxf_geometry_extract.py`, `material_parser.py`
- `normalize/` — turns messy client terminology into canonical values: `material_normalizer.py`, `shape_normalizer.py`, `thickness_normalizer.py`, `unit_normalizer.py`, `client_profile.py`, `learned_rules.py`, orchestrated by `normalization_engine.py`
- `review/` — the human-in-the-loop review layer: `review_model.py`, `candidate_table_model.py`, `evidence_renderer.py`, `review_actions.py`
- `export/` — `export_csv.py`, `export_xlsx.py`, `export_audit_packet.py`
- `data/` — `db.py` (SQLite access) + `schema.sql`, plus reference CSVs (`material_aliases.csv`, `shape_aliases.csv`, `unit_aliases.csv`, `density_table.csv`, `client_profiles.csv`) that back the normalizers above — edits to normalization behavior often belong in these CSVs, not in code
- `companion/` — the optional localhost Flask/Waitress web companion (`flask_app.py`, `waitress_server.py`, `api.py`, `auth.py` — auth is token-gated via `TAKEOFF_COMPANION_TOKEN`) plus `tunnel_notes.md` for the deliberate-only Cloudflare Tunnel path
- `dev/` — hot-reload watcher/relaunch machinery (`file_watcher.py`, `hot_relaunch.py`, `hot_reload_notice.py`)

**Top-level `app_window.py`** (~600 lines) is the PySide6 desktop shell wiring these pipeline stages into the UI; `rendering/pdf_page_renderer.py` defines `PDF_VIEW_DPI` (500) used for high-resolution page preview rendering, imported directly by `app_window.py`.

**Each project is a self-contained `.takeoff.sqlite` file** (schema in `data/schema.sql`) so reviews can be closed and resumed later; `recent_project.py` handles the "reopen most recent project on launch" behavior (disable via `TAKEOFF_OPEN_RECENT_PROJECT=0`).
