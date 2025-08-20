# Playwright 多上下文并发采集框架

这是一个基于 Playwright 构建的、支持多上下文并发的 Python 自动化采集框架。它被设计为高度可配置、模块化，并集成了高级浏览器指纹伪装、环境自动修复、性能监控和动态并发控制功能，适用于需要管理多个独立会话、并要求稳定持久化的采集任务。

## 核心特性

- **多上下文并发**: 基于 `asyncio` 和 Playwright 的 `BrowserContext`，支持在单个浏览器实例中并发运行多个完全隔离的会话。
- **环境变量配置**: 支持通过 `.env` 文件管理敏感配置信息，提高安全性。
- **双模式配置**: 支持两种开箱即用的浏览器配置模式：
    1.  **自定义浏览器**: 可指定本地任意 Chromium 核心的浏览器路径。
    2.  **Playwright 内置浏览器**: 自动管理和使用 Playwright 官方的浏览器，启动速度更快。
- **持久化会话**: 自动通过 `storage_state` 机制保存和加载每个会话的 Cookies 和 LocalStorage，支持断点续采和维持登录状态。
- **高级指纹伪装**: 支持从配置文件加载指纹信息，并在页面初始化时通过注入脚本动态伪装 `navigator` 等关键对象，增强隐蔽性。
- **环境自修复**: 当使用 Playwright 内置浏览器时，框架会自动检测浏览器是否已安装，如果未安装，将**自动执行安装命令**，极大提升了首次运行的鲁棒性。
- **性能监控**: 内置性能监控系统，实时统计处理速度、错误率等指标，支持日志轮转。
- **动态并发控制**: 根据运行状态自动调整并发数，优化资源利用率。
- **错误重试机制**: 网络请求失败时自动重试，支持指数退避策略。
- **事务性数据保存**: 确保数据一致性，失败时自动回滚。
- **优雅关闭**: 支持信号处理，实现程序的优雅关闭和资源清理。
- **模块化项目结构**: 清晰地分离了配置 (`config`)、核心框架 (`core`)、辅助工具 (`utils`) 和业务脚本 (`scripts`)，易于维护和扩展。

## 项目结构

```
.
├── .env                        # 环境变量配置文件（敏感信息）
├── .gitignore                  # Git忽略文件配置
├── config/
│   ├── default.py             # [配置] 使用自定义浏览器的配置
│   ├── playwright_builtin.py  # [配置] 使用 Playwright 内置浏览器的配置
│   └── logging_config.py      # [配置] 日志格式和级别的配置
├── core/
│   ├── browser.py             # 核心框架，包含 PlaywrightBrowser 和 BrowserSession
│   └── init_scripts/          # 存放页面初始化时注入的 JS 脚本
├── utils/
│   ├── database.py            # 数据库管理模块，支持事务和批量操作
│   └── startup.py             # 存放启动相关的辅助函数 (配置加载、环境检查等)
├── browser/                   # (可选) 存放自定义的浏览器可执行文件
│   └── Chrome-bin/
├── data/
│   ├── fingerprints.jsonl     # (可选) 持久化保存的浏览器指纹记录
│   └── session_data/          # 存放每个会话的持久化文件 (_state.json)
├── logs/                      # 日志文件目录（自动创建）
├── scripts/
│   └── cvh_scraper.py         # 具体的业务逻辑脚本，包含重试和错误处理
├── main.py                    # 项目主入口，包含性能监控和动态并发控制
└── README.md                  # 项目说明文档
```

## 如何使用

### 1. 安装依赖

项目主要依赖 `playwright` 和 `python-dotenv`。请通过以下命令安装：

```bash
pip install playwright python-dotenv aiomysql
```
*(您**无需**手动运行 `playwright install`，如果需要，程序首次运行时会自动为您安装。)*

### 2. 配置

框架支持环境变量配置和代码配置两种方式。

#### 环境变量配置（推荐）

1. 复制 `.env` 文件并修改其中的配置：
```bash
cp .env .env.local  # 复制并修改为本地配置
```

2. 编辑 `.env` 文件，设置您的配置：
```env
# 数据库配置
DB_HOST=your_database_host
DB_PORT=3306
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=your_database_name

# 并发控制配置
LIST_CONSUMERS=2
DETAIL_CONSUMERS=4

# 其他配置
BROWSER_HEADLESS=true
SAVE_FINGERPRINT=false
LOG_LEVEL=INFO
```

