from __future__ import annotations

from pathlib import Path

import pandas as pd

from takeoff_workbench.data import db
from takeoff_workbench.export.export_csv import reviewed_lines_dataframe


def export_xlsx(db_path: str | Path, output_path: str | Path | None = None) -> Path:
    if output_path is None:
        output_path = Path(db_path).resolve().parent / "_exports" / "takeoff_export.xlsx"
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    takeoff = reviewed_lines_dataframe(db_path)
    db.init_db(db_path)
    with db.open_db(db_path) as conn:
        needs_review = pd.DataFrame(
            [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT c.*, p.page_number, d.path AS source_pdf, r.image_crop_path
                    FROM material_candidates c
                    JOIN pages p ON p.id = c.page_id
                    JOIN documents d ON d.id = p.document_id
                    LEFT JOIN regions r ON r.id = c.region_id
                    WHERE c.candidate_status IN ('needs_review', 'suggested', 'edited')
                    ORDER BY c.id
                    """
                ).fetchall()
            ]
        )
        rejected = pd.DataFrame(
            [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT c.*, p.page_number, d.path AS source_pdf, r.image_crop_path
                    FROM material_candidates c
                    JOIN pages p ON p.id = c.page_id
                    JOIN documents d ON d.id = p.document_id
                    LEFT JOIN regions r ON r.id = c.region_id
                    WHERE c.candidate_status = 'rejected'
                    ORDER BY c.id
                    """
                ).fetchall()
            ]
        )
        documents = pd.DataFrame([dict(row) for row in conn.execute("SELECT * FROM documents ORDER BY id").fetchall()])
        audit = pd.DataFrame(
            [dict(row) for row in conn.execute("SELECT * FROM app_events ORDER BY id").fetchall()]
        )
        rules = pd.DataFrame(
            [dict(row) for row in conn.execute("SELECT * FROM normalization_rules ORDER BY id").fetchall()]
        )
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        takeoff.to_excel(writer, sheet_name="Takeoff", index=False)
        needs_review.to_excel(writer, sheet_name="Needs Review", index=False)
        rejected.to_excel(writer, sheet_name="Rejected", index=False)
        rules.to_excel(writer, sheet_name="Normalization Rules Used", index=False)
        documents.to_excel(writer, sheet_name="Source Documents", index=False)
        audit.to_excel(writer, sheet_name="Audit Log", index=False)
    return out
