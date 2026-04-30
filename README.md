# Takeoff Workbench

Takeoff Workbench is a local Windows desktop assistant for material takeoffs from
large drawing packages. It indexes PDF drawing sets, extracts text/vector evidence,
helps the user identify likely material lines, normalizes messy client terminology,
and exports reviewed takeoff rows with page-level evidence.

The tool is intentionally human-in-the-loop. It does not silently approve extracted
quantities or rely on cloud LLMs as the source of truth.

The app is local-first. The companion web interface runs on localhost by default.
An optional Cloudflare Tunnel launcher is provided for deliberate remote review,
but tunnels are never auto-started.

## M1 Scope

M1 is the local PDF evidence rail:

- Open and index PDF files.
- Open several PDFs into one local project DB.
- Store deterministic extraction evidence in SQLite.
- Render thumbnails and high-resolution selected page previews with zoom.
- Let a user click once to start a manual evidence window and click again to confirm it.
- Attempt PyMuPDF OCR on pages/regions that do not contain embedded PDF text.
- Create a manually reviewed takeoff line from that region.
- Export reviewed lines to CSV and Excel.
- Run a localhost Flask/Waitress companion app when explicitly launched.
- Provide a Cloudflare Tunnel launcher that must be started deliberately.

M1 does not implement OCR, DXF analysis, ML, cloud LLM interpretation, automatic
approval, or complex table extraction.

## Launch

Desktop hot-reload development mode:

```bat
run_takeoff_workbench.bat
```

Stable one-shot desktop mode:

```bat
run_takeoff_workbench_stable.bat
```

Local companion:

```bat
set TAKEOFF_COMPANION_DB=C:\path\to\project.takeoff.sqlite
set TAKEOFF_COMPANION_TOKEN=local-pin
run_companion_local.bat
```

The default companion URL is:

```text
http://127.0.0.1:8787
```

Optional tunnel, only when intentionally launched:

```bat
run_companion_tunnel.bat
```

## Environment

- `TAKEOFF_HOT_RELOAD=1` enables desktop hot relaunch.
- `TAKEOFF_HOT_RELOAD=0` runs the desktop once.
- `TAKEOFF_RUNTIME_DIR=_runtime` controls launcher logs.
- `TAKEOFF_COMPANION_DB` points to the selected project SQLite DB.
- `TAKEOFF_COMPANION_HOST=127.0.0.1` is the local-first default.
- `TAKEOFF_COMPANION_PORT=8787` is the default companion port.
- `TAKEOFF_COMPANION_TOKEN` gates companion write actions.
- `TAKEOFF_COMPANION_READONLY=1` forces companion read-only mode.

## Development

Install dependencies in a virtual environment, then run:

```bat
pytest
```

Tests use synthetic fixtures only. Do not commit client drawings, project DBs,
exports, audit crops, or runtime logs.
