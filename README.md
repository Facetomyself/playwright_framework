# Playwright 多上下文并发采集框架

这是一个基于 Playwright 构建的、支持多上下文并发的 Python 自动化采集框架。它被设计为高度可配置、模块化，并集成了高级浏览器指rin采集功能，适用于需要管理多个独立会话、并要求稳定持久化的采集任务。

## 核心特性

- **多上下文并发**: 基于 `asyncio` 和 Playwright 的 `BrowserContext`，支持在单个浏览器实例中并发运行多个完全隔离的会话。
- **集中化配置**: 所有关键配置，如浏览器路径、启动参数、数据目录等，都在 `config/default.py` 中统一管理。
- **持久化会话**: 自动通过 `storage_state` 机制保存和加载每个会话的 Cookies 和 LocalStorage，支持断点续采和维持登录状态。
- **高级指纹采集**: 可选功能，能够通过注入 JS 采集详细的浏览器环境指纹（Navigator, Screen, WebGL 等），并以非阻塞方式持久化保存，便于追溯和分析。
- **模块化项目结构**: 清晰地分离了配置 (`config`)、核心框架 (`core`)、浏览器文件 (`browser`)、数据 (`data`) 和业务脚本 (`scripts`)，易于维护和扩展。

## 项目结构

```
.
├── config/
│   └── default.py         # 存放所有配置，如路径、浏览器参数
├── core/
│   ├── browser.py         # 核心框架，包含 PlaywrightBrowser 和 BrowserSession 管理器
│   ├── init_scripts/      # 存放需要在页面初始化时注入的 JS 脚本
│   │   ├── get_fingerprint.js
│   │   └── stealth.min.js
├── browser/
│   └── Chrome-bin/        # 存放自定义的浏览器可执行文件
│       └── chrome.exe
├── data/
│   ├── fingerprints.jsonl # (可选) 持久化保存的浏览器指纹记录
│   └── session_data/      # 存放每个会话的持久化文件 (_state.json)
├── scripts/
│   └── cvh_scraper.py     # 具体的业务逻辑脚本
├── main.py                # 项目主入口，用于启动指定的业务脚本
└── README.md              # 项目说明文档
```

## 如何使用

### 1. 安装依赖

项目主要依赖 `playwright`。请通过以下命令安装：

```bash
pip install playwright
playwright install
```
*(`playwright install` 会下载框架所需的浏览器核心)*

### 2. 配置

打开 `config/default.py` 文件进行自定义配置：

- **浏览器路径**:
  - 如果您想使用**自定义**的浏览器，请设置 `BROWSER_EXECUTABLE_PATH` 为您的 `chrome.exe` 的绝对或相对路径。
  - 如果您想使用 Playwright **自动管理**的浏览器，请将 `BROWSER_EXECUTABLE_PATH` 设置为 `None`，并在 `PlaywrightConfig.BROWSER_CONFIG` 中设置 `"channel": "chrome"`。

- **指纹采集**:
  - 通过设置 `SAVE_FINGERPRINT = True` 或 `False` 来开启或关闭高级指紋采集功能。
  - `FINGERPRINT_DB_PATH` 指定了指纹记录的保存位置。

- **浏览器启动参数**:
  - 在 `PlaywrightConfig.BROWSER_CONFIG` 的 `"args"` 列表中，您可以自定义浏览器启动时使用的命令行参数。

### 3. 编写业务脚本

1. 在 `scripts/` 目录下创建一个新的 Python 文件（例如 `my_task.py`）。
2. 在该文件中，创建一个 `async` 函数，它必须接收 `browser_manager: PlaywrightBrowser` 和 `session_config: SessionConfig` 两个参数。
3. 在函数内部，通过 `browser_manager.create_session("your_unique_session_name", session_config)` 来创建一个会话管理器。
4. 使用 `async with` 来管理会话的生命周期，并在其中通过 `await session.new_page()` 来获取页面进行操作。

### 4. 运行

1. 打开 `main.py` 文件。
2. 从您创建的脚本中导入您的 `async` 任务函数。
3. 在 `main` 函数的 `async with PlaywrightBrowser(...)` 块中，调用您的任务函数。
4. 您可以使用 `asyncio.gather()` 来并发地运行多个不同的任务。
5. 在终端中运行 `python main.py` 来启动项目。

## 数据输出

- **业务数据**: 由您的业务脚本决定，在 `cvh_scraper.py` 示例中，数据被保存在项目根目录下的 `.csv` 文件中。
- **会话状态**: 每个会话的 Cookies 和 LocalStorage 被保存在 `data/session_data/[session_name]_state.json` 文件中。
- **指纹数据**: 如果开启，每个会话的浏览器指纹将被追加到 `data/fingerprints.jsonl` 文件中。