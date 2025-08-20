# main.py
import asyncio
import sys
import logging
import os
import signal
import time
from contextlib import asynccontextmanager

# --- 配置导入 ---
from config.playwright_builtin import (
    PlaywrightConfig,
    BROWSER_EXECUTABLE_PATH,
    USER_DATA_ROOT,
)
from config.logging_config import setup_logging

# --- 核心组件和脚本导入 ---
from core.browser import PlaywrightBrowser
from scripts.cvh_scraper import scrape_list_pages, scrape_detail_page

# --- 辅助工具导入 ---
from utils.startup import (
    load_configs,
    validate_browser_path,
    check_and_install_browser,
)
from utils.database import DatabaseManager

# --- 示例项目配置 ---
# 注意：这些是示例项目的具体配置，实际项目中应该根据需要调整
TOTAL_RECORDS = 8549727
RECORDS_PER_PAGE = 30
LIST_CONSUMERS = 2
DETAIL_CONSUMERS = 4
PAGES_PER_LIST_TASK = 10
DETAIL_QUEUE_SIZE = 1000

# 示例项目数据库配置
EXAMPLE_DATABASE_CONFIG = {
    "host": "host",
    "port": 3306,
    "user": "root",
    "password": "password",
    "db": "db_name",
}

# 性能监控
class PerformanceMonitor:
    """性能监控类"""
    def __init__(self):
        self.start_time = time.time()
        self.list_pages_processed = 0
        self.detail_pages_processed = 0
        self.errors_count = 0
        self.retries_count = 0

    def increment_list_pages(self, count=1):
        self.list_pages_processed += count

    def increment_detail_pages(self, count=1):
        self.detail_pages_processed += count

    def increment_errors(self, count=1):
        self.errors_count += count

    def increment_retries(self, count=1):
        self.retries_count += count

    def get_stats(self):
        elapsed = time.time() - self.start_time
        total_pages = self.list_pages_processed + self.detail_pages_processed
        return {
            "elapsed_time": elapsed,
            "list_pages_processed": self.list_pages_processed,
            "detail_pages_processed": self.detail_pages_processed,
            "total_pages": total_pages,
            "pages_per_second": total_pages / elapsed if elapsed > 0 else 0,
            "errors_count": self.errors_count,
            "retries_count": self.retries_count,
            "error_rate": self.errors_count / max(total_pages, 1)
        }

    def log_stats(self):
        stats = self.get_stats()
        logging.info("=== 性能统计 ===")
        logging.info(f"运行时间: {stats['elapsed_time']:.2f} 秒")
        logging.info(f"列表页处理: {stats['list_pages_processed']}")
        logging.info(f"详情页处理: {stats['detail_pages_processed']}")
        logging.info(f"总页面数: {stats['total_pages']}")
        logging.info(f"处理速度: {stats['pages_per_second']:.2f} 页/秒")
        logging.info(f"错误次数: {stats['errors_count']}")
        logging.info(f"重试次数: {stats['retries_count']}")
        logging.info(f"错误率: {stats['error_rate']:.2%}")
        logging.info("==============")

performance_monitor = PerformanceMonitor()

# 动态并发控制
class ConcurrencyController:
    """动态并发控制"""
    def __init__(self, initial_list_consumers=2, initial_detail_consumers=4):
        self.list_consumers = initial_list_consumers
        self.detail_consumers = initial_detail_consumers
        self.error_threshold = 0.1  # 错误率阈值
        self.min_consumers = 1
        self.max_consumers = 8

    def adjust_concurrency(self, stats):
        """根据性能统计动态调整并发数"""
        error_rate = stats.get('error_rate', 0)
        pages_per_second = stats.get('pages_per_second', 0)

        # 如果错误率过高，减少并发
        if error_rate > self.error_threshold:
            self.list_consumers = max(self.list_consumers - 1, self.min_consumers)
            self.detail_consumers = max(self.detail_consumers - 1, self.min_consumers)
            logging.warning(f"High error rate ({error_rate:.2%}), reducing concurrency to {self.list_consumers}/{self.detail_consumers}")

        # 如果性能良好，可以考虑增加并发
        elif error_rate < 0.05 and pages_per_second > 10:
            self.list_consumers = min(self.list_consumers + 1, self.max_consumers)
            self.detail_consumers = min(self.detail_consumers + 1, self.max_consumers)
            logging.info(f"Good performance, increasing concurrency to {self.list_consumers}/{self.detail_consumers}")

        return self.list_consumers, self.detail_consumers

concurrency_controller = ConcurrencyController(LIST_CONSUMERS, DETAIL_CONSUMERS)

