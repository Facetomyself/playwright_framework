# core/browser.py
import asyncio
import json
import logging
import portalocker
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
    browser_args: List[str] = field(default_factory=list)
    fingerprint_profile_path: Optional[Path] = None

    def get_storage_state_path(self, session_name: str) -> Path:
        """根据会话名生成持久化文件路径"""
        return self.user_data_root / f"{session_name}_state.json"


async def _save_fingerprint_non_blocking(fingerprint_record: Dict[str, Any]):
    """在后台线程中异步追加指纹记录，使用文件锁避免并发写入问题"""
    loop = asyncio.get_running_loop()

    def locked_write():
        try:
            with portalocker.Lock(FINGERPRINT_DB_PATH, "a", encoding="utf-8", timeout=5) as f:
                f.write(json.dumps(fingerprint_record, ensure_ascii=False) + "\n")
            logging.info(f"Fingerprint for session '{fingerprint_record.get('session_name')}' saved in background.")
        except portalocker.LockException as e:
            logging.error(f"Could not acquire lock for fingerprint db: {e}")
        except Exception as e:
            logging.error(f"Background fingerprint save failed: {e}")

    try:
        await loop.run_in_executor(None, locked_write)
    except Exception as e:
        logging.error(f"Failed to execute non-blocking save: {e}")


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
        clear_state: bool = False,
    ):
        self.browser = browser
        self.session_name = session_name
        self.config = config
        self.context: Optional[BrowserContext] = None
        self.storage_path = self.config.get_storage_state_path(self.session_name)
        self.logger = logging.getLogger(f"Session[{self.session_name}]")
        self.fingerprint_data: Optional[Dict[str, Any]] = None

        if clear_state and self.storage_path.exists():
            self.storage_path.unlink()
            self.logger.info("Cleared persistent state file: %s", self.storage_path)

    async def __aenter__(self) -> "BrowserSession":
        """进入上下文，创建并初始化 BrowserContext，并采集或应用指纹"""
        self.logger.info("Initializing browser context...")

        launch_kwargs: Dict[str, Any] = {
            "viewport": self.config.viewport,
            "user_agent": self.config.user_agent,
            "proxy": self.config.proxy,
        }

        # --- 指纹应用 ---
        fingerprint_to_apply = None
        if self.config.fingerprint_profile_path and self.config.fingerprint_profile_path.exists():
            try:
                with self.config.fingerprint_profile_path.open("r", encoding="utf-8") as f:
                    fingerprint_to_apply = json.load(f)
                
                # 优先使用指纹文件中的 UA
                if "user_agent" in fingerprint_to_apply.get("fingerprint", {}):
                    launch_kwargs["user_agent"] = fingerprint_to_apply["fingerprint"]["user_agent"]
                    self.logger.info("-> Applying User-Agent from fingerprint profile.")

            except Exception as e:
                self.logger.error(f"Failed to load fingerprint profile: {e}")
                fingerprint_to_apply = None

        if self.storage_path.exists():
            launch_kwargs["storage_state"] = self.storage_path
            self.logger.info("-> Loading state from: %s", self.storage_path)

        self.context = await self.browser.new_context(**launch_kwargs)

        # --- 注入初始化脚本 ---
        # 1. 注入 stealth.min.js (如果配置了)
        if self.config.init_script_path and self.config.init_script_path.exists():
            await self.context.add_init_script(path=self.config.init_script_path)
            self.logger.info("-> Injected stealth script from: %s", self.config.init_script_path)

        # 2. 如果有指纹配置，生成并注入伪造脚本
        if fingerprint_to_apply:
            try:
                fp_data = fingerprint_to_apply["fingerprint"]
                # 移除 UA，因为它已经通过 launch_kwargs 设置了
                fp_data.pop("user_agent", None)
                
                # 生成伪造脚本
                override_script = "(() => {\n"
                for key, value in fp_data.items():
                    # 简单的 JS 类型转换
                    js_value = json.dumps(value)
                    override_script += f"  Object.defineProperty(navigator, '{key}', {{ get: () => {js_value} }});\n"
                override_script += "})();"
                
                await self.context.add_init_script(script=override_script)
                self.logger.info("-> Injected fingerprint override script.")
            except Exception as e:
                self.logger.error(f"Failed to generate or inject fingerprint script: {e}")

        # --- 指纹采集 (仅在未应用指纹时进行) ---
        if not fingerprint_to_apply and SAVE_FINGERPRINT:
            fp_page = await self.context.new_page()
            try:
                fp_script_path = Path(__file__).parent / "init_scripts" / "get_fingerprint.js"
                if fp_script_path.exists():
                    fp_script = fp_script_path.read_text(encoding="utf-8")
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
                    "storage_state_path": str(self.storage_path),
                    "config": {
                        "user_agent": self.config.user_agent,
                        "browser_args": self.config.browser_args,
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
            clear_state=clear_state,
        )