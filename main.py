# main.py
import asyncio
import sys

# --- 配置导入 ---
# 通过修改这里的导入来切换配置 (default 或 playwright_builtin)
from config.playwright_builtin import (
    PlaywrightConfig,
    BROWSER_EXECUTABLE_PATH,
    USER_DATA_ROOT,
)
from config.logging_config import setup_logging

# --- 核心组件和脚本导入 ---
from core.browser import PlaywrightBrowser
from scripts.cvh_scraper import scrape_cvh_data

# --- 辅助工具导入 ---
from utils.startup import (
    load_configs,
    validate_browser_path,
    check_and_install_browser,
)


async def main():
    """项目主函数"""
    setup_logging()

    # 如果使用内置浏览器，检查是否已安装，否则自动安装
    if not BROWSER_EXECUTABLE_PATH:
        await check_and_install_browser()
    # 如果使用自定义浏览器，验证路径
    elif not validate_browser_path(BROWSER_EXECUTABLE_PATH):
        sys.exit(1)

    # 加载浏览器和会话配置
    browser_config, session_config = load_configs(
        PlaywrightConfig, USER_DATA_ROOT, BROWSER_EXECUTABLE_PATH
    )

    # 启动浏览器管理器并分配任务
    async with PlaywrightBrowser(browser_config) as browser_manager:
        tasks = [
            scrape_cvh_data(
                browser_manager,
                session_config,
                session_name=f"cvh_session_{i}",
                max_pages=2,
            )
            for i in range(1, 5)
        ]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())