# 全局状态管理
class ApplicationState:
    """应用状态管理"""
    def __init__(self):
        self.is_shutting_down = False
        self.tasks_running = 0

app_state = ApplicationState()

# 优雅关闭处理
def signal_handler(signum, frame):
    """处理系统信号"""
    logging.info(f"Received signal {signum}, initiating graceful shutdown...")
    app_state.is_shutting_down = True

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

@asynccontextmanager
async def managed_resources():
    """资源管理上下文管理器"""
    resources = {}
    try:
        # 初始化浏览器管理器配置
        browser_config, session_config = load_configs(
            PlaywrightConfig, USER_DATA_ROOT, BROWSER_EXECUTABLE_PATH
        )
        resources['browser_config'] = browser_config
        resources['session_config'] = session_config

        # 初始化队列
        list_queue = asyncio.Queue()
        detail_queue = asyncio.Queue(maxsize=DETAIL_QUEUE_SIZE)
        resources['list_queue'] = list_queue
        resources['detail_queue'] = detail_queue

        yield resources
    finally:
        # 清理资源
        for name, resource in resources.items():
            try:
                if hasattr(resource, 'close'):
                    if asyncio.iscoroutinefunction(resource.close):
                        await resource.close()
                    else:
                        resource.close()
                elif hasattr(resource, '__aexit__'):
                    # 对于异步上下文管理器，不在这里处理，由调用方处理
                    pass
                logging.info(f"Cleaned up resource: {name}")
            except Exception as e:
                logging.error(f"Error cleaning up resource {name}: {e}")


async def list_producer(queue: asyncio.Queue):
    """生产者：生成列表页采集任务"""
    logging.info("LIST_PRODUCER: Started.")
    total_pages = (TOTAL_RECORDS + RECORDS_PER_PAGE - 1) // RECORDS_PER_PAGE
    tasks_generated = 0
    
    try:
        for page_start in range(0, total_pages, PAGES_PER_LIST_TASK):
            if app_state.is_shutting_down:
                logging.info("LIST_PRODUCER: Shutdown requested, stopping production.")
                break

            offset = page_start * RECORDS_PER_PAGE
            task_info = {"offset": offset, "pages": PAGES_PER_LIST_TASK}
            await queue.put(task_info)
            tasks_generated += 1

            if tasks_generated % 100 == 0:
                logging.info(f"LIST_PRODUCER: Generated {tasks_generated} tasks, queue size: {queue.qsize()}")

        # 发送结束信号
        for _ in range(LIST_CONSUMERS):
            await queue.put(None)

        logging.info(f"LIST_PRODUCER: Finished. Generated {tasks_generated} tasks.")
    except Exception as e:
        logging.error(f"LIST_PRODUCER: Error during production: {e}")
        # 确保发送结束信号
        for _ in range(LIST_CONSUMERS):
            try:
                await queue.put(None)
            except Exception:
                pass
        raise


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
    tasks_processed = 0

    try:
        while not app_state.is_shutting_down:
            try:
                task_info = await list_queue.get()
                if task_info is None:
                    logging.info(f"LIST_CONSUMER_{worker_id}: Received end signal.")
                    break

                if app_state.is_shutting_down:
                    logging.info(f"LIST_CONSUMER_{worker_id}: Shutdown requested, stopping processing.")
                    list_queue.task_done()
                    break

                app_state.tasks_running += 1
                await scrape_list_pages(
                    browser_manager,
                    session_config,
                    session_name=session_name,
                    db_manager=db_manager,
                    detail_task_queue=detail_queue,
                    max_pages=task_info["pages"],
                    offset=task_info["offset"],
                )
                tasks_processed += 1
                app_state.tasks_running -= 1
                performance_monitor.increment_list_pages()

                if tasks_processed % 50 == 0:
                    logging.info(f"LIST_CONSUMER_{worker_id}: Processed {tasks_processed} tasks.")

            except Exception as e:
                app_state.tasks_running -= 1
                performance_monitor.increment_errors()
                logging.error(f"LIST_CONSUMER_{worker_id}: Error processing task: {e}")
                # 继续处理下一个任务
            finally:
                try:
                    list_queue.task_done()
                except Exception:
                    pass

    except Exception as e:
        logging.error(f"LIST_CONSUMER_{worker_id}: Fatal error: {e}")
    finally:
        logging.info(f"LIST_CONSUMER_{worker_id}: Shutting down. Processed {tasks_processed} tasks.")


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
    tasks_processed = 0

    try:
        while not app_state.is_shutting_down:
            try:
                detail_id = await detail_queue.get()
                if detail_id is None:
                    logging.info(f"DETAIL_CONSUMER_{worker_id}: Received end signal.")
                    break

                if app_state.is_shutting_down:
                    logging.info(f"DETAIL_CONSUMER_{worker_id}: Shutdown requested, stopping processing.")
                    detail_queue.task_done()
                    break

                app_state.tasks_running += 1
                await scrape_detail_page(
                    browser_manager,
                    session_config,
                    session_name=session_name,
                    db_manager=db_manager,
                    detail_id=detail_id,
                )
                tasks_processed += 1
                app_state.tasks_running -= 1
                performance_monitor.increment_detail_pages()

                if tasks_processed % 100 == 0:
                    logging.info(f"DETAIL_CONSUMER_{worker_id}: Processed {tasks_processed} tasks.")

            except Exception as e:
                app_state.tasks_running -= 1
                performance_monitor.increment_errors()
                logging.error(f"DETAIL_CONSUMER_{worker_id}: Error processing detail_id {detail_id}: {e}")
                # 继续处理下一个任务
            finally:
                try:
                    detail_queue.task_done()
                except Exception:
                    pass

    except Exception as e:
        logging.error(f"DETAIL_CONSUMER_{worker_id}: Fatal error: {e}")
    finally:
        logging.info(f"DETAIL_CONSUMER_{worker_id}: Shutting down. Processed {tasks_processed} tasks.")


