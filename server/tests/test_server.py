import io
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash


TEST_DIRECTORY = tempfile.TemporaryDirectory()
SERVER_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIRECTORY))

os.environ.update(
    {
        "DATA_DIR": TEST_DIRECTORY.name,
        "SCREENSHOT_DIR": str(Path(TEST_DIRECTORY.name) / "images"),
        "DATABASE_PATH": str(Path(TEST_DIRECTORY.name) / "screenshots.db"),
        "RELAY_SECRET": "test-relay-secret",
        "ADMIN_PASSWORD_HASH": generate_password_hash("test-admin-password"),
        "FLASK_SECRET_KEY": "test-flask-secret",
        "DISABLE_BACKGROUND_WORKERS": "1",
    }
)

import server as application  # noqa: E402


class TelegramResponse:
    ok = True
    status_code = 200

    @staticmethod
    def json():
        return {"ok": True}


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        application.app.config.update(TESTING=True)
        self.client = application.app.test_client()
        application.store.clear()
        application.store.set_setting("retention_days", 0)
        with application.state_lock:
            application.last_seen = 0.0
            application.last_queue_count = 0
            application.stop_requested = False
            application.stop_pending = False
            application.client_event_id = 0
            application.client_event_kind = ""
            application.client_event_message = ""

    def csrf_from(self, response):
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def login(self):
        response = self.client.get("/login")
        token = self.csrf_from(response)
        response = self.client.post(
            "/login",
            data={"csrf_token": token, "password": "test-admin-password"},
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    @patch.object(application.requests, "post", return_value=TelegramResponse())
    def test_upload_live_state_and_viewed_marker(self, _telegram_post):
        csrf = self.login()
        image = b"\x89PNG\r\n\x1a\n" + b"test-image-data"

        response = self.client.post(
            "/upload",
            headers={
                "X-Relay-Secret": "test-relay-secret",
                "X-Upload-ID": "queue-file-1.png",
            },
            data={"image": (io.BytesIO(image), "screenshot.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        screenshot_id = response.get_json()["screenshot_id"]

        duplicate = self.client.post(
            "/upload",
            headers={
                "X-Relay-Secret": "test-relay-secret",
                "X-Upload-ID": "queue-file-1.png",
            },
            data={"image": (io.BytesIO(image), "screenshot.png")},
            content_type="multipart/form-data",
        )
        self.assertFalse(duplicate.get_json()["new_screenshot"])

        state = self.client.get("/api/gallery-state").get_json()
        self.assertEqual(state["total"], 1)
        self.assertEqual(state["unviewed"], 1)
        self.assertTrue(state["screenshot_capacity_label"])
        self.assertFalse(state["screenshots"][0]["viewed"])

        viewed = self.client.post(
            f"/screenshots/{screenshot_id}/viewed",
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(viewed.status_code, 200)
        self.assertEqual(self.client.get("/api/gallery-state").get_json()["unviewed"], 0)

    def test_rejects_bad_secret_and_unsupported_file(self):
        response = self.client.post("/upload")
        self.assertEqual(response.status_code, 401)

        response = self.client.post(
            "/upload",
            headers={"X-Relay-Secret": "test-relay-secret"},
            data={"image": (io.BytesIO(b"not-an-image"), "bad.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 415)

    def test_delete_requires_csrf(self):
        self.login()
        response = self.client.post("/screenshots/missing/delete")
        self.assertEqual(response.status_code, 400)

    def test_timestamp_is_formatted_in_moscow_time(self):
        self.assertEqual(
            application.format_timestamp(1),
            "01.01.1970 03:00 МСК",
        )

    def test_new_screenshot_word_is_declined(self):
        for count in (0, 2, 5, 11, 12, 20, 111):
            self.assertEqual(application.new_screenshots_word(count), "новых")
        for count in (1, 21, 101):
            self.assertEqual(application.new_screenshots_word(count), "новый")

    def test_retention_setting_is_saved(self):
        csrf = self.login()
        response = self.client.post(
            "/settings/retention",
            data={"csrf_token": csrf, "retention_days": "7"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(application.current_retention_days(), 7)

    @patch.object(application, "send_message", return_value=True)
    def test_admin_sees_client_stop_confirmation(self, _send_message):
        csrf = self.login()
        with application.state_lock:
            application.last_seen = time.time()

        response = self.client.post(
            "/client/stop",
            data={"csrf_token": csrf},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(application.stop_requested)
        self.assertTrue(application.stop_pending)
        request_event_id = response.get_json()["client_event_id"]

        response = self.client.post(
            "/stopped",
            headers={"X-Relay-Secret": "test-relay-secret"},
        )
        self.assertEqual(response.status_code, 200)

        state = self.client.get("/api/gallery-state").get_json()
        self.assertFalse(state["client_active"])
        self.assertFalse(state["stop_pending"])
        self.assertGreater(state["client_event"]["id"], request_event_id)
        self.assertEqual(state["client_event"]["kind"], "stopped")
        self.assertEqual(
            state["client_event"]["message"],
            "Программа успешно завершила работу.",
        )


if __name__ == "__main__":
    unittest.main()
