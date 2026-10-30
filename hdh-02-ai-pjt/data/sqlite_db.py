import sqlite3
from typing import Any

from config import SQLITE_DB_PATH
from contracts import StatisticalResult


class DatabaseManager:
    def __init__(self, db_path: str = SQLITE_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 기술 기본 테이블
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS technology (
                technology_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                source_ref TEXT NOT NULL
            );
            """)
            # 통계 관측치 테이블
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS observation (
                observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                technology_id TEXT NOT NULL,
                category TEXT NOT NULL,
                year INTEGER NOT NULL,
                population_id TEXT NOT NULL,
                usage_pct REAL,
                desired_pct REAL,
                admired_pct REAL,
                question_n INTEGER,
                source_locator TEXT,
                UNIQUE(technology_id, year, population_id),
                FOREIGN KEY (technology_id) REFERENCES technology(technology_id)
            );
            """)
            conn.commit()

    def get_technology(self, tech_id: str) -> dict[str, Any] | None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM technology WHERE technology_id = ?", (tech_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_statistics(
        self, tech_id: str, year: int = 2026
    ) -> StatisticalResult | None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT t.technology_id, t.canonical_name, t.category,
                       o.year, o.population_id, o.usage_pct, o.desired_pct, o.admired_pct,
                       o.question_n, o.source_locator
                FROM technology t
                JOIN observation o ON t.technology_id = o.technology_id
                WHERE t.technology_id = ? AND o.year = ?
            """,
                (tech_id, year),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return StatisticalResult(
                result_id=f"stat_{row['technology_id']}_{year}",
                technology_id=row["technology_id"],
                technology_name=row["canonical_name"],
                category=row["category"],
                year=row["year"],
                population=row["population_id"],
                usage_pct=row["usage_pct"],
                desired_pct=row["desired_pct"],
                admired_pct=row["admired_pct"],
                question_n=row["question_n"],
                source_locator=row["source_locator"],
            )

    def filter_technologies(
        self,
        min_usage: float | None = None,
        min_admired: float | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """자연어 조건 탐색용 결정적 쿼리"""
        query = """
            SELECT t.technology_id, t.canonical_name, t.category, o.usage_pct, o.desired_pct, o.admired_pct
            FROM technology t
            JOIN observation o ON t.technology_id = o.technology_id
            WHERE o.year = 2026
        """
        params = []
        if min_usage is not None:
            query += " AND o.usage_pct >= ?"
            params.append(min_usage)
        if min_admired is not None:
            query += " AND o.admired_pct >= ?"
            params.append(min_admired)
        if category is not None:
            query += " AND t.category = ?"
            params.append(category)

        query += " ORDER BY o.usage_pct DESC"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]
