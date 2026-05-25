from __future__ import annotations

import json
import os
from pathlib import Path

from app.models.nfc_models import NfcDeviceState, NfcRecord
from app.ui.qt_compat import (
    QColor,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPainter,
    QPushButton,
    QTextEdit,
    Qt,
    QVBoxLayout,
    QWidget,
    Signal,
)


def default_template_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "OCR_NFC_Desktop" / "nfc_templates.json"
    return Path.home() / ".ocr_nfc_desktop" / "nfc_templates.json"


class NfcTemplateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_template_path()
        self.templates = self._load()

    def add(self, value: str) -> None:
        template = value.strip()
        if not template or template in self.templates:
            return
        self.templates.append(template)
        self._save()

    def delete(self, value: str) -> None:
        template = value.strip()
        self.templates = [item for item in self.templates if item != template]
        self._save()

    def clear(self) -> None:
        self.templates = []
        self._save()

    def _load(self) -> list[str]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [item.strip() for item in data if isinstance(item, str) and item.strip()]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.templates, ensure_ascii=False, indent=2), encoding="utf-8")


class TemplateLineEdit(QLineEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.template_prefix_length = 0

    def set_template_prefix_length(self, value: int) -> None:
        self.template_prefix_length = max(0, value)
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if self.template_prefix_length <= 0:
            return

        prefix = self.text()[: self.template_prefix_length]
        if not prefix:
            return

        margins = self.textMargins()
        left = margins.left() + 8
        width = self.fontMetrics().horizontalAdvance(prefix)
        if width <= 0:
            return

        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(207, 234, 255, 150))
        painter.drawRoundedRect(left - 2, 6, width + 4, max(0, self.height() - 12), 4, 4)


