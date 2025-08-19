# core/browser.py
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from playwright.async_api import (
    async_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
    ProxySettings,
)

from config.default import SAVE_FINGERPRINT, FINGERPRINT_DB_PATH


@dataclass
class BrowserConfig:
    """全局浏览器启动配置"""
    headless: bool = True
    executable_path: Optional[str] = None
    channel: Optional[str] = None
    slow_mo: float = 0
    args: List[str] = field(default_factory=list)


@dataclass
class SessionConfig:
    """浏览器会话配置"""
    user_data_root: Path
    proxy: Optional[ProxySettings] = None
    user_agent: Optional[str] = None
    viewport: Dict[str, int] = field(default_factory=lambda: {"width": 1920, "height": 1080})
    init_script_path: Optional[Path] = None

    def get_storage_state_path(self, session_name: str) -> Path:
        """根据会话名生成持久化文件路径"""
        return self.user_data_root / f"{session_name}_state.json"


async def _save_fingerprint_non_blocking(fingerprint_record: Dict[str, Any]):
    """在后台线程中异步追加指纹记录，避免阻塞主事件循环"""
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None,  # 使用默认的线程池执行器
            lambda: FINGERPRINT_DB_PATH.open("a", encoding="utf-8").write(
                json.dumps(fingerprint_record, ensure_ascii=False) + "\n"
            )
        )
        logging.info(f"Fingerprint for session '{fingerprint_record.get('session_name')}' saved in background.")
    except Exception as e:
        logging.error(f"Background fingerprint save failed: {e}")


class BrowserSession:
    """
    浏览器会话管理器。
    作为异步上下文管理器，负责 BrowserContext 的创建、状态持久化和资源释放。
    """
    def __init__(
        self,
        browser: Browser,
        session_name: str,
        config: SessionConfig,
        browser_args: List[str],
        clear_state: bool = False,
    ):
        self.browser = browser
        self.session_name = session_name
        self.config = config
        self.browser_args = browser_args
        self.context: Optional[BrowserContext] = None
        self.storage_path = self.config.get_storage_state_path(self.session_name)
        self.logger = logging.getLogger(f"Session[{self.session_name}]")
        self.fingerprint_data: Optional[Dict[str, Any]] = None

        if clear_state and self.storage_path.exists():
            self.storage_path.unlink()
            self.logger.info("Cleared persistent state file: %s", self.storage_path)

    async def __aenter__(self) -> "BrowserSession":
        """进入上下文，创建并初始化 BrowserContext，并采集指纹"""
        self.logger.info("Initializing browser context...")
        
        launch_kwargs: Dict[str, Any] = {
            "viewport": self.config.viewport,
            "user_agent": self.config.user_agent,
            "proxy": self.config.proxy,
        }
        if self.storage_path.exists():
            launch_kwargs["storage_state"] = self.storage_path
            self.logger.info("-> Loading state from: %s", self.storage_path)
        
        if self.config.init_script_path and self.config.init_script_path.exists():
             self.logger.info("-> Preparing init script from: %s", self.config.init_script_path)

        self.context = await self.browser.new_context(**launch_kwargs)

        if self.config.init_script_path and self.config.init_script_path.exists():
            await self.context.add_init_script(path=self.config.init_script_path)

        # --- 指纹采集 ---
        # 为了确保指纹采集过程不污染业务逻辑页面，我们在这里创建一个临时的、
        # 一次性的页面来执行采集脚本，采集完毕后立即关闭。
        if SAVE_FINGERPRINT:
            fp_page = await self.context.new_page()
            try:
                # 读取并执行指纹采集脚本
                fp_script_path = Path(__file__).parent / "init_scripts" / "get_fingerprint.js"
                if fp_script_path.exists():
                    fp_script = fp_script_path.read_text(encoding="utf-8")
                    # 在 about:blank 页面执行脚本以获取环境指纹
                    await fp_page.goto("about:blank")
                    fingerprint_json = await fp_page.evaluate(f"({fp_script})()")
                    self.fingerprint_data = json.loads(fingerprint_json)
                    self.logger.info("Browser fingerprint collected.")
                else:
                    self.logger.warning("Fingerprint script not found at: %s", fp_script_path)
            except Exception as e:
                self.logger.error(f"Failed to collect fingerprint: {e}")
            finally:
                await fp_page.close()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，保存状态并关闭 BrowserContext"""
        if self.context:
            # 1. 保存会话状态 (Cookies, LocalStorage)
            try:
                await self.context.storage_state(path=self.storage_path)
                self.logger.info("Storage state saved to: %s", self.storage_path)
            except Exception as e:
                self.logger.error("Failed to save storage state: %s", e)

            # 2. 异步保存指纹/UA信息
            if self.fingerprint_data:
                fingerprint_record = {
                    "timestamp_utc": datetime.utcnow().isoformat(),
                    "session_name": self.session_name,
                    "config": {
                        "user_agent": self.config.user_agent,
                        "browser_args": self.browser_args,
                    },
                    "fingerprint": self.fingerprint_data,
                }
                asyncio.create_task(_save_fingerprint_non_blocking(fingerprint_record))

            await self.context.close()
            self.logger.info("Browser context closed.")
        self.context = None

    async def new_page(self) -> Page:
        """创建一个新页面并返回实例"""
        if not self.context:
            raise RuntimeError("Context is not initialized. Use 'async with BrowserSession(...)'.")
        page = await self.context.new_page()
        return page


class PlaywrightBrowser:
    """
    Playwright 浏览器实例管理器。
    作为顶层异步上下文管理器，负责 Playwright 实例和全局 Browser 的生命周期。
    """
    def __init__(self, config: BrowserConfig):
        self.config = config
        self.pw: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.logger = logging.getLogger("PlaywrightBrowser")

    async def __aenter__(self) -> "PlaywrightBrowser":
        """启动 Playwright 并启动浏览器"""
        self.logger.info("Starting Playwright...")
        self.pw = await async_playwright().start()
        
        launch_options: Dict[str, Any] = {
            "headless": self.config.headless,
            "slow_mo": self.config.slow_mo,
            "args": self.config.args,
        }

        # 动态添加 executable_path 或 channel，确保互斥
        if self.config.executable_path:
            launch_options["executable_path"] = str(self.config.executable_path)
        elif self.config.channel:
            launch_options["channel"] = self.config.channel
        
        self.browser = await self.pw.chromium.launch(**launch_options)
        self.logger.info("Browser launched.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭浏览器和 Playwright"""
        if self.browser:
            await self.browser.close()
            self.logger.info("Browser closed.")
        if self.pw:
            await self.pw.stop()
            self.logger.info("Playwright stopped.")

    def create_session(
        self, session_name: str, config: SessionConfig, clear_state: bool = False
    ) -> BrowserSession:
        """创建一个浏览器会话实例"""
        if not self.browser:
            raise RuntimeError("Browser is not launched. Use 'async with PlaywrightBrowser(...)'.")
        return BrowserSession(
            self.browser,
            session_name,
            config,
            browser_args=self.config.args,
            clear_state=clear_state,
        )