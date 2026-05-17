from __future__ import annotations

from pathlib import Path

from app.models.view_models import OCRResult, OCRTextBox
from app.ui.qt_compat import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QColor,
    QLabel,
    QPainter,
    QPen,
    QPixmap,
    QPushButton,
    QRectF,
    QSizePolicy,
    Qt,
    QVBoxLayout,
    QWidget,
    Signal,
)


class _AnnotationGraphicsView(QGraphicsView):
    def __init__(self, owner: "ImageCanvas") -> None:
        super().__init__()
        self._owner = owner
        self.setRenderHints(self.renderHints() | QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFrameShape(QFrame.NoFrame)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            point = event.position().toPoint() if hasattr(event, "position") else event.pos()
            scene_pos = self.mapToScene(point)
            if self._owner.handle_click(scene_pos.x(), scene_pos.y()):
                event.accept()
                return
            self._owner.clear_selection()
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        delta = event.angleDelta().y() if hasattr(event, "angleDelta") else 0
        if delta > 0:
            self._owner.zoom_in()
            event.accept()
            return
        if delta < 0:
            self._owner.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._owner.handle_view_resized()


class ImageCanvas(QWidget):
    text_box_selected = Signal(object)
    selection_cleared = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_path: Path | None = None
        self._pixmap = QPixmap()
        self._ocr_result: OCRResult | None = None
        self._selected_index: int | None = None
        self._rect_items: list[tuple[QGraphicsRectItem, OCRTextBox]] = []
        self._base_pen = QPen(QColor("#4c9e8f"), 2)
        self._selected_pen = QPen(QColor("#d97706"), 3)
        self._zoom_factor = 1.0
        self._zoom_step = 1.15
        self._min_zoom = 0.2
        self._max_zoom = 6.0
        self._keep_fitted = False

        self.title_label = QLabel("图片预览与标注")
        self.title_label.setObjectName("panelTitle")

        self.zoom_out_button = QPushButton("-")
        self.zoom_out_button.setFixedWidth(42)
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setFixedWidth(42)
        self.fit_button = QPushButton("适配窗口")
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("helperText")
        self.zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.scene = QGraphicsScene(self)
        self.graphics_view = _AnnotationGraphicsView(self)
        self.graphics_view.setScene(self.scene)
        self.graphics_view.setSceneRect(QRectF())

        self.empty_label = QLabel("导入图片后在这里预览。\n后续可点击 OCR 文字框并回显到右侧。")
        self.empty_label.setObjectName("imagePreview")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.hint_label = QLabel("支持滚轮缩放、拖拽平移、适配窗口和文字框点击高亮。")
        self.hint_label.setObjectName("helperText")

        frame = QFrame()
        frame.setObjectName("previewFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(16, 16, 16, 16)
        frame_layout.setSpacing(12)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(8)
        toolbar_layout.addWidget(self.zoom_out_button)
        toolbar_layout.addWidget(self.zoom_in_button)
        toolbar_layout.addWidget(self.fit_button)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.zoom_label)

        frame_layout.addLayout(toolbar_layout)
        frame_layout.addWidget(self.empty_label, 1)
        frame_layout.addWidget(self.graphics_view, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.title_label)
        layout.addWidget(frame, 1)
        layout.addWidget(self.hint_label)

        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.fit_button.clicked.connect(self.fit_to_view)

        self._set_canvas_visible(False)
        self._update_zoom_label()

    def set_image(self, image_path: Path | None, ocr_result: OCRResult | None = None) -> None:
        self._current_path = image_path
        self._ocr_result = ocr_result
        self._selected_index = None
        self._rect_items.clear()
        self.scene.clear()
        self._zoom_factor = 1.0
        self._keep_fitted = False

        if image_path is None:
            self._pixmap = QPixmap()
            self._set_canvas_visible(False)
            self.empty_label.setText("导入图片后在这里预览。\n后续可点击 OCR 文字框并回显到右侧。")
            self.hint_label.setText("支持滚轮缩放、拖拽平移、适配窗口和文字框点击高亮。")
            self._update_zoom_label()
            return

        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self._pixmap = QPixmap()
            self._set_canvas_visible(False)
            self.empty_label.setText(f"无法预览图片: {image_path.name}")
            self.hint_label.setText("图片加载失败，当前无法建立预览层。")
            self._update_zoom_label()
            return

        self._pixmap = pixmap
        pixmap_item = QGraphicsPixmapItem(self._pixmap)
        self.scene.addItem(pixmap_item)
        self.scene.setSceneRect(QRectF(self._pixmap.rect()))
        self._draw_annotations()
        self._set_canvas_visible(True)
        self.fit_to_view()

    def handle_click(self, x: float, y: float) -> bool:
        for rect_item, box in reversed(self._rect_items):
            if rect_item.rect().contains(x, y):
                self._select_box(box.index)
                return True
        return False

    def clear_selection(self) -> None:
        if self._selected_index is None:
            return
        self._selected_index = None
        self._refresh_selection_styles()
        self.hint_label.setText("已取消选中，点击任意 OCR 框可重新回显文字。")
        self.selection_cleared.emit()

    def zoom_in(self) -> None:
        self._apply_zoom(self._zoom_step)

    def zoom_out(self) -> None:
        self._apply_zoom(1 / self._zoom_step)

    def fit_to_view(self) -> None:
        if not self.scene.items() or self.scene.sceneRect().isNull():
            self._zoom_factor = 1.0
            self._keep_fitted = False
            self._update_zoom_label()
            return
        self.graphics_view.resetTransform()
        self.graphics_view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom_factor = 1.0
        self._keep_fitted = True
        self._update_zoom_label(fitted=True)

    def handle_view_resized(self) -> None:
        if self._keep_fitted:
            self.fit_to_view()

    def _draw_annotations(self) -> None:
        if self._ocr_result is None:
            self.hint_label.setText("当前图片暂无 OCR 标注结果。")
            return

        for box in self._ocr_result.boxes:
            left, top, right, bottom = box.bounds
            rect_item = QGraphicsRectItem(QRectF(left, top, right - left, bottom - top))
            rect_item.setPen(self._base_pen)
            rect_item.setBrush(QColor(76, 158, 143, 35))
            rect_item.setZValue(1)
            self.scene.addItem(rect_item)
            self._rect_items.append((rect_item, box))

        if self._ocr_result.boxes:
            self.hint_label.setText("可滚轮缩放图片，也可点击标注框高亮并同步右侧文字。")
        else:
            self.hint_label.setText("OCR 结果为空，当前没有可点击的标注框。")

    def _select_box(self, box_index: int) -> None:
        self._selected_index = box_index
        self._refresh_selection_styles()
        for _, box in self._rect_items:
            if box.index == box_index:
                self.hint_label.setText(f"已选中第 {box.index + 1} 个文本框，置信度 {box.score:.3f}")
                self.text_box_selected.emit(box)
                break

    def _refresh_selection_styles(self) -> None:
        for rect_item, box in self._rect_items:
            is_selected = box.index == self._selected_index
            rect_item.setPen(self._selected_pen if is_selected else self._base_pen)
            rect_item.setBrush(QColor(217, 119, 6, 45) if is_selected else QColor(76, 158, 143, 35))

    def _apply_zoom(self, factor: float) -> None:
        if not self.scene.items():
            return
        next_zoom = max(self._min_zoom, min(self._max_zoom, self._zoom_factor * factor))
        actual_factor = next_zoom / self._zoom_factor
        if abs(actual_factor - 1.0) < 1e-6:
            return
        self.graphics_view.scale(actual_factor, actual_factor)
        self._zoom_factor = next_zoom
        self._keep_fitted = False
        self._update_zoom_label()

    def _set_canvas_visible(self, visible: bool) -> None:
        self.empty_label.setVisible(not visible)
        self.graphics_view.setVisible(visible)

    def _update_zoom_label(self, fitted: bool = False) -> None:
        if fitted:
            self.zoom_label.setText("适配")
            return
        self.zoom_label.setText(f"{int(self._zoom_factor * 100)}%")
