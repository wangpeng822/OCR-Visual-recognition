from __future__ import annotations

from pathlib import Path

from app.models.view_models import OCRResult
from app.services.ocr_service import OCRService
from app.ui.qt_compat import QObject, Signal


class OCRWorker(QObject):
    item_started = Signal(str, int, int)
    item_completed = Signal(str, object)
    item_failed = Signal(str, str)
    batch_finished = Signal(int, int)

    def __init__(self, image_tasks: list[tuple[str, Path]], ocr_service: OCRService) -> None:
        super().__init__()
        self._image_tasks = image_tasks
        self._ocr_service = ocr_service

    def run(self) -> None:
        completed = 0
        failed = 0
        total = len(self._image_tasks)

        for index, (image_id, image_path) in enumerate(self._image_tasks, start=1):
            self.item_started.emit(image_id, index, total)
            try:
                result: OCRResult = self._ocr_service.run(image_path)
            except Exception as exc:
                failed += 1
                self.item_failed.emit(image_id, str(exc))
                continue

            completed += 1
            self.item_completed.emit(image_id, result)

        self.batch_finished.emit(completed, failed)
