# config/default.py
from pathlib import Path
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# --- 基础路径配置 ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- 浏览器相关配置 ---
BROWSER_EXECUTABLE_PATH = BASE_DIR / "chrome" / "Chrome-bin" / "chrome.exe"

# 浏览器数据存储根目录
USER_DATA_ROOT = BASE_DIR / "data" / "session_data"

# --- 指纹持久化配置 ---
SAVE_FINGERPRINT = os.getenv("SAVE_FINGERPRINT", "false").lower() == "true"
FINGERPRINT_DB_PATH = BASE_DIR / "data" / "fingerprints.jsonl"


# --- Playwright 框架配置 ---
class PlaywrightConfig:
    """Playwright 浏览器和会话的详细配置"""

    # 全局浏览器配置
    BROWSER_CONFIG = {
        "headless": os.getenv("BROWSER_HEADLESS", "true").lower() == "true",
        # 当使用 executable_path 时，不应指定 channel
        # "channel": "chrome",
        "slow_mo": int(os.getenv("BROWSER_SLOW_MO", "0")),
        "args": [
            "--disable-infobars",
            "--disable-blink-features=AutomationControlled",
        ],
    }

    # 通用浏览器会话配置
    SESSION_CONFIG = {
        # user_data_root 将在主逻辑中从上面的常量动态传入
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
            "--fpseed=12lfsfffaughu98",  # 示例指纹种子
        ],
    }

# 确保数据目录存在 (包括父目录)
USER_DATA_ROOT.mkdir(parents=True, exist_ok=True)