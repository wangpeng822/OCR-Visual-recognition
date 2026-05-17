from __future__ import annotations

from app.models.nfc_models import NfcDeviceState
from app.services.pcsc_backend import NfcServiceError, PcscBackend
from app.ui.qt_compat import QObject, Signal


class NfcService(QObject):
    state_changed = Signal(object)
    record_added = Signal(object)
    error_occurred = Signal(str)
    error_details = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._backend = PcscBackend()

    @property
    def state(self) -> NfcDeviceState:
        return self._backend.state

    def connect_reader(self) -> None:
        try:
            state, record = self._backend.connect_reader()
            self.state_changed.emit(state)
            self.record_added.emit(record)
        except NfcServiceError as exc:
            self._backend.state.status_text = exc.status_text
            self._backend.state.operation_text = exc.operation_text
            self.state_changed.emit(self._backend.state)
            self.error_occurred.emit(str(exc))
            self.error_details.emit(exc)

    def read_tag(self) -> None:
        try:
            _, state, record = self._backend.read_uid()
            self.state_changed.emit(state)
            self.record_added.emit(record)
        except NfcServiceError as exc:
            self._backend.state.status_text = exc.status_text
            self._backend.state.operation_text = exc.operation_text
            self.state_changed.emit(self._backend.state)
            self.error_occurred.emit(str(exc))
            self.error_details.emit(exc)

    def write_tag(self, value: str) -> None:
        try:
            state, record = self._backend.prepare_write(value)
            self.state_changed.emit(state)
            self.record_added.emit(record)
            exc = NfcServiceError(
                "已经接入真实 PC/SC 读卡器，但通用写卡尚未启用。写入前必须明确标签类型、扇区布局和认证密钥。",
                status_text="写卡未启用",
                operation_text="等待标签写卡协议确认",
                severity="info",
            )
            self.error_occurred.emit(str(exc))
            self.error_details.emit(exc)
        except NfcServiceError as exc:
            self._backend.state.status_text = exc.status_text
            self._backend.state.operation_text = exc.operation_text
            self.state_changed.emit(self._backend.state)
            self.error_occurred.emit(str(exc))
            self.error_details.emit(exc)

    def shutdown(self) -> None:
        state = self._backend.shutdown()
        self.state_changed.emit(state)
