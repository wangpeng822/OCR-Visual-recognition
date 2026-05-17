# OCR + NFC 桌面程序架构设计

## 1. 项目目标

基于 Python 开发一个 Windows 桌面程序，满足以下业务需求：

1. 支持用户一次上传多张图片。
2. 对图片按批次执行 OCR 文字检测与识别。
3. 在图片上可视化展示识别到的文字区域。
4. 用户点击图片上的已识别文字后，将该文字内容回显到右侧文本框。
5. 右侧侧边栏集成 NFC 编号读取与写入功能。
6. 支持将“当前选中文字”与“NFC 编号”联动，便于人工确认与写卡。

当前已知模型资源：

- 检测模型：`ch_PP-OCRv4_det_infer/inference.onnx`
- 识别模型：`ch_PP-OCRv4_rec_infer/inference.onnx`
- 字典文件：`ch_PP-OCRv4_rec_infer/dict.txt`

## 2. 推荐技术方案

## 2.1 GUI 框架

推荐使用 `PySide6`。

原因：

1. Windows 桌面支持成熟。
2. 图形界面、图片标注、侧边栏布局、事件处理都比较方便。
3. 后续打包为 `.exe` 也比较成熟。
4. 比 Tkinter 更适合做图片交互和复杂控件界面。

## 2.2 OCR 推理框架

推荐使用：

- `onnxruntime`：加载检测与识别模型
- `opencv-python`：图像预处理、检测框绘制、坐标变换
- `numpy`：张量与图像数据处理

## 2.3 NFC 通信

推荐优先支持两种接入方式：

1. `pyscard`
   - 适合 PC/SC 兼容读卡器
   - 用于常见 USB NFC 读写器
2. 预留“串口设备模式”
   - 如果后续接的是串口型读写器，可通过 `pyserial` 扩展

设计上应抽象统一 `NFCService` 接口，不把 GUI 与具体硬件协议直接耦合。

## 3. 总体架构

采用分层架构：

1. 表现层（UI）
2. 应用层（任务编排）
3. 领域层（OCR / 图片标注 / NFC 业务）
4. 基础设施层（ONNX Runtime / 读卡器驱动 / 文件系统）

示意如下：

```text
+------------------------------------------------------+
|                    Desktop UI                        |
|  MainWindow                                          |
|  - 图片列表                                           |
|  - 图片预览/标注区                                     |
|  - OCR结果区                                          |
|  - NFC侧边栏                                          |
+-------------------------+----------------------------+
                          |
                          v
+------------------------------------------------------+
|                Application Layer                     |
|  OCRBatchController                                  |
|  ImageSelectionController                            |
|  NFCController                                       |
|  TaskScheduler / WorkerManager                       |
+-------------------------+----------------------------+
                          |
          +---------------+------------------+
          |                                  |
          v                                  v
+-----------------------------+   +-----------------------------+
|         OCR Domain          |   |         NFC Domain          |
|  OCRPipeline                |   |  NFCService                 |
|  Detector                   |   |  Reader / Writer            |
|  Recognizer                 |   |  DeviceAdapter              |
|  ResultMapper               |   |  CardDataCodec              |
+-----------------------------+   +-----------------------------+
          |                                  |
          v                                  v
+-----------------------------+   +-----------------------------+
|     Infrastructure Layer    |   |     Infrastructure Layer    |
| onnxruntime / opencv / np   |   | pyscard / pyserial / logs   |
+-----------------------------+   +-----------------------------+
```

## 4. 功能模块划分

## 4.1 图片导入模块

职责：

1. 支持多选图片导入。
2. 支持拖拽导入。
3. 生成待处理队列。
4. 记录每张图片的状态。

建议状态：

- `pending`：待识别
- `processing`：识别中
- `done`：完成
- `failed`：失败

数据结构建议：

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class ImageTask:
    image_id: str
    path: Path
    status: str = "pending"
    ocr_result: "OCRResult | None" = None
    error: str | None = None