async def main():
    """项目主函数"""
    setup_logging()

    # 检查浏览器路径
    if not BROWSER_EXECUTABLE_PATH:
        await check_and_install_browser()
    elif not validate_browser_path(BROWSER_EXECUTABLE_PATH):
        sys.exit(1)

    # 使用资源管理器
    async with managed_resources() as resources:
        # 使用示例项目的数据库配置
        db_manager = DatabaseManager(EXAMPLE_DATABASE_CONFIG)
        await db_manager.initialize()

        browser_config = resources['browser_config']
        session_config = resources['session_config']
        list_queue = resources['list_queue']
        detail_queue = resources['detail_queue']

                # 启动浏览器上下文
        async with PlaywrightBrowser(browser_config) as browser_manager:
            try:
                # 1. 启动列表页生产者和消费者
                list_producer_task = asyncio.create_task(list_producer(list_queue))
                list_consumer_tasks = [
                asyncio.create_task(
                        list_consumer(i + 1, list_queue, detail_queue, browser_manager, session_config, db_manager)
                    ) for i in range(concurrency_controller.list_consumers)
            ]

                # 2. 启动详情页消费者
                detail_consumer_tasks = [
                    asyncio.create_task(
                        detail_consumer(i + 1, detail_queue, browser_manager, session_config, db_manager)
                    ) for i in range(concurrency_controller.detail_consumers)
                ]

                # 3. 启动并发控制监控任务
                async def monitor_and_adjust():
                    """定期监控性能并调整并发数"""
                    while not app_state.is_shutting_down:
                        await asyncio.sleep(60)  # 每分钟调整一次
                        stats = performance_monitor.get_stats()
                        if stats['total_pages'] > 100:  # 至少处理了100页才有意义
                            new_list_consumers, new_detail_consumers = concurrency_controller.adjust_concurrency(stats)
                            if (new_list_consumers != concurrency_controller.list_consumers or
                                new_detail_consumers != concurrency_controller.detail_consumers):
                                logging.info(f"Concurrency adjusted to: {new_list_consumers} list, {new_detail_consumers} detail")

                monitor_task = asyncio.create_task(monitor_and_adjust())

                # 3. 等待列表页任务完成
                await list_producer_task
                await list_queue.join()
                await asyncio.gather(*list_consumer_tasks)

                # 4. 列表页任务完成后，向详情页队列发送结束信号
                for _ in range(concurrency_controller.detail_consumers):
                    await detail_queue.put(None)

                # 5. 等待详情页任务完成
                await detail_queue.join()
                await asyncio.gather(*detail_consumer_tasks)

                logging.info("All tasks completed successfully.")
                performance_monitor.log_stats()

            except KeyboardInterrupt:
                logging.info("Keyboard interrupt received, initiating graceful shutdown...")
                app_state.is_shutting_down = True
                # 等待正在运行的任务完成
                await asyncio.sleep(5)
                performance_monitor.log_stats()
                logging.info("Shutdown complete.")

            except Exception as e:
                logging.error(f"Fatal error in main execution: {e}")
                app_state.is_shutting_down = True
                performance_monitor.log_stats()
                raise

    logging.info("Application shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())