class NfcTemplateManagerDialog(QDialog):
    template_applied = Signal(str)

    def __init__(self, store: NfcTemplateStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("模版管理")
        self.resize(360, 300)

        self.prefix_template_input = QLineEdit()
        self.prefix_template_input.setPlaceholderText("输入前缀模版，如 E123")
        self.template_list = QListWidget()
        self.add_prefix_button = QPushButton("新增模版")
        self.apply_button = QPushButton("应用")
        self.delete_button = QPushButton("删除")
        self.delete_all_button = QPushButton("删除全部")
        self.close_button = QPushButton("关闭")

        prefix_row = QHBoxLayout()
        prefix_row.setSpacing(8)
        prefix_row.addWidget(QLabel("模版"))
        prefix_row.addWidget(self.prefix_template_input, 1)
        prefix_row.addWidget(self.add_prefix_button)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(self.apply_button)
        action_row.addWidget(self.delete_button)
        action_row.addWidget(self.delete_all_button)
        action_row.addStretch(1)
        action_row.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(QLabel("已有模版"))
        layout.addLayout(prefix_row)
        layout.addWidget(self.template_list, 1)
        layout.addLayout(action_row)

        self.add_prefix_button.clicked.connect(self._add_prefix_template)
        self.apply_button.clicked.connect(self._apply_template)
        self.delete_button.clicked.connect(self._delete_template)
        self.delete_all_button.clicked.connect(self._delete_all_templates)
        self.close_button.clicked.connect(self.close)
        self.template_list.itemDoubleClicked.connect(lambda _item: self._apply_template())

        self._refresh_templates()

    def _refresh_templates(self) -> None:
        self.template_list.clear()
        for template in self.store.templates:
            self.template_list.addItem(template)

    def _selected_template(self) -> str:
        item = self.template_list.currentItem()
        return item.text() if item is not None else ""

    def _add_prefix_template(self) -> None:
        self.store.add(self.prefix_template_input.text())
        self.prefix_template_input.clear()
        self._refresh_templates()
        if self.template_list.count() > 0:
            self.template_list.setCurrentRow(self.template_list.count() - 1)

    def _apply_template(self) -> None:
        template = self._selected_template()
        if template:
            self.template_applied.emit(template)
            self.accept()

    def _delete_template(self) -> None:
        template = self._selected_template()
        if not template:
            return
        self.store.delete(template)
        self._refresh_templates()

    def _delete_all_templates(self) -> None:
        self.store.clear()
        self._refresh_templates()


class RightSidebar(QWidget):
    fill_text_from_nfc_requested = Signal(str)
    nfc_connect_requested = Signal()
    nfc_read_requested = Signal()
    nfc_write_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None, template_store: NfcTemplateStore | None = None) -> None:
        super().__init__(parent)
        self.template_store = template_store or NfcTemplateStore()

        self.title_label = QLabel("当前文字与 NFC")
        self.title_label.setObjectName("panelTitle")

        self.selected_text_input = QTextEdit()
        self.selected_text_input.setObjectName("selectedTextPreview")
        self.selected_text_input.setPlaceholderText("点击图片中的识别文字后显示在这里")
        self.selected_text_input.setReadOnly(True)
        self.selected_text_input.setMinimumHeight(120)
        self.selected_text_input.setMaximumHeight(170)

        self.selected_score_label = QLabel("置信度: -")
        self.selected_score_label.setObjectName("helperText")

        self.device_status_value = QLabel("未连接")
        self.device_status_value.setObjectName("statusChip")

        self.reader_name_value = QLabel("未检测到设备")
        self.reader_name_value.setObjectName("helperText")
        self.reader_name_value.setWordWrap(True)

        self.protocol_value = QLabel("-")
        self.protocol_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.last_seen_value = QLabel("等待连接")
        self.last_seen_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.operation_value = QLabel("空闲")
        self.operation_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.current_template_value = QLabel("未设置")
        self.current_template_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.current_template_value.setObjectName("helperText")

        self.nfc_read_value = QLineEdit()
        self.nfc_read_value.setPlaceholderText("读取后的编号")
        self.nfc_read_value.setReadOnly(True)

        self.nfc_write_value = TemplateLineEdit()
        self.nfc_write_value.setPlaceholderText("待写入编号")
        self._nfc_template = ""
        self._filled_template_as_text = False

        self.connect_button = QPushButton("连接设备")
        self.read_button = QPushButton("读取编号")
        self.write_button = QPushButton("写入编号")
        self.increment_number_button = QPushButton("编号+1")
        self.template_button = QPushButton("设置模版")
        self.fill_template_button = QPushButton("填入模版")
        self.fill_from_nfc_button = QPushButton("将 NFC 编号回填文本")

        self.history_list = QListWidget()
        self.history_list.setObjectName("nfcHistoryList")
        self.history_list.setSelectionMode(QListWidget.NoSelection)
        self.history_list.setFocusPolicy(Qt.NoFocus)
        self.history_list.setMaximumHeight(150)

        self._wire_events()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.title_label)
        layout.addWidget(self._build_result_group())
        layout.addWidget(self._build_nfc_group())
        layout.addStretch(1)

        self.set_nfc_snapshot(NfcDeviceState())

    def set_selected_text(self, value: str, score: float | None = None) -> None:
        self.selected_text_input.setPlainText(value)
        self.selected_score_label.setText(f"置信度: {score:.3f}" if score is not None else "置信度: -")

    def set_nfc_status(self, value: str) -> None:
        self.device_status_value.setText(value)

    def set_nfc_read_value(self, value: str) -> None:
        self.nfc_read_value.setText(value)
        self.fill_from_nfc_button.setEnabled(bool(value.strip()))

    def set_nfc_template(self, value: str) -> None:
        self._nfc_template = value.strip()
        self._filled_template_as_text = False
        self.current_template_value.setText(self._nfc_template or "未设置")
        self._refresh_template_prefix()

    def fill_current_template(self) -> None:
        if not self._nfc_template:
            return
        self._filled_template_as_text = True
        self.nfc_write_value.setText(self._nfc_template)

    def increment_write_number(self) -> None:
        value = self.nfc_write_value.text()
        prefix_length = self._template_prefix_length(value)
        prefix = value[:prefix_length]
        numeric_part = value[prefix_length:]
        if not numeric_part:
            self.nfc_write_value.setText(f"{prefix}1")
            return
        if not numeric_part.isdigit():
            return

        incremented = str(int(numeric_part) + 1).zfill(len(numeric_part))
        self.nfc_write_value.setText(f"{prefix}{incremented}")

    def set_nfc_snapshot(self, state: NfcDeviceState) -> None:
        self.device_status_value.setText(state.status_text)
        self.reader_name_value.setText(state.reader_name)
        self.protocol_value.setText(state.protocol)
        self.last_seen_value.setText(state.last_seen_text)
        self.operation_value.setText(state.operation_text)
        if state.last_uid != "-":
            self.set_nfc_read_value(state.last_uid)
        else:
            self.fill_from_nfc_button.setEnabled(bool(self.nfc_read_value.text().strip()))
        self.read_button.setEnabled(state.connected)
        self.write_button.setEnabled(state.connected)

    def append_nfc_record(self, record: NfcRecord) -> None:
        self.history_list.insertItem(0, QListWidgetItem(record.display_text))
        while self.history_list.count() > 8:
            self.history_list.takeItem(self.history_list.count() - 1)

    def _build_result_group(self) -> QGroupBox:
        group = QGroupBox("当前选中文字")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(6)
        layout.addWidget(self.selected_text_input)
        layout.addWidget(self.selected_score_label)
        return group

    def _build_nfc_group(self) -> QGroupBox:
        group = QGroupBox("NFC 操作")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)

        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("设备状态"))
        status_row.addStretch(1)
        status_row.addWidget(self.device_status_value)

        meta_grid = QGridLayout()
        meta_grid.setHorizontalSpacing(8)
        meta_grid.setVerticalSpacing(6)
        meta_grid.addWidget(QLabel("读卡器"), 0, 0)
        meta_grid.addWidget(self.reader_name_value, 0, 1)
        meta_grid.addWidget(QLabel("协议"), 1, 0)
        meta_grid.addWidget(self.protocol_value, 1, 1)
        meta_grid.addWidget(QLabel("最近活动"), 2, 0)
        meta_grid.addWidget(self.last_seen_value, 2, 1)
        meta_grid.addWidget(QLabel("当前操作"), 3, 0)
        meta_grid.addWidget(self.operation_value, 3, 1)
        meta_grid.addWidget(QLabel("正在使用模版"), 4, 0)
        meta_grid.addWidget(self.current_template_value, 4, 1)

        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(8)
        field_grid.setVerticalSpacing(8)
        field_grid.addWidget(QLabel("读出编号"), 0, 0)
        field_grid.addWidget(self.nfc_read_value, 0, 1)
        field_grid.addWidget(QLabel("待写编号"), 1, 0)
        field_grid.addWidget(self.nfc_write_value, 1, 1)

        template_actions = QHBoxLayout()
        template_actions.setSpacing(8)
        template_actions.addWidget(self.fill_template_button)
        template_actions.addWidget(self.increment_number_button)
        template_actions.addWidget(self.template_button)

        primary_actions = QHBoxLayout()
        primary_actions.setSpacing(8)
        primary_actions.addWidget(self.connect_button)
        primary_actions.addWidget(self.read_button)
        primary_actions.addWidget(self.write_button)

        helper_actions = QVBoxLayout()
        helper_actions.setSpacing(8)
        helper_actions.addWidget(self.fill_from_nfc_button)

        history_layout = QVBoxLayout()
        history_layout.setSpacing(6)
        history_layout.addWidget(QLabel("最近记录"))
        history_layout.addWidget(self.history_list)

        layout.addLayout(status_row)
        layout.addLayout(meta_grid)
        layout.addLayout(field_grid)
        layout.addLayout(template_actions)
        layout.addLayout(primary_actions)
        layout.addLayout(helper_actions)
        layout.addLayout(history_layout)
        return group

    def _wire_events(self) -> None:
        self.nfc_write_value.textChanged.connect(self._refresh_template_prefix)
        self.fill_from_nfc_button.clicked.connect(
            lambda: self.fill_text_from_nfc_requested.emit(self.nfc_read_value.text())
        )
        self.connect_button.clicked.connect(self.nfc_connect_requested.emit)
        self.read_button.clicked.connect(self.nfc_read_requested.emit)
        self.write_button.clicked.connect(lambda: self.nfc_write_requested.emit(self.nfc_write_value.text()))
        self.fill_template_button.clicked.connect(self.fill_current_template)
        self.increment_number_button.clicked.connect(self.increment_write_number)
        self.template_button.clicked.connect(self._open_template_manager)

    def create_template_manager_dialog(self) -> NfcTemplateManagerDialog:
        dialog = NfcTemplateManagerDialog(self.template_store, self)
        dialog.template_applied.connect(self.set_nfc_template)
        return dialog

    def _open_template_manager(self) -> None:
        self.create_template_manager_dialog().exec()

    def _refresh_template_prefix(self) -> None:
        self.nfc_write_value.set_template_prefix_length(
            self._template_prefix_length(self.nfc_write_value.text())
        )

    def _template_prefix_length(self, value: str) -> int:
        if not self._nfc_template:
            return 0
        if self._filled_template_as_text and value.startswith(self._nfc_template):
            return len(self._nfc_template)
        if value.startswith(self._nfc_template):
            return len(self._nfc_template)
        return 0