```

## 4.2 OCR 批处理模块

职责：

1. 按批次读取图片。
2. 对每张图片执行文本检测。
3. 对检测框区域执行裁剪与文本识别。
4. 汇总结构化 OCR 结果。
5. 向 UI 回传进度。

批处理原则：

1. “多张图片分批”是任务调度层面的 batch，不是必须把多张图合并进一个模型输入。
2. 第一版建议逐图处理，但采用后台线程池异步执行。
3. 后续如需提速，可在识别阶段增加小批量推理。

建议流程：

```text
图片列表
  -> 逐张加载
  -> 检测模型推理
  -> 检测框后处理
  -> 文本区域裁剪/排序
  -> 识别模型推理
  -> 文本解码
  -> 结果回传 UI
```

## 4.3 图片标注与点击交互模块

职责：

1. 在图片预览区域绘制 OCR 检测框。
2. 支持鼠标点击某个文字框。
3. 命中后高亮当前框。
4. 将对应识别文本回显到右侧文本框。

建议实现：

1. 使用 `QGraphicsView + QGraphicsScene` 展示图片。
2. 每个 OCR 文本框映射为可点击的图元。
3. 图元保存：
   - 框坐标
   - 文本内容
   - 置信度
   - 行号/顺序号

点击流程：

```text
用户点击图片
  -> 命中检测框
  -> 获取 OCRTextItem
  -> 更新右侧“当前选中文字”
  -> 可选：同步填充“NFC 待写入编号”
```

## 4.4 右侧结果与操作侧边栏

建议右侧分为 3 个区域：

### A. 当前识别结果区

展示内容：

1. 当前图片文件名
2. 当前选中文字
3. 当前选中框置信度
4. 当前图片完整 OCR 文本列表

### B. 文本编辑区

控件建议：

1. 单行文本框：当前选中文字
2. 多行文本框：手动整理后的文本
3. 按钮：
   - 追加到结果区
   - 清空
   - 复制

### C. NFC 操作区

控件建议：

1. 设备状态显示
2. “连接设备”按钮
3. “读取编号”按钮
4. “写入编号”按钮
5. 文本框：
   - 读出的 NFC 编号
   - 待写入 NFC 编号
6. 联动按钮：
   - 使用当前选中文字作为待写入编号
   - 将 NFC 编号回填到文本区

## 4.5 NFC 模块

职责：

1. 枚举并连接 NFC 设备。
2. 读取卡片唯一编号或指定块数据。
3. 将编号写入指定存储位置。
4. 返回标准结果给 UI。

由于不同卡型差异较大，需要先抽象接口，再适配设备协议。

建议接口：

```python
class NFCService:
    def connect(self) -> bool:
        ...

    def disconnect(self) -> None:
        ...

    def read_id(self) -> str:
        ...

    def write_id(self, value: str) -> bool:
        ...

    def get_status(self) -> str:
        ...
```

补充说明：

1. 如果只是读取 UID，部分卡片 UID 不可改写。
2. 如果“写入编号”实际是写用户区数据块，则应明确卡片类型和块地址。
3. 因此项目启动前必须先确认：
   - NFC 读写器型号
   - 卡片类型
   - 编号写入位置
   - 数据编码规则

## 5. 核心数据结构设计

## 5.1 OCR 文本框结构

```python
from dataclasses import dataclass

@dataclass
class OCRTextBox:
    points: list[list[float]]
    text: str
    score: float
    index: int
```

## 5.2 OCR 结果结构

```python
from dataclasses import dataclass, field

@dataclass
class OCRResult:
    image_path: str
    boxes: list[OCRTextBox] = field(default_factory=list)
    full_text: str = ""
```

## 5.3 NFC 结果结构

```python
from dataclasses import dataclass

@dataclass
class NFCReadResult:
    success: bool
    value: str
    message: str
