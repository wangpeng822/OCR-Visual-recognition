from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.models.view_models import ImageListItem, STATUS_LABELS
from app.ui.qt_compat import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
    Signal,
)


class ImageListPanel(QWidget):
    images_imported = Signal(list)
    selection_changed = Signal(object)
    item_deleted = Signal(object)
    list_cleared = Signal()
    start_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items_by_row: list[ImageListItem] = []

        self.title_label = QLabel("图片任务")
        self.title_label.setObjectName("panelTitle")

        self.summary_label = QLabel("0 张图片")
        self.summary_label.setObjectName("helperText")

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("imageTaskList")
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.currentRowChanged.connect(self._emit_selection)

        self.import_button = QPushButton("导入图片")
        self.start_button = QPushButton("开始识别")
        self.delete_button = QPushButton("删除选中")
        self.clear_button = QPushButton("清空列表")

        self.import_button.clicked.connect(self._pick_files)
        self.start_button.clicked.connect(self.start_requested.emit)
        self.delete_button.clicked.connect(self.delete_current_item)
        self.clear_button.clicked.connect(self.clear_all_items)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(self.import_button)
        action_row.addWidget(self.start_button)

        manage_row = QHBoxLayout()
        manage_row.setSpacing(8)
        manage_row.addWidget(self.delete_button)
        manage_row.addWidget(self.clear_button)

        frame = QFrame()
        frame.setObjectName("leftPanelFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.setSpacing(8)
        frame_layout.addWidget(self.summary_label)
        frame_layout.addWidget(self.list_widget, 1)
        frame_layout.addLayout(action_row)
        frame_layout.addLayout(manage_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.title_label)
        layout.addWidget(frame, 1)

    def _pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if files:
            self.add_images([Path(file) for file in files])

    def add_images(self, paths: list[Path]) -> list[ImageListItem]:
        items: list[ImageListItem] = []
        for path in paths:
            item = ImageListItem(image_id=uuid4().hex, path=path)
            items.append(item)
            self._items_by_row.append(item)

            list_item = QListWidgetItem(self._render_label(item))
            list_item.setData(Qt.UserRole, item)
            self.list_widget.addItem(list_item)

        self._refresh_summary()
        if self.list_widget.count() and self.list_widget.currentRow() < 0:
            self.list_widget.setCurrentRow(0)

        self.images_imported.emit(items)
        return items

    def update_item_status(self, image_id: str, status: str) -> None:
        for row, item in enumerate(self._items_by_row):
            if item.image_id == image_id:
                item.status = status
                widget_item = self.list_widget.item(row)
                if widget_item is not None:
                    widget_item.setText(self._render_label(item))
                break

    def current_item(self) -> ImageListItem | None:
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._items_by_row):
            return None
        return self._items_by_row[row]

    def delete_current_item(self) -> ImageListItem | None:
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._items_by_row):
            return None

        item = self._items_by_row.pop(row)
        removed = self.list_widget.takeItem(row)
        del removed
        self._refresh_summary()

        if self.list_widget.count():
            self.list_widget.setCurrentRow(min(row, self.list_widget.count() - 1))
        else:
            self.selection_changed.emit(None)

        self.item_deleted.emit(item)
        return item

    def clear_all_items(self) -> None:
        if not self._items_by_row:
            return
        self._items_by_row.clear()
        self.list_widget.clear()
        self._refresh_summary()
        self.selection_changed.emit(None)
        self.list_cleared.emit()

    def _emit_selection(self, row: int) -> None:
        if row < 0 or row >= len(self._items_by_row):
            self.selection_changed.emit(None)
            return
        self.selection_changed.emit(self._items_by_row[row])

    def _refresh_summary(self) -> None:
        self.summary_label.setText(f"{len(self._items_by_row)} 张图片")

    @staticmethod
    def _render_label(item: ImageListItem) -> str:
        status_label = STATUS_LABELS.get(item.status, item.status)
        return f"[{status_label}] {item.filename}"
