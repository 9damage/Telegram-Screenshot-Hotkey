import hmac
import os
import threading
import time

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
RELAY_SECRET = os.environ.get("RELAY_SECRET", "").strip()

state_lock = threading.Lock()

last_seen = 0.0
last_queue_count = 0
stop_requested = False
last_update_id = 0


def authorized():
    supplied_secret = request.headers.get(
        "X-Relay-Secret",
        ""
    )

    return (
        bool(RELAY_SECRET)
        and hmac.compare_digest(
            supplied_secret,
            RELAY_SECRET
        )
    )


def send_message(text):
    try:
        response = requests.post(
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text
            },
            timeout=60
        )

        return response.ok

    except requests.RequestException:
        return False


def client_is_active():
    with state_lock:
        seen = last_seen

    return (
        seen > 0
        and (time.time() - seen) <= 15
    )


def normalize_command(text):
    if not text.strip():
        return ""

    first_part = text.strip().split()[0]

    return (
        first_part
        .split("@")[0]
        .lower()
    )


def command_worker():
    global last_update_id
    global stop_requested

    while True:
        try:
            response = requests.get(
                f"https://api.telegram.org/"
                f"bot{BOT_TOKEN}/getUpdates",
                params={
                    "offset": last_update_id + 1,
                    "timeout": 50,
                    "allowed_updates": '["message"]'
                },
                timeout=65
            )

            data = response.json()

            if not data.get("ok"):
                time.sleep(3)
                continue

            for update in data.get("result", []):
                update_id = int(
                    update.get(
                        "update_id",
                        0
                    )
                )

                last_update_id = max(
                    last_update_id,
                    update_id
                )

                message = (
                    update.get("message")
                    or {}
                )

                chat = (
                    message.get("chat")
                    or {}
                )

                text = str(
                    message.get(
                        "text",
                        ""
                    )
                ).strip()

                if str(
                    chat.get("id")
                ) != CHAT_ID:
                    continue

                command = normalize_command(text)

                if command == "/queue":
                    with state_lock:
                        count = last_queue_count

                    if client_is_active():
                        send_message(
                            "Программа активна.\n"
                            f"В очереди {count} скриншотов."
                        )
                    else:
                        send_message(
                            "Программа неактивна."
                        )

                elif command == "/stop":
                    if client_is_active():
                        with state_lock:
                            stop_requested = True

                        send_message(
                            "Команда остановки отправлена."
                        )
                    else:
                        send_message(
                            "Программа неактивна."
                        )

        except Exception:
            time.sleep(3)


@app.get("/health")
def health():
    return jsonify({
        "ok": True
    })


@app.post("/startup")
def startup():
    global last_seen
    global last_queue_count
    global stop_requested

    if not authorized():
        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 401

    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    with state_lock:
        last_seen = time.time()

        last_queue_count = int(
            payload.get(
                "queue_count",
                0
            )
        )

        stop_requested = False

    send_message(
        "Запуск успешен."
    )

    return jsonify({
        "ok": True
    })


@app.post("/heartbeat")
def heartbeat():
    global last_seen
    global last_queue_count
    global stop_requested

    if not authorized():
        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 401

    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )

    with state_lock:
        last_seen = time.time()

        last_queue_count = int(
            payload.get(
                "queue_count",
                0
            )
        )

        if stop_requested:
            command = "stop"
            stop_requested = False
        else:
            command = None

    return jsonify({
        "ok": True,
        "command": command
    })


@app.post("/stopped")
def stopped():
    global last_seen
    global last_queue_count

    if not authorized():
        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 401

    with state_lock:
        last_seen = 0.0
        last_queue_count = 0

    send_message(
        "Программа успешно завершила работу."
    )

    return jsonify({
        "ok": True
    })


@app.post("/upload")
def upload():
    if not authorized():
        return jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 401

    image = request.files.get(
        "image"
    )

    if image is None:
        return jsonify({
            "ok": False,
            "error": "image_missing"
        }), 400

    image_data = image.read()

    if not image_data:
        return jsonify({
            "ok": False,
            "error": "empty_image"
        }), 400

    try:
        response = requests.post(
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendPhoto",
            data={
                "chat_id": CHAT_ID
            },
            files={
                "photo": (
                    "screenshot.png",
                    image_data,
                    "image/png"
                )
            },
            timeout=60
        )

        try:
            payload = response.json()

        except ValueError:
            payload = {
                "ok": False,
                "error": "telegram_non_json",
                "telegram_status":
                    response.status_code,
                "telegram_response":
                    response.text[:1000]
            }

        return (
            jsonify(payload),
            response.status_code
        )

    except requests.RequestException as error:
        return jsonify({
            "ok": False,
            "error":
                type(error).__name__,
            "details":
                str(error)
        }), 502


threading.Thread(
    target=command_worker,
    daemon=True
).start()
