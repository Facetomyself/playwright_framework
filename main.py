# main.py
import asyncio
import logging

from config.default import (
    PlaywrightConfig,
    BROWSER_EXECUTABLE_PATH,
    USER_DATA_ROOT,
)
from core.browser import (
    PlaywrightBrowser,
    BrowserConfig,
    SessionConfig,
)
# 导入新的采集脚本任务
from scripts.cvh_scraper import scrape_cvh_data


async def main():
    """项目主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. 从配置文件加载并组合浏览器配置
    browser_cfg_dict = PlaywrightConfig.BROWSER_CONFIG
    if BROWSER_EXECUTABLE_PATH:
        browser_cfg_dict["executable_path"] = str(BROWSER_EXECUTABLE_PATH)
    browser_config = BrowserConfig(**browser_cfg_dict)

    # 2. 从配置文件加载会话配置
    session_cfg_dict = PlaywrightConfig.SESSION_CONFIG
    session_cfg_dict["user_data_root"] = USER_DATA_ROOT
    session_config = SessionConfig(**session_cfg_dict)

    # 3. 启动浏览器管理器
    async with PlaywrightBrowser(browser_config) as browser_manager:
        # 4. 演示多上下文：创建两个并发的采集任务
        task1 = scrape_cvh_data(
            browser_manager,
            session_config,
            session_name="cvh_session_1",
            max_pages=100,  # 为了演示，每个任务只跑2页
        )
        task2 = scrape_cvh_data(
            browser_manager,
            session_config,
            session_name="cvh_session_2",
            max_pages=100,
        )
        task3 = scrape_cvh_data(
            browser_manager,
            session_config,
            session_name="cvh_session_3",
            max_pages=100,
        )
        task4 = scrape_cvh_data(
            browser_manager,
            session_config,
            session_name="cvh_session_4",
            max_pages=100,
        )

        # 使用 asyncio.gather 并发运行这两个任务
        await asyncio.gather(task1, task2, task3, task4)


if __name__ == "__main__":
    # 验证自定义浏览器路径是否存在
    if BROWSER_EXECUTABLE_PATH and not BROWSER_EXECUTABLE_PATH.exists():
        logging.error(
            f"Browser executable not found at: {BROWSER_EXECUTABLE_PATH}"
        )
        logging.error(
            "Please check the BROWSER_EXECUTABLE_PATH in 'config/default.py'"
        )
    else:
        asyncio.run(main())