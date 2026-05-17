from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.models.view_models import OCRResult, OCRTextBox


@dataclass
class OcrAssetPaths:
    det_model_path: Path
    rec_model_path: Path
    dict_path: Path


class PPOcrV4OnnxPipeline:
    def __init__(self, assets: OcrAssetPaths) -> None:
        import onnxruntime as ort

        self.assets = self._ensure_ascii_assets(assets)
        self._ort = ort
        self.det_session = ort.InferenceSession(str(self.assets.det_model_path), providers=["CPUExecutionProvider"])
        self.rec_session = ort.InferenceSession(str(self.assets.rec_model_path), providers=["CPUExecutionProvider"])
        self.det_input_name = self.det_session.get_inputs()[0].name
        self.rec_input_name = self.rec_session.get_inputs()[0].name
        self.character_list = self._load_dict(self.assets.dict_path)

        self.det_limit_side_len = 960
        self.det_thresh = 0.3
        self.det_box_thresh = 0.55
        self.det_min_size = 3
        self.rec_img_h = 48
        self.rec_img_w = 320

    def run(self, image_path: Path) -> OCRResult:
        image = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"Unable to read image: {image_path}")

        boxes = self.detect(image)
        if not boxes:
            return OCRResult(image_path=str(image_path), boxes=[], full_text="")

        boxes = self.sort_boxes(boxes)
        crops = [self.get_rotate_crop_image(image, box) for box in boxes]
        rec_results = self.recognize(crops)

        text_boxes: list[OCRTextBox] = []
        for index, (box, (text, score)) in enumerate(zip(boxes, rec_results)):
            if not text.strip():
                continue
            text_boxes.append(
                OCRTextBox(
                    points=[[float(x), float(y)] for x, y in box.tolist()],
                    text=text,
                    score=float(score),
                    index=index,
                )
            )

        full_text = "\n".join(box.text for box in text_boxes)
        return OCRResult(image_path=str(image_path), boxes=text_boxes, full_text=full_text)

    def detect(self, image: np.ndarray) -> list[np.ndarray]:
        resized, ratio_h, ratio_w = self.resize_det_image(image)
        blob = resized.astype("float32") / 255.0
        blob = (blob - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
            [0.229, 0.224, 0.225], dtype=np.float32
        )
        blob = blob.transpose(2, 0, 1)[None, ...]

        pred = self.det_session.run(None, {self.det_input_name: blob})[0]
        pred_map = pred[0, 0]
        bitmap = pred_map > self.det_thresh
        bitmap = bitmap.astype("uint8") * 255

        contours_info = cv2.findContours(bitmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]
        boxes: list[np.ndarray] = []
        for contour in contours:
            points, short_side = self.get_mini_boxes(contour)
            if short_side < self.det_min_size:
                continue
            score = self.box_score_fast(pred_map, points)
            if score < self.det_box_thresh:
                continue

            points[:, 0] = np.clip(np.round(points[:, 0] / ratio_w), 0, image.shape[1] - 1)
            points[:, 1] = np.clip(np.round(points[:, 1] / ratio_h), 0, image.shape[0] - 1)
            boxes.append(points.astype(np.float32))
        return boxes

    def recognize(self, crops: list[np.ndarray]) -> list[tuple[str, float]]:
        results: list[tuple[str, float]] = []
        for crop in crops:
            norm_img = self.resize_norm_img(crop)
            preds = self.rec_session.run(None, {self.rec_input_name: norm_img})[0]
            results.append(self.ctc_decode(preds[0]))
        return results

    def resize_det_image(self, image: np.ndarray) -> tuple[np.ndarray, float, float]:
        src_h, src_w = image.shape[:2]
        max_side = max(src_h, src_w)
        scale = 1.0
        if max_side > self.det_limit_side_len:
            scale = self.det_limit_side_len / max_side

        resize_h = max(int(round(src_h * scale / 32) * 32), 32)
        resize_w = max(int(round(src_w * scale / 32) * 32), 32)
        resized = cv2.resize(image, (resize_w, resize_h))
        ratio_h = resize_h / float(src_h)
        ratio_w = resize_w / float(src_w)
        return resized, ratio_h, ratio_w

    def resize_norm_img(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        if h == 0 or w == 0:
            return np.zeros((1, 3, self.rec_img_h, self.rec_img_w), dtype=np.float32)

        if h / float(w) > 1.5:
            image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
            h, w = image.shape[:2]

        ratio = w / float(h)
        resized_w = min(self.rec_img_w, max(1, int(math.ceil(self.rec_img_h * ratio))))
        resized = cv2.resize(image, (resized_w, self.rec_img_h))
        resized = resized.astype("float32") / 127.5 - 1.0
        resized = resized.transpose(2, 0, 1)

        padded = np.zeros((3, self.rec_img_h, self.rec_img_w), dtype=np.float32)
        padded[:, :, :resized_w] = resized
        return padded[None, ...]

    def ctc_decode(self, preds: np.ndarray) -> tuple[str, float]:
        char_indices = preds.argmax(axis=1)
        char_scores = preds.max(axis=1)

        last_idx = -1
        text_chars: list[str] = []
        score_values: list[float] = []
        blank_idx = 0

        for idx, score in zip(char_indices.tolist(), char_scores.tolist()):
            if idx == blank_idx or idx == last_idx:
                last_idx = idx
                continue
            char_pos = idx - 1
            if 0 <= char_pos < len(self.character_list):
                text_chars.append(self.character_list[char_pos])
                score_values.append(float(score))
            last_idx = idx

        text = "".join(text_chars)
        mean_score = float(sum(score_values) / len(score_values)) if score_values else 0.0
        return text, mean_score

    @staticmethod
    def get_mini_boxes(contour: np.ndarray) -> tuple[np.ndarray, float]:
        bounding_box = cv2.minAreaRect(contour)
        points = sorted(list(cv2.boxPoints(bounding_box)), key=lambda x: (x[0], x[1]))

        index_1, index_2, index_3, index_4 = 0, 1, 2, 3
        if points[1][1] > points[0][1]:
            index_1 = 0
            index_4 = 1
        else:
            index_1 = 1
            index_4 = 0
        if points[3][1] > points[2][1]:
            index_2 = 2
            index_3 = 3
        else:
            index_2 = 3
            index_3 = 2
        box = np.array([points[index_1], points[index_2], points[index_3], points[index_4]], dtype=np.float32)
        return box, min(bounding_box[1])

    @staticmethod
    def box_score_fast(bitmap: np.ndarray, box: np.ndarray) -> float:
        h, w = bitmap.shape[:2]
        xmin = np.clip(int(np.floor(box[:, 0].min())), 0, w - 1)
        xmax = np.clip(int(np.ceil(box[:, 0].max())), 0, w - 1)
        ymin = np.clip(int(np.floor(box[:, 1].min())), 0, h - 1)
        ymax = np.clip(int(np.ceil(box[:, 1].max())), 0, h - 1)
        if xmax <= xmin or ymax <= ymin:
            return 0.0

        mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
        shifted_box = box.copy()
        shifted_box[:, 0] -= xmin
        shifted_box[:, 1] -= ymin
        cv2.fillPoly(mask, [shifted_box.astype(np.int32)], 1)
        crop = bitmap[ymin : ymax + 1, xmin : xmax + 1]
        return float(cv2.mean(crop, mask)[0])

    @staticmethod
    def sort_boxes(boxes: list[np.ndarray]) -> list[np.ndarray]:
        boxes = sorted(boxes, key=lambda box: (box[0][1], box[0][0]))
        for i in range(len(boxes) - 1):
            for j in range(i, -1, -1):
                if abs(boxes[j + 1][0][1] - boxes[j][0][1]) < 10 and boxes[j + 1][0][0] < boxes[j][0][0]:
                    boxes[j], boxes[j + 1] = boxes[j + 1], boxes[j]
                else:
                    break
        return boxes

    @staticmethod
    def get_rotate_crop_image(image: np.ndarray, points: np.ndarray) -> np.ndarray:
        points = points.astype(np.float32)
        width = int(
            max(np.linalg.norm(points[0] - points[1]), np.linalg.norm(points[2] - points[3]))
        )
        height = int(
            max(np.linalg.norm(points[0] - points[3]), np.linalg.norm(points[1] - points[2]))
        )
        width = max(width, 1)
        height = max(height, 1)

        dst_points = np.array(
            [[0, 0], [width, 0], [width, height], [0, height]],
            dtype=np.float32,
        )
        transform = cv2.getPerspectiveTransform(points, dst_points)
        crop = cv2.warpPerspective(
            image,
            transform,
            (width, height),
            borderMode=cv2.BORDER_REPLICATE,
            flags=cv2.INTER_CUBIC,
        )
        if crop.shape[0] / float(max(crop.shape[1], 1)) >= 1.5:
            crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
        return crop

    @staticmethod
    def _load_dict(dict_path: Path) -> list[str]:
        return [line.strip("\n\r") for line in dict_path.read_text(encoding="utf-8").splitlines() if line]

    @staticmethod
    def _ensure_ascii_assets(assets: OcrAssetPaths) -> OcrAssetPaths:
        def is_ascii_path(path: Path) -> bool:
            try:
                str(path).encode("ascii")
                return True
            except UnicodeEncodeError:
                return False

        if all(is_ascii_path(path) for path in (assets.det_model_path, assets.rec_model_path, assets.dict_path)):
            return assets

        cache_dir = Path.home() / ".codex" / "memories" / "ocr_models"
        cache_dir.mkdir(parents=True, exist_ok=True)

        det_copy = cache_dir / "det.onnx"
        rec_copy = cache_dir / "rec.onnx"
        dict_copy = cache_dir / "dict.txt"

        for src, dst in (
            (assets.det_model_path, det_copy),
            (assets.rec_model_path, rec_copy),
            (assets.dict_path, dict_copy),
        ):
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(src, dst)

        return OcrAssetPaths(det_model_path=det_copy, rec_model_path=rec_copy, dict_path=dict_copy)


class PPOcrV4JavaPipeline(PPOcrV4OnnxPipeline):
    def __init__(self, assets: OcrAssetPaths, project_root: Path) -> None:
        self.assets = self._ensure_ascii_assets(assets)
        self.project_root = project_root
        self.character_list = self._load_dict(self.assets.dict_path)
        self.det_limit_side_len = 960
        self.det_thresh = 0.3
        self.det_box_thresh = 0.55
        self.det_min_size = 3
        self.rec_img_h = 48
        self.rec_img_w = 320

        self.java_dir = Path.home() / ".codex" / "memories" / "java_ort_runner"
        self.java_dir.mkdir(parents=True, exist_ok=True)
        self.jar_path = Path.home() / ".codex" / "memories" / "onnxruntime-1.16.0.jar"
        self._ensure_java_jar()
        self._ensure_java_runner()

    def detect(self, image: np.ndarray) -> list[np.ndarray]:
        resized, ratio_h, ratio_w = self.resize_det_image(image)
        blob = resized.astype("float32") / 255.0
        blob = (blob - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
            [0.229, 0.224, 0.225], dtype=np.float32
        )
        blob = blob.transpose(2, 0, 1)[None, ...]

        pred = self._run_model(self.assets.det_model_path, blob)
        pred_map = pred[0, 0]
        bitmap = pred_map > self.det_thresh
        bitmap = bitmap.astype("uint8") * 255

        contours_info = cv2.findContours(bitmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]
        boxes: list[np.ndarray] = []
        for contour in contours:
            points, short_side = self.get_mini_boxes(contour)
            if short_side < self.det_min_size:
                continue
            score = self.box_score_fast(pred_map, points)
            if score < self.det_box_thresh:
                continue
            points[:, 0] = np.clip(np.round(points[:, 0] / ratio_w), 0, image.shape[1] - 1)
            points[:, 1] = np.clip(np.round(points[:, 1] / ratio_h), 0, image.shape[0] - 1)
            boxes.append(points.astype(np.float32))
        return boxes

    def recognize(self, crops: list[np.ndarray]) -> list[tuple[str, float]]:
        if not crops:
            return []
        batch = np.concatenate([self.resize_norm_img(crop) for crop in crops], axis=0)
        preds = self._run_model(self.assets.rec_model_path, batch)
        return [self.ctc_decode(preds[i]) for i in range(preds.shape[0])]

    def _ensure_java_jar(self) -> None:
        if self.jar_path.exists():
            return
        source = Path(r"C:\Users\admin\Desktop\treehole-v2.2.9-windows-x64-cpu\app\lib\onnxruntime-1.16.0.jar")
        if not source.exists():
            raise RuntimeError("Missing onnxruntime-1.16.0.jar for Java OCR backend")
        shutil.copy2(source, self.jar_path)

    def _ensure_java_runner(self) -> None:
        source_java = self.project_root / "app" / "services" / "java_ort" / "OrtTensorRunner.java"
        cache_java = self.java_dir / "OrtTensorRunner.java"
        cache_class = self.java_dir / "OrtTensorRunner.class"

        if (not cache_java.exists()) or source_java.read_bytes() != cache_java.read_bytes():
            shutil.copy2(source_java, cache_java)

        if cache_class.exists() and cache_class.stat().st_mtime >= cache_java.stat().st_mtime:
            return

        subprocess.run(
            ["javac", "-cp", str(self.jar_path), str(cache_java)],
            check=True,
            cwd=str(self.java_dir),
            capture_output=True,
            text=True,
        )

    def _run_model(self, model_path: Path, tensor: np.ndarray) -> np.ndarray:
        with tempfile.TemporaryDirectory(dir=self.java_dir) as tmpdir:
            tmpdir_path = Path(tmpdir)
            input_path = tmpdir_path / "input.bin"
            output_path = tmpdir_path / "output.bin"
            shape_path = tmpdir_path / "output_shape.txt"
            tensor.astype(np.float32).tofile(input_path)
            shape = ",".join(str(dim) for dim in tensor.shape)

            result = subprocess.run(
                [
                    "java",
                    "--enable-native-access=ALL-UNNAMED",
                    "-cp",
                    f"{self.java_dir};{self.jar_path}",
                    "OrtTensorRunner",
                    str(model_path),
                    shape,
                    str(input_path),
                    str(output_path),
                    str(shape_path),
                ],
                cwd=str(self.java_dir),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Java ORT runner failed")

            out_shape = tuple(int(part) for part in shape_path.read_text(encoding="utf-8").strip().split(",") if part)
            output = np.fromfile(output_path, dtype=np.float32)
            return output.reshape(out_shape)
