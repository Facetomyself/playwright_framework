# config/playwright_builtin.py
from pathlib import Path

# --- 基础路径配置 ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- 浏览器相关配置 ---
# 使用 Playwright 内置浏览器，因此 BROWSER_EXECUTABLE_PATH 设置为 None
BROWSER_EXECUTABLE_PATH = None

# 浏览器数据存储根目录
USER_DATA_ROOT = BASE_DIR / "data" / "session_data"

# --- 指纹持久化配置 ---
SAVE_FINGERPRINT = False
FINGERPRINT_DB_PATH = BASE_DIR / "data" / "fingerprints.jsonl"


# --- 数据库配置 ---
DATABASE_CONFIG = {
    "host": "106.15.239.221",
    "port": 3306,
    "user": "root",
    "password": "z4JDcvkIkSIRbHge",
    "db": "cvh_data",
}


# --- Playwright 框架配置 ---
class PlaywrightConfig:
    """Playwright 浏览器和会话的详细配置 (使用内置浏览器)"""

    # 全局浏览器配置
    BROWSER_CONFIG = {
        "headless": True,
        # 使用 Playwright 自动下载和管理的 Chromium 浏览器。
        # 移除 channel 配置，让 Playwright 使用其默认的、通过 `playwright install` 安装的浏览器。
        "slow_mo": 0,
        "args": [
            "--disable-infobars",
            "--disable-blink-features=AutomationControlled",
        ],
    }

    # 通用浏览器会话配置
    SESSION_CONFIG = {
        "init_script_path": BASE_DIR / "core" / "init_scripts" / "stealth.min.js",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1920, "height": 1080},
        "browser_args": [
            "--timezone=Asia/Shanghai",
            "--lang=zh-CN",
            "--accept-lang=zh-CN",
            "--fpseed=12lfsfffaughu98",
        ],
    }

# 确保数据目录存在
USER_DATA_ROOT.mkdir(parents=True, exist_ok=True)