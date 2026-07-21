import hashlib
import os
import sqlite3
import time
import uuid
from pathlib import Path


class ScreenshotStore:
    def __init__(self, database_path, screenshot_dir):
        self.database_path = Path(database_path)
        self.screenshot_dir = Path(screenshot_dir)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS screenshots (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL UNIQUE,
                    created_at INTEGER NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    viewed INTEGER NOT NULL DEFAULT 0,
                    upload_key TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS screenshots_created_at_idx
                ON screenshots(created_at DESC)
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(screenshots)")
            }
            if "viewed" not in columns:
                connection.execute(
                    "ALTER TABLE screenshots ADD COLUMN viewed INTEGER NOT NULL DEFAULT 0"
                )
            if "upload_key" not in columns:
                connection.execute(
                    "ALTER TABLE screenshots ADD COLUMN upload_key TEXT"
                )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS screenshots_upload_key_idx
                ON screenshots(upload_key)
                WHERE upload_key IS NOT NULL
                """
            )

    @staticmethod
    def detect_image(image_data):
        if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png", "image/png"
        if image_data.startswith(b"\xff\xd8\xff"):
            return ".jpg", "image/jpeg"
        if image_data.startswith((b"GIF87a", b"GIF89a")):
            return ".gif", "image/gif"
        if image_data.startswith(b"RIFF") and image_data[8:12] == b"WEBP":
            return ".webp", "image/webp"
        raise ValueError("unsupported_image")

    def save(self, image_data, upload_id=None):
        extension, content_type = self.detect_image(image_data)
        upload_key = None
        if upload_id:
            upload_key = hashlib.sha256(
                str(upload_id).encode("utf-8", errors="replace")
            ).hexdigest()
            with self._connect() as connection:
                existing = connection.execute(
                    "SELECT * FROM screenshots WHERE upload_key = ?",
                    (upload_key,),
                ).fetchone()
            if existing:
                return dict(existing), False

        screenshot_id = uuid.uuid4().hex
        filename = f"{int(time.time())}-{screenshot_id}{extension}"
        final_path = self.screenshot_dir / filename
        temporary_path = self.screenshot_dir / f".{filename}.tmp"

        with open(temporary_path, "xb") as output:
            output.write(image_data)
            output.flush()
            os.fsync(output.fileno())

        os.replace(temporary_path, final_path)

        record = {
            "id": screenshot_id,
            "filename": filename,
            "created_at": int(time.time()),
            "size_bytes": len(image_data),
            "sha256": hashlib.sha256(image_data).hexdigest(),
            "content_type": content_type,
        }

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO screenshots (
                        id, filename, created_at, size_bytes, sha256,
                        content_type, upload_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["id"],
                        record["filename"],
                        record["created_at"],
                        record["size_bytes"],
                        record["sha256"],
                        record["content_type"],
                        upload_key,
                    ),
                )
        except Exception:
            final_path.unlink(missing_ok=True)
            raise

        record["viewed"] = 0
        record["upload_key"] = upload_key
        return record, True

    def get(self, screenshot_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM screenshots WHERE id = ?",
                (screenshot_id,),
            ).fetchone()
        return dict(row) if row else None

    def list(self, page=1, per_page=24):
        page = max(int(page), 1)
        per_page = min(max(int(per_page), 1), 100)
        with self._connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM screenshots"
            ).fetchone()[0]
            rows = connection.execute(
                """
                SELECT * FROM screenshots
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (per_page, (page - 1) * per_page),
            ).fetchall()

        return [dict(row) for row in rows], total

    def stats(self):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS count,
                    COALESCE(SUM(size_bytes), 0) AS size_bytes,
                    COALESCE(SUM(CASE WHEN viewed = 0 THEN 1 ELSE 0 END), 0) AS unviewed,
                    MIN(created_at) AS oldest_at,
                    MAX(created_at) AS newest_at
                FROM screenshots
                """
            ).fetchone()
        return dict(row)

    def mark_viewed(self, screenshot_id):
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE screenshots SET viewed = 1 WHERE id = ?",
                (screenshot_id,),
            )
        return cursor.rowcount > 0

    def delete(self, screenshot_id):
        record = self.get(screenshot_id)
        if not record:
            return False

        with self._connect() as connection:
            connection.execute(
                "DELETE FROM screenshots WHERE id = ?",
                (screenshot_id,),
            )

        (self.screenshot_dir / record["filename"]).unlink(missing_ok=True)
        return True

    def delete_many(self, screenshot_ids):
        deleted = 0
        for screenshot_id in dict.fromkeys(screenshot_ids):
            deleted += int(self.delete(screenshot_id))
        return deleted

    def clear(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT filename FROM screenshots"
            ).fetchall()
            connection.execute("DELETE FROM screenshots")

        for row in rows:
            (self.screenshot_dir / row["filename"]).unlink(missing_ok=True)
        return len(rows)

    def delete_older_than(self, cutoff_timestamp):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id FROM screenshots WHERE created_at < ?",
                (int(cutoff_timestamp),),
            ).fetchall()

        return self.delete_many([row["id"] for row in rows])
