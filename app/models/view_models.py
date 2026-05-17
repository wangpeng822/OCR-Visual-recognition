from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OCRTextBox:
    points: list[list[float]]
    text: str
    score: float
    index: int

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        xs = [point[0] for point in self.points]
        ys = [point[1] for point in self.points]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass
class OCRResult:
    image_path: str
    boxes: list[OCRTextBox] = field(default_factory=list)
    full_text: str = ""


@dataclass
class ImageListItem:
    image_id: str
    path: Path
    status: str = "pending"
    selected_text: str = ""
    selected_score: float | None = None
    full_text: str = ""
    error: str = ""
    ocr_result: OCRResult | None = None

    @property
    def filename(self) -> str:
        return self.path.name


class ImageTaskStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


STATUS_LABELS = {
    ImageTaskStatus.PENDING: "待处理",
    ImageTaskStatus.PROCESSING: "识别中",
    ImageTaskStatus.DONE: "已完成",
    ImageTaskStatus.FAILED: "失败",
}
