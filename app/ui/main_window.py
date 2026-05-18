from __future__ import annotations

from pathlib import Path

from app.models.nfc_models import NfcDeviceState, NfcRecord
from app.models.view_models import ImageListItem, ImageTaskStatus, OCRResult, OCRTextBox
from app.services.nfc_service import NfcService
from app.services.ocr_service import OCRService
from app.ui.image_canvas import ImageCanvas
from app.ui.image_list_panel import ImageListPanel
from app.ui.qt_compat import (
    QAction,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QThread,
    QVBoxLayout,
    QWidget,
)
from app.ui.sidebar import RightSidebar
from app.workers.ocr_worker import OCRWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCR + NFC Desktop")
        self.resize(1480, 900)

        self.image_list_panel = ImageListPanel()
        self.image_canvas = ImageCanvas()
        self.right_sidebar = RightSidebar()
        self.nfc_service = NfcService(self)
        self.ocr_service = OCRService(Path(__file__).resolve().parents[2])
        self.ocr_thread: QThread | None = None
        self.ocr_worker: OCRWorker | None = None
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self._build_ui()
        self._build_menu()
        self._wire_events()
        self._apply_styles()
        self.right_sidebar.set_nfc_snapshot(self.nfc_service.state)
        self.statusBar().showMessage(f"OCR backend: {self.ocr_service.backend.name}")

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        header_label = QLabel("OCR 批处理与 NFC 编号工具")
        header_label.setObjectName("heroTitle")

        sub_label = QLabel("当前支持图片列表、预览标注、右侧结果栏，以及 OCR/NFC 联调入口。")
        sub_label.setObjectName("helperText")

        splitter = QSplitter()
        splitter.addWidget(self.image_list_panel)
        splitter.addWidget(self.image_canvas)
        splitter.addWidget(self.right_sidebar)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 6)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([280, 740, 420])

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)
        root_layout.addWidget(header_label)
        root_layout.addWidget(sub_label)
        root_layout.addWidget(splitter, 1)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        status_bar.showMessage("就绪")
        status_bar.addPermanentWidget(QLabel("批处理进度"))
        status_bar.addPermanentWidget(self.progress_bar, 1)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件")

        import_action = QAction("导入图片", self)
        import_action.triggered.connect(self.image_list_panel.import_button.click)

        file_menu.addAction(import_action)

    def _wire_events(self) -> None:
        self.image_list_panel.selection_changed.connect(self._on_image_selected)
        self.image_list_panel.images_imported.connect(self._on_images_imported)
        self.image_list_panel.item_deleted.connect(self._on_image_deleted)
        self.image_list_panel.list_cleared.connect(self._on_image_list_cleared)
        self.image_list_panel.start_requested.connect(self._on_start_requested)

        self.image_canvas.text_box_selected.connect(self._on_text_box_selected)
        self.image_canvas.selection_cleared.connect(self._on_canvas_selection_cleared)

        self.right_sidebar.fill_text_from_nfc_requested.connect(self._on_fill_text_from_nfc)
        self.right_sidebar.nfc_connect_requested.connect(self._on_nfc_connect_requested)
        self.right_sidebar.nfc_read_requested.connect(self._on_nfc_read_requested)
        self.right_sidebar.nfc_write_requested.connect(self._on_nfc_write_requested)

        self.nfc_service.state_changed.connect(self._on_nfc_state_changed)
        self.nfc_service.record_added.connect(self._on_nfc_record_added)
        self.nfc_service.error_occurred.connect(self._on_nfc_error)
        self.nfc_service.error_details.connect(self._on_nfc_error_details)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f3efe6;
            }
            QLabel#heroTitle {
                font-size: 24px;
                font-weight: 700;
                color: #1f2a2a;
            }
            QLabel#panelTitle {
                font-size: 16px;
                font-weight: 650;
                color: #213547;
            }
            QLabel#helperText {
                color: #5f6b6d;
            }
            QLabel#statusChip {
                background: #d8ead6;
                color: #244227;
                border-radius: 10px;
                padding: 4px 10px;
                font-weight: 600;
            }
            QFrame#leftPanelFrame, QFrame#previewFrame, QGroupBox {
                background: #fffdf8;
                border: 1px solid #d9d0c3;
                border-radius: 14px;
            }
            QGroupBox {
                margin-top: 8px;
                padding-top: 12px;
                font-weight: 650;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            QListWidget#imageTaskList {
                border: none;
                background: transparent;
            }
            QListWidget#imageTaskList::item {
                padding: 10px 12px;
                margin-bottom: 6px;
                border-radius: 10px;
                background: #f7f1e7;
            }
            QListWidget#imageTaskList::item:selected {
                background: #dce8d2;
                color: #1d2c1f;
            }
            QLabel#imagePreview {
                color: #73808a;
                font-size: 16px;
                border: 2px dashed #d7c9b0;
                border-radius: 16px;
                background: #faf7f2;
            }
            QPushButton {
                background: #284b63;
                color: white;
                border: none;
                padding: 9px 14px;
                border-radius: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #34627f;
            }
            QLineEdit, QTextEdit {
                background: #fffdf8;
                border: 1px solid #d9d0c3;
                border-radius: 10px;
                padding: 8px;
            }
            QTextEdit#selectedTextPreview {
                font-size: 20px;
                font-weight: 650;
                color: #182f2d;
                line-height: 1.35;
            }
            QSplitter::handle {
                background: #e0d8cc;
                width: 6px;
            }
            """
        )

    def _on_images_imported(self, items: list[ImageListItem]) -> None:
        self.statusBar().showMessage(f"已导入 {len(items)} 张图片")

    def _on_image_selected(self, item: ImageListItem | None) -> None:
        if item is None:
            self.image_canvas.set_image(None)
            self.right_sidebar.set_selected_text("")
            return

        self.image_canvas.set_image(item.path, item.ocr_result)
        self.right_sidebar.set_selected_text(item.selected_text or "", item.selected_score)
        self.statusBar().showMessage(f"当前图片: {item.filename}")

    def _on_image_deleted(self, item: ImageListItem) -> None:
        if not self.image_list_panel._items_by_row:
            self.image_canvas.set_image(None)
            self.right_sidebar.set_selected_text("")
            self.progress_bar.setValue(0)
        self.statusBar().showMessage(f"已删除图片任务: {item.filename}")

    def _on_image_list_cleared(self) -> None:
        self.image_canvas.set_image(None)
        self.right_sidebar.set_selected_text("")
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("图片任务列表已清空")

    def _on_text_box_selected(self, box: OCRTextBox) -> None:
        current_item = self.image_list_panel.current_item()
        if current_item is None:
            return
        current_item.selected_text = box.text
        current_item.selected_score = box.score
        self.right_sidebar.set_selected_text(box.text, box.score)
        self.statusBar().showMessage(f"已选中第 {box.index + 1} 个文本框: {box.text}")

    def _on_canvas_selection_cleared(self) -> None:
        current_item = self.image_list_panel.current_item()
        if current_item is not None:
            current_item.selected_text = ""
            current_item.selected_score = None
        self.right_sidebar.set_selected_text("")
        self.statusBar().showMessage("已取消文本框选中")

    def _on_start_requested(self) -> None:
        if self.ocr_thread is not None:
            self.statusBar().showMessage("OCR 正在执行，请等待当前批次完成")
            return

        tasks = [(item.image_id, item.path) for item in self.image_list_panel._items_by_row]
        if not tasks:
            QMessageBox.information(self, "提示", "请先导入图片")
            return

        for item in self.image_list_panel._items_by_row:
            item.status = ImageTaskStatus.PENDING
            item.error = ""
            item.selected_text = ""
            item.selected_score = None
            item.full_text = ""
            item.ocr_result = None
            self.image_list_panel.update_item_status(item.image_id, item.status)

        self.progress_bar.setValue(0)
        self.statusBar().showMessage(f"开始 OCR 识别，backend: {self.ocr_service.backend.name}")

        self.ocr_thread = QThread(self)
        self.ocr_worker = OCRWorker(tasks, self.ocr_service)
        self.ocr_worker.moveToThread(self.ocr_thread)
        self.ocr_thread.started.connect(self.ocr_worker.run)
        self.ocr_worker.item_started.connect(self._on_ocr_item_started)
        self.ocr_worker.item_completed.connect(self._on_ocr_item_completed)
        self.ocr_worker.item_failed.connect(self._on_ocr_item_failed)
        self.ocr_worker.batch_finished.connect(self._on_ocr_batch_finished)
        self.ocr_worker.batch_finished.connect(self.ocr_thread.quit)
        self.ocr_thread.finished.connect(self._cleanup_ocr_worker)
        self.ocr_thread.start()

    def _on_fill_text_from_nfc(self, text: str) -> None:
        self.right_sidebar.set_selected_text(text)
        current_item = self.image_list_panel.current_item()
        if current_item is not None:
            current_item.selected_text = text
            current_item.selected_score = None
        self.statusBar().showMessage("已将 NFC 编号回填到当前文本")

    def _on_nfc_connect_requested(self) -> None:
        self.nfc_service.connect_reader()
        self.statusBar().showMessage("正在连接 NFC 设备")

    def _on_nfc_read_requested(self) -> None:
        self.nfc_service.read_tag()
        self.statusBar().showMessage("正在读取 NFC UID")

    def _on_nfc_write_requested(self, value: str) -> None:
        if not value:
            QMessageBox.warning(self, "提示", "待写入编号不能为空")
            return
        self.nfc_service.write_tag(value)

    def _on_nfc_state_changed(self, state: NfcDeviceState) -> None:
        self.right_sidebar.set_nfc_snapshot(state)

    def _on_nfc_record_added(self, record: NfcRecord) -> None:
        self.right_sidebar.append_nfc_record(record)
        self.statusBar().showMessage(record.display_text)

    def _on_nfc_error(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _on_nfc_error_details(self, error) -> None:
        title = "NFC 提示"
        detail = error.user_message
        if error.error_code:
            detail = f"{detail}\n错误码: {error.error_code}"

        if error.severity == "critical":
            QMessageBox.critical(self, title, detail)
            return
        if error.severity == "info":
            QMessageBox.information(self, title, detail)
            return
        QMessageBox.warning(self, title, detail)

    def _on_ocr_item_started(self, image_id: str, current: int, total: int) -> None:
        item = self._find_item(image_id)
        if item is None:
            return
        item.status = ImageTaskStatus.PROCESSING
        self.image_list_panel.update_item_status(image_id, item.status)
        self.progress_bar.setValue(max(1, int(((current - 1) / max(total, 1)) * 100)))
        self.statusBar().showMessage(f"正在识别 {item.filename} ({current}/{total})")

    def _on_ocr_item_completed(self, image_id: str, result: OCRResult) -> None:
        item = self._find_item(image_id)
        if item is None:
            return
        item.status = ImageTaskStatus.DONE
        item.error = ""
        item.ocr_result = result
        item.full_text = result.full_text
        item.selected_text = ""
        item.selected_score = None
        self.image_list_panel.update_item_status(image_id, item.status)

        current_item = self.image_list_panel.current_item()
        if current_item is not None and current_item.image_id == image_id:
            self.image_canvas.set_image(item.path, item.ocr_result)
            self.right_sidebar.set_selected_text("")

    def _on_ocr_item_failed(self, image_id: str, message: str) -> None:
        item = self._find_item(image_id)
        if item is None:
            return
        item.status = ImageTaskStatus.FAILED
        item.error = message
        item.ocr_result = None
        item.full_text = ""
        item.selected_text = ""
        item.selected_score = None
        self.image_list_panel.update_item_status(image_id, item.status)

        current_item = self.image_list_panel.current_item()
        if current_item is not None and current_item.image_id == image_id:
            self.image_canvas.set_image(item.path, None)
            self.right_sidebar.set_selected_text("")
        self.statusBar().showMessage(f"{item.filename} 识别失败: {message}")

    def _on_ocr_batch_finished(self, completed: int, failed: int) -> None:
        self.progress_bar.setValue(100)
        self.statusBar().showMessage(
            f"OCR 完成: 成功 {completed}，失败 {failed}，backend: {self.ocr_service.backend.name}"
        )

    def _cleanup_ocr_worker(self) -> None:
        if self.ocr_worker is not None:
            self.ocr_worker.deleteLater()
            self.ocr_worker = None
        if self.ocr_thread is not None:
            self.ocr_thread.deleteLater()
            self.ocr_thread = None

    def _find_item(self, image_id: str) -> ImageListItem | None:
        for item in self.image_list_panel._items_by_row:
            if item.image_id == image_id:
                return item
        return None

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.nfc_service.shutdown()
        if self.ocr_thread is not None:
            self.ocr_thread.quit()
            self.ocr_thread.wait(2000)
        super().closeEvent(event)
