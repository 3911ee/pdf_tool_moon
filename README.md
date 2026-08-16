# PDF 工具包

本地 PDF 处理工具，基于 FastAPI + win32com，提供 Word/PPT/图片 → PDF、PDF → Word、合并、拆分、删页、压缩等功能。

## 环境要求

- Windows 10+
- Python 3.10+
- Microsoft Office 2013+（Word / PowerPoint）

## 快速开始

### 方式一：一键启动

双击 `start.bat`，自动安装依赖并启动服务。

### 方式二：手动启动

```bash
pip install -r requirements.txt
python run.py
```

浏览器打开 **http://localhost:8001**。

### 自定义参数

```bash
python run.py --host 0.0.0.0 --port 8080 --reload
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `127.0.0.1` | 绑定地址 |
| `--port` | `8001` | 监听端口 |
| `--reload` | 关闭 | 开发热重载 |

## 功能

| 功能 | 引擎 | 说明 |
|------|------|------|
| Word → PDF | Microsoft Word COM | .doc / .docx，支持批量；实例复用，Word/PPT 可并行 |
| PPT → PDF | Microsoft PowerPoint COM | .ppt / .pptx，支持批量；实例复用 |
| 图片 → PDF | PIL | 多图合并，每张一页；可选 A4 页面（居中） |
| 图片格式互转 | PIL | png / jpg / webp / gif / bmp / tiff / ico |
| PDF → Word | pdf2docx | 解析重建，不重排 |
| PDF 合并 | pypdf | 多 PDF 按序合并 |
| PDF 拆分 | pypdf | 按指定页 / 每页拆分 |
| PDF 删页 | pypdf | 预览后点击删除 |
| PDF 压缩 | PyMuPDF + PIL | 三档：轻度 / 推荐 / 极致；去重 + 超大图降级 |
| PDF 预览 | PyMuPDF | 分页缩略图，首批即时渲染，其余滚动按需加载 |
| 任务进度 | 内存存储 | Word/PPT/压缩实时进度，前端轮询展示 |

## 目录结构

```
├── app.py                  # FastAPI 主入口
├── config.py               # 配置（支持环境变量覆盖）
├── run.py                  # 启动脚本
├── start.bat               # Windows 一键启动
├── requirements.txt        # 依赖声明
├── requirements.lock       # 依赖锁定
│
├── engines/                # 引擎层
│   ├── com_engine.py       # COM 引擎（Word/PPT 转换）
│   ├── pdf_engine.py       # PDF 引擎（压缩/预览/PDF→Word）
│   └── image_engine.py     # 图片引擎（格式转换/合并）
│
├── routers/                # 路由层
│   ├── convert.py          # 转换接口
│   ├── pdf_ops.py          # PDF 操作接口
│   ├── download.py         # 文件下载
│   └── system.py           # 健康检查 / 关闭服务
│
├── utils/                  # 工具层
│   ├── file_utils.py       # 文件操作 / 类型校验 / 文件名清洗 / 清理
│   ├── task_progress.py    # 任务进度存储（内存，供轮询）
│   └── logging_config.py   # 日志配置
│
├── tests/                  # 测试（99 个用例，含路由层安全测试）
│
├── static/
│   └── index.html          # 前端页面
├── uploads/                # 临时上传（自动清理）
├── outputs/                # 转换输出（保留 24h）
└── logs/                   # 运行日志
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PDF_MAX_UPLOAD_SIZE` | `209715200` | 上传大小限制（字节，默认 200MB） |
| `PDF_MAX_FILES_PER_REQUEST` | `20` | 单次请求最多上传文件数 |
| `PDF_PREVIEW_MAX_PAGES` | `200` | 可预览的最大页数 |
| `PDF_PREVIEW_DPI` | `72` | 预览图片 DPI |
| `PDF_PREVIEW_INITIAL_PAGES` | `12` | 首批即时渲染的页数（其余按需加载） |
| `PDF_PREVIEW_CACHE_SECONDS` | `3600` | 预览缓存文件保留时间（秒） |
| `PDF_COM_TIMEOUT` | `120` | COM 操作超时（秒） |
| `PDF_COMPRESS_MAX_IMAGE_BYTES` | `52428800` | 超过该大小的单张图片不重压缩（防内存峰值） |
| `PDF_FILE_RETENTION` | `86400` | 输出文件保留时间（秒） |
| `PDF_MAX_FILES_PER_DIR` | `500` | 目录文件数上限 |
| `PDF_CORS_ORIGINS` | 空（关闭跨域） | CORS 允许来源，逗号分隔，如 `http://a.com,http://b.com` |
| `PDF_SHUTDOWN_TOKEN` | 空 | 配置后 `/api/shutdown` 需携带匹配的 `X-Shutdown-Token` 头；未配置时仅限本机调用 |
| `PDF_LOG_LEVEL` | `INFO` | 日志级别 |

## 运行测试

```bash
python -m pytest tests/ -v
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/convert` | Word → PDF（可 `task_id` 轮询进度） |
| POST | `/api/convert-ppt` | PPT → PDF（可 `task_id` 轮询进度） |
| POST | `/api/convert-image` | 图片 → PDF（可选 `page_size=fit/a4`） |
| POST | `/api/convert-format` | 图片格式互转（`target` 参数） |
| POST | `/api/pdf-to-word` | PDF → Word |
| POST | `/api/merge-pdf` | PDF 合并 |
| POST | `/api/split-pdf` | PDF 拆分（`positions` 参数） |
| POST | `/api/preview-pages` | PDF 预览（返回 `preview_id` + 首批缩略图） |
| GET | `/api/preview-page` | 按需加载单页缩略图（`preview_id` + `page`） |
| POST | `/api/delete-pages` | PDF 删页（`pages` 参数） |
| POST | `/api/compress-pdf` | PDF 压缩（`level`，返回压缩统计与图片处理数） |
| GET | `/api/task/{task_id}` | 轮询长任务进度 |
| POST | `/api/shutdown` | 关闭服务（本机 / token 鉴权） |
| GET | `/api/health` | 健康检查 |
| GET | `/api/download/{id}` | 文件下载（`ext` 可选：pdf/zip/docx） |
