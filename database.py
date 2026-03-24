import os
import shutil
import sqlite3
import random
from typing import List, Tuple, Optional

from config import SUPER_ADMIN_ID


class Database:
    def __init__(self, db_path: str = "/app/data/rolls.db"):
        self.db_path = db_path

        os.makedirs("/app/data", exist_ok=True)

        seed_db = "/app/rolls.db"
        if not os.path.exists(self.db_path) and os.path.exists(seed_db):
            shutil.copy2(seed_db, self.db_path)

        self.init_db()

    def get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self):
        with self.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS moderators (
                    user_id     INTEGER PRIMARY KEY,
                    user_name   TEXT,
                    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT UNIQUE NOT NULL,
                    created_by  INTEGER NOT NULL,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id INTEGER NOT NULL,
                    name        TEXT NOT NULL,
                    chance      REAL NOT NULL,
                    file_id     TEXT,
                    media_type  TEXT,
                    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS roll_history (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       INTEGER NOT NULL,
                    user_name     TEXT NOT NULL,
                    category_id   INTEGER NOT NULL,
                    category_name TEXT NOT NULL,
                    result        TEXT NOT NULL,
                    rolled_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

            # Миграция: добавляем колонки media если их нет (для старых БД)
            for col in ("file_id", "media_type"):
                try:
                    conn.execute(f"ALTER TABLE items ADD COLUMN {col} TEXT")
                    conn.commit()
                except Exception:
                    pass  # колонка уже есть

    # ---------- MODERATORS ----------

    def is_allowed(self, user_id: int) -> bool:
        if user_id == SUPER_ADMIN_ID:
            return True
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM moderators WHERE user_id = ?", (user_id,)
            ).fetchone()
            return row is not None

    def add_moderator(self, user_id: int, user_name: str) -> bool:
        try:
            with self.get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO moderators (user_id, user_name) VALUES (?, ?)",
                    (user_id, user_name),
                )
                conn.commit()
                return True
        except Exception:
            return False

    def remove_moderator(self, user_id: int) -> bool:
        try:
            with self.get_conn() as conn:
                conn.execute("DELETE FROM moderators WHERE user_id = ?", (user_id,))
                conn.commit()
                return True
        except Exception:
            return False

    def get_moderators(self) -> List[Tuple]:
        with self.get_conn() as conn:
            return conn.execute(
                "SELECT user_id, user_name, added_at FROM moderators ORDER BY added_at"
            ).fetchall()

    # ---------- CATEGORIES ----------

    def create_category(self, name: str, user_id: int) -> Optional[int]:
        try:
            with self.get_conn() as conn:
                cursor = conn.execute(
                    "INSERT INTO categories (name, created_by) VALUES (?, ?)",
                    (name, user_id),
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_categories(self) -> List[Tuple]:
        with self.get_conn() as conn:
            return conn.execute(
                "SELECT id, name FROM categories ORDER BY name"
            ).fetchall()

    def get_category(self, category_id: int) -> Optional[Tuple]:
        with self.get_conn() as conn:
            return conn.execute(
                "SELECT id, name FROM categories WHERE id = ?", (category_id,)
            ).fetchone()

    def delete_category(self, category_id: int) -> bool:
        try:
            with self.get_conn() as conn:
                conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
                conn.commit()
                return True
        except Exception:
            return False

    # ---------- ITEMS ----------

    def add_item(self, category_id: int, name: str, chance: float) -> Optional[int]:
        try:
            with self.get_conn() as conn:
                cursor = conn.execute(
                    "INSERT INTO items (category_id, name, chance) VALUES (?, ?, ?)",
                    (category_id, name, chance),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception:
            return None

    def get_items(self, category_id: int) -> List[Tuple]:
        """Возвращает (id, name, chance, file_id, media_type)"""
        with self.get_conn() as conn:
            return conn.execute(
                """SELECT id, name, chance, file_id, media_type
                   FROM items WHERE category_id = ?
                   ORDER BY chance DESC""",
                (category_id,),
            ).fetchall()

    def get_item(self, item_id: int) -> Optional[Tuple]:
        """Возвращает (id, name, chance, file_id, media_type)"""
        with self.get_conn() as conn:
            return conn.execute(
                "SELECT id, name, chance, file_id, media_type FROM items WHERE id = ?",
                (item_id,),
            ).fetchone()

    def update_item_chance(self, item_id: int, new_chance: float) -> bool:
        try:
            with self.get_conn() as conn:
                conn.execute(
                    "UPDATE items SET chance = ? WHERE id = ?",
                    (new_chance, item_id),
                )
                conn.commit()
                return True
        except Exception:
            return False

    def update_item_media(self, item_id: int, file_id: Optional[str], media_type: Optional[str]) -> bool:
        try:
            with self.get_conn() as conn:
                conn.execute(
                    "UPDATE items SET file_id = ?, media_type = ? WHERE id = ?",
                    (file_id, media_type, item_id),
                )
                conn.commit()
                return True
        except Exception:
            return False

    def delete_item(self, item_id: int) -> bool:
        try:
            with self.get_conn() as conn:
                conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
                conn.commit()
                return True
        except Exception:
            return False

    # ---------- ROLL ----------

    def roll(self, category_id: int) -> Optional[Tuple]:
        """Возвращает (name, file_id, media_type) или None"""
        items = self.get_items(category_id)
        if not items:
            return None
        total = sum(item[2] for item in items)
        rand = random.uniform(0, total)
        cumulative = 0.0
        for item_id, name, chance, file_id, media_type in items:
            cumulative += chance
            if rand <= cumulative:
                return (name, file_id, media_type)
        last = items[-1]
        return (last[1], last[3], last[4])

    # ---------- HISTORY ----------

    def save_roll(self, user_id: int, user_name: str, category_id: int, category_name: str, result: str):
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO roll_history (user_id, user_name, category_id, category_name, result)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, user_name, category_id, category_name, result),
            )
            conn.commit()

    def get_history(self, limit: int = 20) -> List[Tuple]:
        with self.get_conn() as conn:
            return conn.execute(
                """SELECT user_name, category_name, result, rolled_at
                   FROM roll_history ORDER BY rolled_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