```

## 6. 目录结构建议

建议项目目录如下：

```text
project/
├─ main.py
├─ requirements.txt
├─ app/
│  ├─ ui/
│  │  ├─ main_window.py
│  │  ├─ image_view.py
│  │  ├─ sidebar.py
│  │  └─ widgets/
│  ├─ controllers/
│  │  ├─ ocr_controller.py
│  │  ├─ image_controller.py
│  │  └─ nfc_controller.py
│  ├─ services/
│  │  ├─ ocr/
│  │  │  ├─ pipeline.py
│  │  │  ├─ detector.py
│  │  │  ├─ recognizer.py
│  │  │  ├─ preprocess.py
│  │  │  └─ postprocess.py
│  │  └─ nfc/
│  │     ├─ service.py
│  │     ├─ pyscard_adapter.py
│  │     └─ codec.py
│  ├─ models/
│  │  ├─ entities.py
│  │  └─ view_models.py
│  ├─ workers/
│  │  ├─ ocr_worker.py
│  │  └─ nfc_worker.py
│  └─ utils/
│     ├─ image_utils.py
│     ├─ logger.py
│     └─ config.py
├─ assets/
├─ outputs/
└─ docs/
```

如果你已经固定使用外部模型目录，也可在配置中引用，不强制复制到项目内。

## 7. 关键流程设计

## 7.1 多图 OCR 处理流程

```text
选择多张图片
  -> 加入任务队列
  -> 用户点击“开始识别”
  -> OCRWorker 后台逐张处理
  -> 每完成一张发出信号
  -> UI 更新图片状态与结果
  -> 默认显示当前完成图片的标注结果
```

## 7.2 点击文字回显流程

```text
用户在图片上点击 OCR 框
  -> image_view 判断命中框
  -> 发出 text_box_selected(box) 信号
  -> sidebar 更新“当前选中文字”
  -> 用户可手动编辑
  -> 用户可一键写入 NFC
```

## 7.3 NFC 读取流程

```text
点击“连接设备”
  -> NFCService.connect()
  -> 更新设备状态

点击“读取编号”
  -> NFCWorker.read_id()
  -> 结果显示到右侧“读出的 NFC 编号”
  -> 可选：同步追加到文本区
```

## 7.4 NFC 写入流程

```text
用户选择 OCR 文字
  -> 当前选中文字回显
  -> 点击“设为待写入编号”
  -> 点击“写入编号”
  -> NFCWorker.write_id(value)
  -> 返回成功/失败提示
```

## 8. UI 布局建议

推荐三栏布局：

1. 左侧：图片任务列表
2. 中间：图片预览与 OCR 标注区域
3. 右侧：文本/NFC 操作侧边栏

示意：

```text
+----------------+-----------------------------+----------------------+
| 图片列表        | 图片预览 + OCR框标注          | 文本/NFC侧边栏         |
|                |                             |                      |
| 1. img001.jpg  |                             | 当前选中文字          |
| 2. img002.jpg  |                             | [文本框]             |
| 3. img003.jpg  |                             |                      |
|                |                             | 完整OCR文本           |
| [导入图片]      |                             | [多行框]             |
| [开始识别]      |                             |                      |
| [下一批]        |                             | NFC设备状态           |
|                |                             | [连接] [读取] [写入]  |
|                |                             | 读出编号              |
|                |                             | 待写编号              |
+----------------+-----------------------------+----------------------+
```

## 9. 并发与性能设计

## 9.1 线程模型

不建议在主线程直接执行 OCR 或 NFC IO。

建议：

1. 主线程负责 UI。
2. OCR 使用 `QThread` 或 `QRunnable + QThreadPool`。
3. NFC 读写也放到后台线程，避免设备响应阻塞界面。

## 9.2 批处理策略

第一版推荐：

1. 每批次处理 `5~20` 张图片。
2. 单张图片内部顺序执行检测和识别。
3. 在 UI 上显示进度条：
   - 当前批次进度
   - 总体进度

## 9.3 缓存策略

建议缓存：

1. 原图缩略图
2. OCR 结构化结果
3. 标注后预览层

避免切换图片时重复 OCR。

## 10. OCR 技术设计细节

## 10.1 检测模型职责

输入图片，输出文本区域候选框。

模块：

- `Detector`
- 负责预处理、推理、后处理

建议方法：

```python
class Detector:
    def detect(self, image: "np.ndarray") -> list[list[list[float]]]:
        ...
```

## 10.2 识别模型职责

输入裁剪文本图，输出文本字符串及置信度。

建议方法：

```python
class Recognizer:
    def recognize(self, crops: list["np.ndarray"]) -> list[tuple[str, float]]:
        ...
```

## 10.3 OCR 管线职责

统一调度检测与识别，输出 `OCRResult`。

建议方法：

```python
class OCRPipeline:
    def run(self, image_path: str) -> OCRResult:
        ...
