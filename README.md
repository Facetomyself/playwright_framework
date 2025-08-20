# Playwright 多上下文并发采集框架

这是一个基于 Playwright 构建的、支持多上下文并发的 Python 自动化采集框架。它被设计为高度可配置、模块化，并集成了高级浏览器指纹伪装和环境自动修复功能，适用于需要管理多个独立会话、并要求稳定持久化的采集任务。

## 核心特性

- **多上下文并发**: 基于 `asyncio` 和 Playwright 的 `BrowserContext`，支持在单个浏览器实例中并发运行多个完全隔离的会话。
- **双模式配置**: 支持两种开箱即用的浏览器配置模式：
    1.  **自定义浏览器**: 可指定本地任意 Chromium 核心的浏览器路径。
    2.  **Playwright 内置浏览器**: 自动管理和使用 Playwright 官方的浏览器，启动速度更快。
- **持久化会话**: 自动通过 `storage_state` 机制保存和加载每个会话的 Cookies 和 LocalStorage，支持断点续采和维持登录状态。
- **高级指纹伪装**: 支持从配置文件加载指纹信息，并在页面初始化时通过注入脚本动态伪装 `navigator` 等关键对象，增强隐蔽性。
- **环境自修复**: 当使用 Playwright 内置浏览器时，框架会自动检测浏览器是否已安装，如果未安装，将**自动执行安装命令**，极大提升了首次运行的鲁棒性。
- **模块化项目结构**: 清晰地分离了配置 (`config`)、核心框架 (`core`)、辅助工具 (`utils`) 和业务脚本 (`scripts`)，易于维护和扩展。

## 项目结构

```
.
├── config/
│   ├── default.py             # [配置] 使用自定义浏览器的配置
│   ├── playwright_builtin.py  # [配置] 使用 Playwright 内置浏览器的配置
│   └── logging_config.py      # [配置] 日志格式和级别的配置
├── core/
│   ├── browser.py             # 核心框架，包含 PlaywrightBrowser 和 BrowserSession
│   └── init_scripts/          # 存放页面初始化时注入的 JS 脚本
├── utils/
│   └── startup.py             # 存放启动相关的辅助函数 (配置加载、环境检查等)
├── browser/                   # (可选) 存放自定义的浏览器可执行文件
│   └── Chrome-bin/
├── data/
│   ├── fingerprints.jsonl     # (可选) 持久化保存的浏览器指纹记录
│   └── session_data/          # 存放每个会话的持久化文件 (_state.json)
├── scripts/
│   └── cvh_scraper.py         # 具体的业务逻辑脚本
├── main.py                    # 项目主入口，协调并启动业务任务
└── README.md                  # 项目说明文档
```

## 如何使用

### 1. 安装依赖

项目主要依赖 `playwright`。请通过以下命令安装：

```bash
pip install playwright
```
*(您**无需**手动运行 `playwright install`，如果需要，程序首次运行时会自动为您安装。)*

### 2. 配置

框架的核心配置通过切换 `main.py` 中的导入来实现。

- **要使用 Playwright 内置浏览器 (推荐，启动快)**:
  确保 `main.py` 中导入的是 `config.playwright_builtin`。
  ```python
  # main.py
  from config.playwright_builtin import (
      PlaywrightConfig,
      BROWSER_EXECUTABLE_PATH,
      USER_DATA_ROOT,
  )
  ```

- **要使用自定义浏览器**:
  1.  将您的浏览器文件放在项目中的某个位置 (例如 `browser/Chrome-bin/`)。
  2.  打开 `config/default.py` 并正确设置 `BROWSER_EXECUTABLE_PATH`。
  3.  修改 `main.py`，将导入切换为 `config.default`。
  ```python
  # main.py
  from config.default import (
      PlaywrightConfig,
      BROWSER_EXECUTABLE_PATH,
      USER_DATA_ROOT,
  )
  ```

- **其他配置**:
  - **指纹**: 在 `config` 文件中设置 `SAVE_FINGERPRINT` 来开启或关闭指纹采集。
  - **日志**: 在 `config/logging_config.py` 中修改日志格式。
  - **浏览器参数**: 在 `config` 文件中的 `PlaywrightConfig` 类里修改。

### 3. 编写业务脚本

业务逻辑与框架核心解耦，存放在 `scripts/` 目录中。

1.  在 `scripts/` 目录下创建一个新的 Python 文件。
2.  参考 `scripts/cvh_scraper.py`，创建一个 `async` 函数，它接收 `browser_manager` 和 `session_config` 等参数。
3.  在函数内部，通过 `browser_manager.create_session(...)` 创建会话，并使用 `async with` 管理其生命周期。

### 4. 运行

所有任务都在 `main.py` 的 `main` 函数中定义和启动。

1.  打开 `main.py`。
2.  在 `async with PlaywrightBrowser(...)` 块中，定义您想运行的任务列表。
3.  使用 `asyncio.gather(*tasks)` 来并发执行它们。
4.  在终端中运行 `python main.py` 来启动项目。

## 数据输出

- **业务数据**: 由您的业务脚本决定。
- **会话状态**: 保存在 `data/session_data/[session_name]_state.json`。
- **指纹数据**: 如果开启，保存在 `data/fingerprints.jsonl`。