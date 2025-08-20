# config/logging_config.py
import logging
import logging.handlers
import os
from pathlib import Path

def setup_logging():
    """初始化日志配置"""
    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # 基础配置
    log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper())

    # 根日志配置
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            # 控制台输出
            logging.StreamHandler(),
            # 文件输出 - 按日期分割
            logging.handlers.TimedRotatingFileHandler(
                log_dir / "cvh_scraper.log",
                when="midnight",
                interval=1,
                backupCount=30,
                encoding="utf-8"
            )
        ]
    )

    # 设置第三方库的日志级别
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # 创建特定模块的日志记录器
    logger = logging.getLogger("CVH_SCRAPER")
    logger.info("Logging system initialized")