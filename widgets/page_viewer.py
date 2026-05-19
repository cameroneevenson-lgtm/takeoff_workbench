from __future__ import annotations

from typing import Mapping, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView


class PageViewer(QGraphicsView):
    region_selected = Signal(tuple)
    region_started = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pix_item = QGraphicsPixmapItem()
        self._pix_item.setTransformationMode(Qt.FastTransformation)
        self._scene.addItem(self._pix_item)
        self._selection_item = QGraphicsRectItem()
        pen = QPen(QColor("#d24b2a"), 2, Qt.DashLine)
        pen.setCosmetic(True)
        self._selection_item.setPen(pen)
        self._selection_item.setVisible(False)
        self._scene.addItem(self._selection_item)
        self._persisted_region_items: list[QGraphicsRectItem] = []
        self._page_width = 1.0
        self._page_height = 1.0
        self._render_scale = 1.0
        self._selection_anchor: Optional[QPointF] = None
        self._last_region: Optional[tuple[float, float, float, float]] = None
        self._user_zoom = 1.0
        self._baseline_scale = 1.0
        self.setMinimumSize(640, 480)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        hints = QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform
        if hasattr(QPainter, "LosslessImageRendering"):
            hints |= QPainter.LosslessImageRendering
        self.setRenderHints(hints)
        self.setStyleSheet("QGraphicsView { background: #202428; }")

    def set_page(
        self,
        pixmap: QPixmap,
        page_width: float,
        page_height: float,
        render_scale: float,
        *,
        reset_zoom: bool = True,
    ) -> None:
        self._pix_item.setPixmap(pixmap)
        self._page_width = max(float(page_width or 1.0), 1.0)
        self._page_height = max(float(page_height or 1.0), 1.0)
        self._render_scale = max(float(render_scale or 1.0), 0.01)
        self._scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self.clear_selection()
        if reset_zoom:
            self._user_zoom = 1.0
        self._recompute_baseline_and_apply()

    def selected_region(self) -> Optional[tuple[float, float, float, float]]:
        return self._last_region

    def clear_selection(self) -> None:
        self._last_region = None
        self._selection_anchor = None
        self._selection_item.setVisible(False)

    def set_persisted_regions(self, regions: list[dict]) -> None:
        for item in self._persisted_region_items:
            self._scene.removeItem(item)
        self._persisted_region_items = []
        pen = QPen(QColor("#d24b2a"), 2, Qt.SolidLine)
        pen.setCosmetic(True)
        brush = QBrush(QColor(210, 75, 42, 28))
        for region in regions:
            rect = self._page_region_to_scene_rect(region)
            if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
                continue
            item = QGraphicsRectItem(rect)
            item.setPen(pen)
            item.setBrush(brush)
            item.setZValue(5)
            self._scene.addItem(item)
            self._persisted_region_items.append(item)
        self._selection_item.setZValue(10)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MiddleButton:
            self.reset_to_fit()
            event.accept()
            return
        if event.button() != Qt.LeftButton or self._pix_item.pixmap().isNull():
            super().mousePressEvent(event)
            return
        point = self.mapToScene(event.position().toPoint())
        if not self._scene.sceneRect().contains(point):
            return
        if self._selection_anchor is None:
            self._selection_anchor = point
            self._last_region = None
            self._selection_item.setRect(QRectF(point, point).normalized())
            self._selection_item.setVisible(True)
            self.region_started.emit()
        else:
            rect = QRectF(self._selection_anchor, point).normalized().intersected(self._scene.sceneRect())
            region = self._scene_rect_to_page(rect)
            if region:
                self._last_region = region
                self._selection_item.setRect(rect)
                self._selection_item.setVisible(True)
                self.region_selected.emit(region)
            self._selection_anchor = None
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._selection_anchor:
            point = self.mapToScene(event.position().toPoint())
            rect = QRectF(self._selection_anchor, point).normalized().intersected(self._scene.sceneRect())
            self._selection_item.setRect(rect)
            self._selection_item.setVisible(True)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return
        factor = 1.12 if delta > 0 else 1 / 1.12
        cursor = event.position().toPoint()
        before = self.mapToScene(cursor)
        self._user_zoom = max(0.08, min(self._user_zoom * factor, 30.0))
        self._apply_current_zoom()
        after = self.mapToScene(cursor)
        delta_scene = after - before
        self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() + delta_scene.x() * self.transform().m11()))
        self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() + delta_scene.y() * self.transform().m22()))
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.clear_selection()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._recompute_baseline_and_apply()

    def reset_to_fit(self) -> None:
        self._user_zoom = 1.0
        self._recompute_baseline_and_apply()

    def _scene_rect_to_page(self, rect: QRectF) -> Optional[tuple[float, float, float, float]]:
        if rect.width() < 4 or rect.height() < 4:
            return None
        x0 = rect.left() / self._render_scale
        y0 = rect.top() / self._render_scale
        x1 = rect.right() / self._render_scale
        y1 = rect.bottom() / self._render_scale
        return (x0, y0, x1, y1)

    def _page_region_to_scene_rect(self, region: Mapping) -> QRectF:
        x0 = float(region.get("x0") or 0) * self._render_scale
        y0 = float(region.get("y0") or 0) * self._render_scale
        x1 = float(region.get("x1") or 0) * self._render_scale
        y1 = float(region.get("y1") or 0) * self._render_scale
        return QRectF(QPointF(x0, y0), QPointF(x1, y1)).normalized()

    def _recompute_baseline_and_apply(self) -> None:
        pixmap = self._pix_item.pixmap()
        if pixmap.isNull():
            self._baseline_scale = 1.0
            self._apply_current_zoom()
            return
        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())
        self._baseline_scale = min(vw / max(1, pixmap.width()), vh / max(1, pixmap.height()))
        self._apply_current_zoom()

    def _apply_current_zoom(self) -> None:
        scale = max(0.02, self._baseline_scale * self._user_zoom)
        self.resetTransform()
        self.scale(scale, scale)
