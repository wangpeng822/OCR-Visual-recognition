from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.models.view_models import OCRResult, OCRTextBox
from app.services.ppocr_onnx import OcrAssetPaths, PPOcrV4JavaPipeline, PPOcrV4OnnxPipeline


class OCRServiceError(RuntimeError):
    pass


@dataclass
class OCRBackendInfo:
    name: str
    is_demo: bool = False


class OCRService:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.det_model_path = project_root / "ch_PP-OCRv4_det_infer" / "inference.onnx"
        self.rec_model_path = project_root / "ch_PP-OCRv4_rec_infer" / "inference.onnx"
        self.dict_path = project_root / "ch_PP-OCRv4_rec_infer" / "dict.txt"
        self._pipeline: PPOcrV4OnnxPipeline | None = None
        self._backend = self._detect_backend()

    @property
    def backend(self) -> OCRBackendInfo:
        return self._backend

    def run(self, image_path: Path) -> OCRResult:
        if not self._backend.is_demo:
            if self._pipeline is None:
                raise OCRServiceError("Real OCR backend is not initialized")
            return self._pipeline.run(image_path)
        return self._build_demo_result(image_path)

    def _detect_backend(self) -> OCRBackendInfo:
        assets = (self.det_model_path, self.rec_model_path, self.dict_path)
        if any(not path.exists() for path in assets):
            return OCRBackendInfo(name="demo-missing-models", is_demo=True)

        try:
            from PIL import Image  # noqa: F401
            import cv2  # noqa: F401
            import numpy  # noqa: F401
        except Exception:
            return OCRBackendInfo(name="demo-runtime-fallback", is_demo=True)

        try:
            import onnxruntime  # noqa: F401
            self._pipeline = PPOcrV4OnnxPipeline(
                OcrAssetPaths(
                    det_model_path=self.det_model_path,
                    rec_model_path=self.rec_model_path,
                    dict_path=self.dict_path,
                )
            )
            return OCRBackendInfo(name="ppocrv4-onnxruntime", is_demo=False)
        except Exception:
            self._pipeline = None

        try:
            self._pipeline = PPOcrV4JavaPipeline(
                OcrAssetPaths(
                    det_model_path=self.det_model_path,
                    rec_model_path=self.rec_model_path,
                    dict_path=self.dict_path,
                ),
                project_root=self.project_root,
            )
            return OCRBackendInfo(name="ppocrv4-java-ort", is_demo=False)
        except Exception:
            self._pipeline = None
            return OCRBackendInfo(name="demo-runtime-fallback", is_demo=True)

    def _build_demo_result(self, image_path: Path) -> OCRResult:
        try:
            from PIL import Image
        except Exception as exc:
            raise OCRServiceError(f"Unable to load image backend: {exc}") from exc

        with Image.open(image_path) as image:
            width, height = image.size

        width = max(width, 1)
        height = max(height, 1)

        sample_texts = [
            "SN-001245",
            "LOT-A09",
            "NFC-CODE-7788",
            image_path.stem,
        ]
        box_height = max(height * 0.11, 36.0)
        left = width * 0.08
        right = width * 0.72
        start_top = height * 0.16
        gap = box_height * 0.45

        boxes: list[OCRTextBox] = []
        for index, text in enumerate(sample_texts):
            top = start_top + index * (box_height + gap)
            bottom = min(top + box_height, height - 12.0)
            points = [
                [left, top],
                [right, top],
                [right, bottom],
                [left, bottom],
            ]
            score = max(0.82, 0.96 - index * 0.03)
            boxes.append(OCRTextBox(points=points, text=text, score=score, index=index))

        full_text = "\n".join(box.text for box in boxes)
        return OCRResult(image_path=str(image_path), boxes=boxes, full_text=full_text)
