# utils/startup.py
import logging
import subprocess
import sys
from pathlib import Path
from typing import Tuple
from dotenv import load_dotenv

from playwright.async_api import async_playwright

from core.browser import BrowserConfig, SessionConfig

# 加载环境变量
load_dotenv()


def load_configs(
    PlaywrightConfig, USER_DATA_ROOT: Path, BROWSER_EXECUTABLE_PATH: Path | None
) -> Tuple[BrowserConfig, SessionConfig]:
    """从配置类和常量中加载并组合浏览器和会话配置对象"""
    browser_cfg_dict = PlaywrightConfig.BROWSER_CONFIG
    if BROWSER_EXECUTABLE_PATH:
        browser_cfg_dict["executable_path"] = str(BROWSER_EXECUTABLE_PATH)
    browser_config = BrowserConfig(**browser_cfg_dict)

    session_cfg_dict = PlaywrightConfig.SESSION_CONFIG
    session_cfg_dict["user_data_root"] = USER_DATA_ROOT
    session_config = SessionConfig(**session_cfg_dict)

    return browser_config, session_config


def validate_browser_path(executable_path: Path | None):
    """验证自定义浏览器可执行文件路径是否存在"""
    if executable_path and not executable_path.exists():
        logging.error(f"Browser executable not found at: {executable_path}")
        logging.error("Please check the BROWSER_EXECUTABLE_PATH in your config file.")
        return False
    return True


async def check_and_install_browser():
    """检查 Playwright 浏览器是否安装，如果没有则自动安装"""
    try:
        async with async_playwright() as p:
            # 尝试启动一个临时的浏览器来检查是否安装
            browser = await p.chromium.launch()
            await browser.close()
    except Exception as e:
        if 'Run "playwright install"' in str(e):
            logging.warning("Playwright browser not found. Attempting to install...")
            try:
                # 使用 subprocess 运行安装命令
                process = subprocess.run(
                    [sys.executable, "-m", "playwright", "install"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                logging.info("Playwright browser installed successfully.")
                logging.info(process.stdout)
            except subprocess.CalledProcessError as cpe:
                logging.error("Failed to install Playwright browser.")
                logging.error(cpe.stderr)
                sys.exit(1)
            except FileNotFoundError:
                logging.error("Could not find 'playwright' command. Is Playwright installed correctly in your environment?")
                sys.exit(1)
        else:
            # 其他启动错误
            logging.error(f"An unexpected error occurred while checking browser status: {e}")
            sys.exit(1)