```

## 10.4 检测框排序

为了让完整 OCR 文本更符合阅读顺序，需要对文本框排序。

建议规则：

1. 先按 `y` 坐标排序
2. 同一行内按 `x` 坐标排序
3. 对轻微倾斜文本做容差处理

## 11. 配置设计

建议增加配置文件 `config.yaml` 或 `json`：

```yaml
models:
  det_model_path: "ch_PP-OCRv4_det_infer/inference.onnx"
  rec_model_path: "ch_PP-OCRv4_rec_infer/inference.onnx"
  rec_dict_path: "ch_PP-OCRv4_rec_infer/dict.txt"

ocr:
  batch_size: 10
  det_input_size: 960
  rec_image_height: 48
  score_threshold: 0.5

nfc:
  reader_type: "pcsc"
  timeout_ms: 3000
  write_block: 4
```

## 12. 异常处理设计

需要明确处理以下异常：

1. 图片加载失败
2. 模型文件不存在
3. ONNX Runtime 初始化失败
4. 某张图片 OCR 失败
5. NFC 设备未连接
6. 卡片未放置
7. 卡片不可写
8. 写入数据格式非法

错误处理原则：

1. 单张图片失败不影响整批任务继续。
2. 错误信息应展示到 UI 状态栏或日志区。
3. NFC 写入前必须进行参数校验。

## 13. 日志与调试设计

建议至少记录以下日志：

1. 程序启动配置
2. 模型加载耗时
3. 每张图片 OCR 耗时
4. 检测框数量
5. NFC 连接状态
6. 读卡/写卡结果
7. 异常堆栈

建议日志输出：

- 控制台
- 本地日志文件 `logs/app.log`

## 14. 打包与部署

Windows 平台建议使用：

- `PyInstaller`

打包输出：

1. 主程序 exe
2. 模型目录
3. 配置文件
4. 运行依赖动态库

注意事项：

1. `onnxruntime` 打包后需要验证 dll 是否齐全。
2. `PySide6` 打包时需检查 platform plugins。
3. NFC 驱动一般不随程序分发，需要用户预装。

## 15. 开发阶段划分

建议分四期实施：

### 第一阶段：最小可用版本

目标：

1. 导入多张图片
2. 批量 OCR
3. 展示识别框
4. 点击文字回显到右侧文本框

### 第二阶段：NFC 接入

目标：

1. 连接 NFC 设备
2. 读取编号
3. 写入编号
4. 与右侧文本区联动

### 第三阶段：稳定性和交互增强

目标：

1. 增加进度条
2. 增加错误提示
3. 增加日志
4. 增加 OCR 结果导出

### 第四阶段：部署与打包

目标：

1. 生成 Windows 可执行程序
2. 交付模型与配置
3. 完成设备环境验证

## 16. 风险与前置确认

本项目的最大不确定项不在 OCR，而在 NFC 写卡细节。

在正式编码前，需要你补充以下信息：

1. NFC 读写器具体型号。
2. 卡片类型。
3. “编号”是读取 UID，还是读取卡内某个数据块。
4. “写入编号”是否真的允许改写。
5. 写入的数据长度、编码方式、目标块地址。

如果这些信息不明确，程序可以先把 NFC 模块做成接口与模拟模式，但无法保证真实写卡功能一次接通。

## 17. 最终推荐实施方案

推荐最终实现路线：

1. 使用 `PySide6` 构建桌面界面。
2. 使用 `onnxruntime + opencv + numpy` 封装 PP-OCRv4 检测与识别管线。
3. 使用 `QGraphicsView` 实现图片标注和点击选词。
4. 使用 `QThread` 将 OCR 和 NFC 放到后台执行。
5. 使用 `pyscard` 抽象 NFC 设备读写。
6. 先完成 OCR 主流程，再接入 NFC 真机协议。

## 18. 后续可直接进入的实现清单

下一步编码时，可以直接按以下顺序落地：

1. 搭项目骨架与依赖。
2. 实现主窗口三栏布局。
3. 实现图片导入与任务列表。
4. 实现 OCRPipeline。
5. 实现图片框选点击回显。
6. 实现右侧文本联动。
7. 接入 NFCService 抽象。
8. 对接真实 NFC 设备协议。
![Uploading image.png…]()
