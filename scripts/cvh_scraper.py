# scripts/cvh_scraper.py
import asyncio
import logging
from typing import List, Dict, Any

from playwright.async_api import Page

from core.browser import PlaywrightBrowser, SessionConfig
from utils.database import DatabaseManager


async def parse_detail_page(page: Page) -> Dict[str, Any]:
    """解析详情页的标本数据"""
    detail_data = {}
    
    async def get_text(selector: str):
        element = await page.query_selector(selector)
        return await element.inner_text() if element else ""

    # 获取主图 URL
    img_element = await page.query_selector("#spm_image")
    detail_data["detail_image_url"] = await img_element.get_attribute("src") if img_element else ""

    detail_data["sci_name"] = await get_text("#formattedName")
    detail_data["chinese_name"] = await get_text("#chineseName")
    detail_data["identified_by"] = await get_text("#identifiedBy")
    detail_data["date_identified"] = await get_text("#dateIdentified")
    detail_data["recorded_by"] = await get_text("#recordedBy")
    detail_data["record_number"] = await get_text("#recordNumber")
    detail_data["verbatim_event_date"] = await get_text("#verbatimEventDate")
    detail_data["locality"] = await get_text("#locality")
    detail_data["elevation"] = await get_text("#elevation")
    detail_data["habitat"] = await get_text("#habitat")
    detail_data["occurrence_remarks"] = await get_text("#occurrenceRemarks")
    detail_data["reproductive_condition"] = await get_text("#reproductiveCondition")
    
    return detail_data


async def parse_list_page(page: Page) -> List[Dict[str, Any]]:
    """解析列表页面的所有标本数据"""
    results = []
    rows = await page.query_selector_all("tbody#spms_list tr.spms-row")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) < 6:
            continue
        
        # 从第一个单元格 (cells[0]) 获取图片
        img_element = await cells[0].query_selector("img")
        img_src = await img_element.get_attribute("src") if img_element else ""

        # 获取行元素的 data-collection-id 属性
        detail_id = await row.get_attribute("data-collection-id")

        if not detail_id:
            continue

        # 按索引从每个单元格获取文本
        data = {
            "detail_id": detail_id,
            "image_url": img_src,
            "barcode": await cells[1].inner_text(),
            "name": await cells[2].inner_text(),
            "collector": await cells[3].inner_text(),
            "location": await cells[4].inner_text(),
            "year": await cells[5].inner_text(),
        }
        results.append(data)
    return results



async def scrape_list_pages(
    browser_manager: PlaywrightBrowser,
    session_config: SessionConfig,
    session_name: str,
    db_manager: DatabaseManager,
    detail_task_queue: asyncio.Queue,
    max_pages: int,
    offset: int,
):
    """采集列表页，将基础数据存入数据库，并将 detail_id 放入详情页任务队列。"""
    logging.info(f"LIST_SCRAPER ({session_name}): Starting chunk, offset={offset}, pages={max_pages}")
    
    session_manager = browser_manager.create_session(session_name, session_config)
    async with session_manager as session:
        page = await session.new_page()
        try:
            base_url = "https://www.cvh.ac.cn/spms/list.php"
            records_per_page = 30

            for page_num in range(max_pages):
                current_offset = offset + (page_num * records_per_page)
                url = f"{base_url}?&offset={current_offset}"
                
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_selector("tbody#spms_list tr.spms-row", state="attached", timeout=30000)

                list_records = await parse_list_page(page)
                if not list_records:
                    logging.warning(f"LIST_SCRAPER ({session_name}): No data found at offset {current_offset}.")
                    break

                for record in list_records:
                    await db_manager.save_list_data(record)
                    await detail_task_queue.put(record["detail_id"])
                
                logging.info(f"LIST_SCRAPER ({session_name}): Saved and queued {len(list_records)} records from offset {current_offset}.")

        except Exception as e:
            logging.error(f"LIST_SCRAPER ({session_name}): Error at offset {offset}: {e}", exc_info=True)
        finally:
            await page.close()


async def scrape_detail_page(
    browser_manager: PlaywrightBrowser,
    session_config: SessionConfig,
    session_name: str,
    db_manager: DatabaseManager,
    detail_id: str,
):
    """接收一个 detail_id，采集其详情页数据并存入数据库。"""
    logging.debug(f"DETAIL_SCRAPER ({session_name}): Processing id: {detail_id}")
    
    session_manager = browser_manager.create_session(session_name, session_config, clear_state=True) # 使用无状态会话
    async with session_manager as session:
        page = await session.new_page()
        try:
            detail_url = f"https://www.cvh.ac.cn/spms/detail.php?id={detail_id}"
            await page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)
            
            detail_info = await parse_detail_page(page)
            detail_info["detail_id"] = detail_id
            
            await db_manager.save_detail_data(detail_info)
            logging.info(f"DETAIL_SCRAPER ({session_name}): Successfully saved detail for id: {detail_id}")

        except Exception as e:
            logging.error(f"DETAIL_SCRAPER ({session_name}): Failed to process id {detail_id}: {e}")
            # 在实际生产中，这里可以加入重试逻辑，例如将失败的 id 重新放入队列
        finally:
            await page.close()