#### 代码配置

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

#### 配置说明

- **数据库配置**: 通过环境变量或配置文件设置数据库连接信息
- **并发控制**: `LIST_CONSUMERS` 和 `DETAIL_CONSUMERS` 控制列表页和详情页的并发数
- **浏览器配置**: `BROWSER_HEADLESS` 控制是否启用无头模式
- **日志配置**: `LOG_LEVEL` 设置日志级别，支持 DEBUG、INFO、WARNING、ERROR
- **指纹配置**: `SAVE_FINGERPRINT` 控制是否保存浏览器指纹信息

### 3. 编写业务脚本

业务逻辑与框架核心解耦，存放在 `scripts/` 目录中。

1.  在 `scripts/` 目录下创建一个新的 Python 文件。
2.  参考 `scripts/cvh_scraper.py`，创建一个 `async` 函数，它接收 `browser_manager` 和 `session_config` 等参数。
3.  在函数内部，通过 `browser_manager.create_session(...)` 创建会话，并使用 `async with` 管理其生命周期。

### 4. 运行

所有任务都在 `main.py` 的 `main` 函数中定义和启动。

1. 确保已正确配置 `.env` 文件。
2. 在终端中运行 `python main.py` 来启动项目：

```bash
python main.py
```

#### 运行特性

- **自动重试**: 网络请求失败时会自动重试，最大重试次数和间隔时间可配置
- **性能监控**: 程序运行时会实时显示性能统计信息，包括处理速度、错误率等
- **动态并发**: 系统会根据运行状态自动调整并发数，优化性能
- **优雅关闭**: 按 `Ctrl+C` 可以优雅地关闭程序，等待当前任务完成并清理资源
- **日志记录**: 所有日志会同时输出到控制台和 `logs/` 目录下的日志文件

#### 监控指标

运行时会显示以下监控信息：
- **处理速度**: 每秒处理的页面数
- **错误率**: 错误任务占总任务的比例
- **并发数**: 当前的列表页和详情页并发数量
- **任务统计**: 已完成的任务数量和类型

### 5. 扩展开发

#### 添加新的业务脚本

1. 在 `scripts/` 目录下创建新的 Python 文件
2. 参考 `cvh_scraper.py` 实现业务逻辑
3. 在 `main.py` 中导入并启动新的任务

#### 自定义监控指标

可以通过修改 `PerformanceMonitor` 类来添加自定义监控指标。

#### 错误处理策略

框架提供了多种错误处理策略：
- **重试装饰器**: `@retry_on_failure(max_retries=3, delay=2, backoff=2)`
- **事务处理**: `save_data_transactional()` 确保数据一致性
- **降级处理**: 关键功能失败时的降级方案

## 数据输出

- **业务数据**: 由您的业务脚本决定，存储在配置的数据库中。
- **会话状态**: 保存在 `data/session_data/[session_name]_state.json`。
- **指纹数据**: 如果开启，保存在 `data/fingerprints.jsonl`。
- **日志文件**: 运行时日志保存在 `logs/` 目录下，按日期分割。
- **性能统计**: 程序结束时会输出完整的性能统计信息，包括：
  - 总运行时间
  - 处理的页面数量和速度
  - 错误统计和错误率
  - 重试次数统计

## 故障排除

### 常见问题

1. **数据库连接失败**
   - 检查 `.env` 文件中的数据库配置是否正确
   - 确保数据库服务正在运行

2. **浏览器启动失败**
   - 检查浏览器路径配置是否正确
   - 运行 `playwright install` 安装浏览器

3. **高错误率**
   - 检查网络连接稳定性
   - 适当调整并发数配置
   - 查看日志文件获取详细错误信息

4. **内存使用过高**
   - 减少 `DETAIL_QUEUE_SIZE` 配置
   - 降低并发数配置
   - 检查是否有内存泄漏

### 日志分析

日志文件包含详细的运行信息：
- `INFO` 级别：正常运行信息
- `WARNING` 级别：警告信息
- `ERROR` 级别：错误信息，包含堆栈跟踪

可以通过调整 `LOG_LEVEL` 环境变量来控制日志详细程度。

## 贡献指南

欢迎提交 Issue 和 Pull Request 来改进框架。

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。