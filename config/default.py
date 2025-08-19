# config/default.py
from pathlib import Path
from typing import List, Dict

# --- 基础路径配置 ---
# 项目根目录
# Path(__file__) -> d:/Chrome/config/default.py
# .parent -> d:/Chrome/config
# .parent -> d:/Chrome
BASE_DIR = Path(__file__).resolve().parent.parent

# --- 浏览器相关配置 ---
# 自定义浏览器主程序路径
# 恢复使用自定义浏览器路径
BROWSER_EXECUTABLE_PATH = BASE_DIR / "chrome" / "Chrome-bin" / "chrome.exe"

# 浏览器数据存储根目录
USER_DATA_ROOT = BASE_DIR / "data" / "session_data"

# --- 指纹持久化配置 ---
# 是否开启指纹采集与保存功能
SAVE_FINGERPRINT = False
# 指纹数据库文件路径 (使用 .jsonl 格式，方便追加)
FINGERPRINT_DB_PATH = BASE_DIR / "data" / "fingerprints.jsonl"


# --- Playwright 框架配置 ---
class PlaywrightConfig:
    """Playwright 浏览器和会话的详细配置"""

    # 全局浏览器配置
    BROWSER_CONFIG = {
        "headless": False,
        # 当使用 executable_path 时，不应指定 channel
        # "channel": "chrome",
        "slow_mo": 50,  # 慢速模式，单位毫秒，方便观察
        # 参考 test/playwrightTest.py 添加的浏览器启动参数
        "args": [
            "--timezone=Asia/Shanghai",
            "--lang=zh-CN",
            "--accept-lang=zh-CN",
            "--fpseed=12lfsfffaughu98",  # 示例指纹种子
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
    }

# 确保数据目录存在 (包括父目录)
USER_DATA_ROOT.mkdir(parents=True, exist_ok=True)