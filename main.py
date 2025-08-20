# main.py
import asyncio
import sys
import logging

# --- 配置导入 ---
from config.playwright_builtin import (
    PlaywrightConfig,
    BROWSER_EXECUTABLE_PATH,
    USER_DATA_ROOT,
    DATABASE_CONFIG,
)
from config.logging_config import setup_logging

# --- 核心组件和脚本导入 ---
from core.browser import PlaywrightBrowser, BrowserConfig, SessionConfig
from scripts.cvh_scraper import scrape_list_pages, scrape_detail_page

# --- 辅助工具导入 ---
from utils.startup import (
    load_configs,
    validate_browser_path,
    check_and_install_browser,
)
from utils.database import DatabaseManager

# --- 全局任务参数 ---
TOTAL_RECORDS = 8549727
RECORDS_PER_PAGE = 30
# 列表页和详情页的并发消费者数量可以独立配置
LIST_CONSUMERS = 4
DETAIL_CONSUMERS = 8
PAGES_PER_LIST_TASK = 10  # 每个列表页任务包含的页面数


async def list_producer(queue: asyncio.Queue):
    """生产者：生成列表页采集任务"""
    logging.info("LIST_PRODUCER: Started.")
    total_pages = (TOTAL_RECORDS + RECORDS_PER_PAGE - 1) // RECORDS_PER_PAGE
    
    for page_start in range(0, total_pages, PAGES_PER_LIST_TASK):
        offset = page_start * RECORDS_PER_PAGE
        task_info = {"offset": offset, "pages": PAGES_PER_LIST_TASK}
        await queue.put(task_info)
        
    for _ in range(LIST_CONSUMERS):
        await queue.put(None)
    logging.info("LIST_PRODUCER: Finished.")


async def list_consumer(
    worker_id: int,
    list_queue: asyncio.Queue,
    detail_queue: asyncio.Queue,
    browser_manager: PlaywrightBrowser,
    session_config: SessionConfig,
    db_manager: DatabaseManager,
):
    """消费者：处理列表页任务，并将detail_id送入详情页队列"""
    logging.info(f"LIST_CONSUMER_{worker_id}: Started.")
    session_name = f"list_worker_{worker_id}"

    while True:
        task_info = await list_queue.get()
        if task_info is None:
            logging.info(f"LIST_CONSUMER_{worker_id}: Received end signal.")
            break

        await scrape_list_pages(
            browser_manager,
            session_config,
            session_name=session_name,
            db_manager=db_manager,
            detail_task_queue=detail_queue,
            max_pages=task_info["pages"],
            offset=task_info["offset"],
        )
        list_queue.task_done()
    logging.info(f"LIST_CONSUMER_{worker_id}: Shutting down.")


async def detail_consumer(
    worker_id: int,
    detail_queue: asyncio.Queue,
    browser_manager: PlaywrightBrowser,
    session_config: SessionConfig,
    db_manager: DatabaseManager,
):
    """消费者：处理详情页任务"""
    logging.info(f"DETAIL_CONSUMER_{worker_id}: Started.")
    session_name = f"detail_worker_{worker_id}"

    while True:
        detail_id = await detail_queue.get()
        if detail_id is None:
            logging.info(f"DETAIL_CONSUMER_{worker_id}: Received end signal.")
            break

        await scrape_detail_page(
            browser_manager,
            session_config,
            session_name=session_name,
            db_manager=db_manager,
            detail_id=detail_id,
        )
        detail_queue.task_done()
    logging.info(f"DETAIL_CONSUMER_{worker_id}: Shutting down.")


async def main():
    """项目主函数"""
    setup_logging()

    if not BROWSER_EXECUTABLE_PATH:
        await check_and_install_browser()
    elif not validate_browser_path(BROWSER_EXECUTABLE_PATH):
        sys.exit(1)

    browser_config, session_config = load_configs(
        PlaywrightConfig, USER_DATA_ROOT, BROWSER_EXECUTABLE_PATH
    )

    db_manager = DatabaseManager(DATABASE_CONFIG)
    await db_manager.initialize()

    list_task_queue = asyncio.Queue()
    detail_task_queue = asyncio.Queue(maxsize=1000) # 限制队列大小以控制内存

    try:
        async with PlaywrightBrowser(browser_config) as browser_manager:
            # 1. 启动列表页生产者和消费者
            list_producer_task = asyncio.create_task(list_producer(list_task_queue))
            list_consumer_tasks = [
                asyncio.create_task(
                    list_consumer(i + 1, list_task_queue, detail_task_queue, browser_manager, session_config, db_manager)
                ) for i in range(LIST_CONSUMERS)
            ]
            
            # 2. 启动详情页消费者
            detail_consumer_tasks = [
                asyncio.create_task(
                    detail_consumer(i + 1, detail_task_queue, browser_manager, session_config, db_manager)
                ) for i in range(DETAIL_CONSUMERS)
            ]

            # 3. 等待列表页任务完成
            await list_producer_task
            await list_task_queue.join()
            await asyncio.gather(*list_consumer_tasks)

            # 4. 列表页任务完成后，向详情页队列发送结束信号
            for _ in range(DETAIL_CONSUMERS):
                await detail_task_queue.put(None)

            # 5. 等待详情页任务完成
            await detail_task_queue.join()
            await asyncio.gather(*detail_consumer_tasks)

    finally:
        await db_manager.close()
    logging.info("All tasks completed. Shutting down.")


if __name__ == "__main__":
    asyncio.run(main())