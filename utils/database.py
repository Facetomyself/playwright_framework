# utils/database.py
import logging
import aiomysql


class DatabaseManager:
    """异步管理 MySQL 数据库连接和操作"""

    def __init__(self, config: dict):
        self.config = config
        self.pool = None

    async def initialize(self):
        """初始化数据库：创建数据库、连接池和表"""
        try:
            # 1. 连接到 MySQL 服务器 (不指定数据库)
            conn = await aiomysql.connect(
                host=self.config["host"],
                port=self.config["port"],
                user=self.config["user"],
                password=self.config["password"],
                autocommit=True,  # DDL 语句需要自动提交
            )
            async with conn.cursor() as cursor:
                # 2. 创建数据库 (如果不存在)
                db_name = self.config["db"]
                await cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                logging.info(f"Database '{db_name}' ensured to exist.")
            conn.close()

            # 3. 创建连接池
            self.pool = await aiomysql.create_pool(
                host=self.config["host"],
                port=self.config["port"],
                user=self.config["user"],
                password=self.config["password"],
                db=self.config["db"],
                autocommit=True,
            )
            logging.info("Database connection pool created.")

            # 4. 创建表
            await self._create_tables()

        except Exception as e:
            logging.error(f"Failed to initialize database: {e}")
            raise

    async def _create_tables(self):
        """检查并创建所需的表"""
        if not self.pool:
            raise ConnectionError("Database pool is not initialized. Call initialize() first.")
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # 创建列表数据表
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS specimen_list (
                        detail_id VARCHAR(255) PRIMARY KEY,
                        image_url TEXT,
                        barcode VARCHAR(255),
                        name VARCHAR(255),
                        collector VARCHAR(255),
                        location TEXT,
                        year VARCHAR(50),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB;
                """)
                logging.info("Table 'specimen_list' ensured to exist.")

                # 创建详情数据表
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS specimen_details (
                        detail_id VARCHAR(255) PRIMARY KEY,
                        detail_image_url TEXT,
                        sci_name TEXT,
                        chinese_name VARCHAR(255),
                        identified_by VARCHAR(255),
                        date_identified VARCHAR(50),
                        recorded_by VARCHAR(255),
                        record_number VARCHAR(255),
                        verbatim_event_date VARCHAR(50),
                        locality TEXT,
                        elevation VARCHAR(50),
                        habitat TEXT,
                        occurrence_remarks TEXT,
                        reproductive_condition VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (detail_id) REFERENCES specimen_list(detail_id) ON DELETE CASCADE
                    ) ENGINE=InnoDB;
                """)
                logging.info("Table 'specimen_details' ensured to exist.")

    async def save_list_data(self, data: dict):
        """将单条列表数据保存到数据库，忽略重复"""
        if not self.pool:
            raise ConnectionError("Database pool is not initialized.")
        sql = """
            INSERT IGNORE INTO specimen_list
            (detail_id, image_url, barcode, name, collector, location, year)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(sql, (
                    data.get("detail_id"),
                    data.get("image_url"),
                    data.get("barcode"),
                    data.get("name"),
                    data.get("collector"),
                    data.get("location"),
                    data.get("year"),
                ))

    async def save_detail_data(self, data: dict):
        """将单条详情数据保存到数据库，忽略重复"""
        if not self.pool:
            raise ConnectionError("Database pool is not initialized.")
        sql = """
            INSERT IGNORE INTO specimen_details
            (detail_id, detail_image_url, sci_name, chinese_name, identified_by,
            date_identified, recorded_by, record_number, verbatim_event_date,
            locality, elevation, habitat, occurrence_remarks, reproductive_condition)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(sql, (
                    data.get("detail_id"),
                    data.get("detail_image_url"),
                    data.get("sci_name"),
                    data.get("chinese_name"),
                    data.get("identified_by"),
                    data.get("date_identified"),
                    data.get("recorded_by"),
                    data.get("record_number"),
                    data.get("verbatim_event_date"),
                    data.get("locality"),
                    data.get("elevation"),
                    data.get("habitat"),
                    data.get("occurrence_remarks"),
                    data.get("reproductive_condition"),
                ))

    async def save_data_transactional(self, list_data: dict, detail_data: dict = None):
        """事务性保存数据：列表数据和详情数据要么都保存，要么都不保存"""
        if not self.pool:
            raise ConnectionError("Database pool is not initialized.")

        async with self.pool.acquire() as conn:
            try:
                # 开始事务
                await conn.begin()

                # 1. 保存列表数据
                list_sql = """
                    INSERT IGNORE INTO specimen_list
                    (detail_id, image_url, barcode, name, collector, location, year)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                async with conn.cursor() as cursor:
                    await cursor.execute(list_sql, (
                        list_data.get("detail_id"),
                        list_data.get("image_url"),
                        list_data.get("barcode"),
                        list_data.get("name"),
                        list_data.get("collector"),
                        list_data.get("location"),
                        list_data.get("year"),
                    ))

                # 2. 如果有详情数据，一并保存
                if detail_data:
                    detail_sql = """
                        INSERT IGNORE INTO specimen_details
                        (detail_id, detail_image_url, sci_name, chinese_name, identified_by,
                        date_identified, recorded_by, record_number, verbatim_event_date,
                        locality, elevation, habitat, occurrence_remarks, reproductive_condition)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    async with conn.cursor() as cursor:
                        await cursor.execute(detail_sql, (
                            detail_data.get("detail_id"),
                            detail_data.get("detail_image_url"),
                            detail_data.get("sci_name"),
                            detail_data.get("chinese_name"),
                            detail_data.get("identified_by"),
                            detail_data.get("date_identified"),
                            detail_data.get("recorded_by"),
                            detail_data.get("record_number"),
                            detail_data.get("verbatim_event_date"),
                            detail_data.get("locality"),
                            detail_data.get("elevation"),
                            detail_data.get("habitat"),
                            detail_data.get("occurrence_remarks"),
                            detail_data.get("reproductive_condition"),
                        ))

                # 提交事务
                await conn.commit()
                return True

            except Exception as e:
                # 回滚事务
                await conn.rollback()
                logging.error(f"Transaction failed, rolled back: {e}")
                raise e

    async def save_list_data_batch(self, data_list: list):
        """批量保存列表数据，提高性能"""
        if not self.pool or not data_list:
            return

        sql = """
            INSERT IGNORE INTO specimen_list
            (detail_id, image_url, barcode, name, collector, location, year)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # 批量插入
                values = [(
                    data.get("detail_id"),
                    data.get("image_url"),
                    data.get("barcode"),
                    data.get("name"),
                    data.get("collector"),
                    data.get("location"),
                    data.get("year"),
                ) for data in data_list]

                await cursor.executemany(sql, values)

    async def close(self):
        """关闭数据库连接池"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logging.info("Database connection pool closed.")