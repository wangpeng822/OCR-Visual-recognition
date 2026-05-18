from __future__ import annotations

from app.models.nfc_models import NfcDeviceState, NfcRecord
from app.ui.qt_compat import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    Qt,
    QVBoxLayout,
    QWidget,
    Signal,
)


class RightSidebar(QWidget):
    fill_text_from_nfc_requested = Signal(str)
    nfc_connect_requested = Signal()
    nfc_read_requested = Signal()
    nfc_write_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

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

        self.nfc_read_value = QLineEdit()
        self.nfc_read_value.setPlaceholderText("读取后的编号")
        self.nfc_read_value.setReadOnly(True)

        self.nfc_write_value = QLineEdit()
        self.nfc_write_value.setPlaceholderText("待写入编号")

        self.connect_button = QPushButton("连接设备")
        self.read_button = QPushButton("读取编号")
        self.write_button = QPushButton("写入编号")
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

        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(8)
        field_grid.setVerticalSpacing(8)
        field_grid.addWidget(QLabel("读出编号"), 0, 0)
        field_grid.addWidget(self.nfc_read_value, 0, 1)
        field_grid.addWidget(QLabel("待写编号"), 1, 0)
        field_grid.addWidget(self.nfc_write_value, 1, 1)

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
        layout.addLayout(primary_actions)
        layout.addLayout(helper_actions)
        layout.addLayout(history_layout)
        return group

    def _wire_events(self) -> None:
        self.fill_from_nfc_button.clicked.connect(
            lambda: self.fill_text_from_nfc_requested.emit(self.nfc_read_value.text())
        )
        self.connect_button.clicked.connect(self.nfc_connect_requested.emit)
        self.read_button.clicked.connect(self.nfc_read_requested.emit)
        self.write_button.clicked.connect(lambda: self.nfc_write_requested.emit(self.nfc_write_value.text()))
