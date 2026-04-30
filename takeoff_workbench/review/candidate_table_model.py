from __future__ import annotations

try:
    from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
except Exception:  # pragma: no cover - allows non-Qt test environments.
    QAbstractTableModel = object
    QModelIndex = object
    Qt = None


class CandidateTableModel(QAbstractTableModel):
    columns = [
        "candidate_status",
        "page_number",
        "normalized_family",
        "normalized_shape",
        "parsed_quantity",
        "normalized_unit",
        "confidence",
        "normalization_status",
        "raw_text",
    ]

    def __init__(self, rows: list[dict] | None = None) -> None:
        super().__init__()
        self.rows = rows or []

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(self.columns)

    def data(self, index, role=None):
        if Qt is None or not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        value = self.rows[index.row()].get(self.columns[index.column()])
        return "" if value is None else str(value)

    def headerData(self, section, orientation, role=None):  # noqa: N802
        if Qt is None or role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.columns[section].replace("_", " ").title()
        return str(section + 1)
