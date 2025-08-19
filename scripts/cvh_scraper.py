# scripts/cvh_scraper.py
import asyncio
import logging
import re
from typing import List, Dict, Any
import csv
import functools

from playwright.async_api import Page

from core.browser import PlaywrightBrowser, SessionConfig


async def parse_current_page(page: Page) -> List[Dict[str, Any]]:
    """解析当前页面的所有标本数据"""
    results = []
    rows = await page.query_selector_all("tbody#spms_list tr.spms-row")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) < 6:
            continue
        
        # 从第一个单元格 (cells[0]) 获取图片
        img_element = await cells[0].query_selector("img")
        img_src = await img_element.get_attribute("src") if img_element else ""

        # 按索引从每个单元格获取文本
        data = {
            "image_url": img_src,
            "barcode": await cells[1].inner_text(),
            "name": await cells[2].inner_text(),
            "collector": await cells[3].inner_text(),
            "location": await cells[4].inner_text(),
            "year": await cells[5].inner_text(),
        }
        results.append(data)
    return results



async def scrape_cvh_data(
    browser_manager: PlaywrightBrowser,
    session_config: SessionConfig,
    session_name: str,
    max_pages: int = 5,  # 限制最大采集页数，以防采太多
):
    """
    采集中国数字植物标本馆的标本数据。

    :param browser_manager: 已初始化的 PlaywrightBrowser 实例。
    :param session_config: 通用的会话配置。
    :param session_name: 本次任务要使用的会话名称。
    :param max_pages: 本次运行最多采集的页数。
    """
    logging.info(f"Starting CVH data scraping task for session: {session_name}")
    
    output_filename = f"cvh_specimen_data_{session_name}.csv"
    fieldnames = ["image_url", "barcode", "name", "collector", "location", "year"]
    
    loop = asyncio.get_running_loop()

    # 使用 run_in_executor 将同步的文件写入操作异步化
    def sync_write_header():
        with open(output_filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
    
    await loop.run_in_executor(None, sync_write_header)

    total_records = 0
    session_manager = browser_manager.create_session(session_name, session_config)

    async with session_manager as session:
        page = await session.new_page()
        try:
            url = "https://www.cvh.ac.cn/spms/list.php"
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_selector("tbody#spms_list", state="attached", timeout=60000)

            for page_num in range(1, max_pages + 1):
                logging.info(f"Scraping page {page_num}...")
                
                await page.wait_for_selector("tbody#spms_list tr.spms-row", state="attached", timeout=30000)
                
                records = await parse_current_page(page)
                if not records:
                    logging.warning(f"No data found on page {page_num}. Exiting.")
                    break
                
                # 将追加写入的操作也异步化
                def sync_append_rows():
                    with open(output_filename, "a", newline="", encoding="utf-8-sig") as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writerows(records)
                
                await loop.run_in_executor(None, sync_append_rows)
                
                total_records += len(records)
                logging.info(f"Saved {len(records)} records from page {page_num}. Total saved: {total_records}")

                jump_input = await page.query_selector("#jump_to")
                if not jump_input:
                    logging.error("Could not find page jump input. Exiting.")
                    break
                
                placeholder = await jump_input.get_attribute("placeholder")
                if not placeholder:
                    logging.error("Could not get placeholder from jump input. Exiting.")
                    break

                match = re.search(r'第(\d+)/(\d+)页', placeholder)
                if not match:
                    logging.error(f"Could not parse page numbers from placeholder: '{placeholder}'. Exiting.")
                    break
                
                current_page, total_pages = map(int, match.groups())
                
                if current_page >= total_pages or page_num >= max_pages:
                    logging.info("Reached the last page or max_pages limit. Finishing.")
                    break

                next_button = await page.query_selector("#next_page")
                if next_button and await next_button.is_enabled():
                    await next_button.click()
                    await page.wait_for_selector("tbody#spms_list tr.spms-row", state="attached", timeout=30000)
                else:
                    logging.warning("Next page button not found or disabled. Exiting.")
                    break

        except Exception as e:
            logging.error(f"An error occurred during scraping: {e}", exc_info=True)
        finally:
            await page.close()
            logging.info(f"Scraping task finished. Total records saved to '{output_filename}': {total_records}")
