import hmac
import math
import os
import secrets
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import requests
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from storage import ScreenshotStore


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
SCREENSHOT_DIR = Path(
    os.environ.get("SCREENSHOT_DIR", DATA_DIR / "screenshots")
)
DATABASE_PATH = Path(
    os.environ.get("DATABASE_PATH", DATA_DIR / "screenshots.db")
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
RELAY_SECRET = os.environ.get("RELAY_SECRET", "").strip()
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "").strip()
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "").strip()
DEFAULT_RETENTION_DAYS = max(int(os.environ.get("SCREENSHOT_RETENTION_DAYS", "0")), 0)
RETENTION_CHOICES = (0, 1, 3, 7, 14, 30, 90, 365)
MOSCOW_TZ = timezone(timedelta(hours=3), name="МСК")

app = Flask(__name__)
app.config.update(
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,
    SECRET_KEY=FLASK_SECRET_KEY or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=12 * 60 * 60,
)

store = ScreenshotStore(DATABASE_PATH, SCREENSHOT_DIR)
state_lock = threading.Lock()
login_lock = threading.Lock()

last_seen = 0.0
last_queue_count = 0
stop_requested = False
stop_pending = False
client_event_id = 0
client_event_kind = ""
client_event_message = ""
last_update_id = 0
login_attempts = {}


def relay_authorized():
    supplied_secret = request.headers.get("X-Relay-Secret", "")
    return bool(RELAY_SECRET) and hmac.compare_digest(
        supplied_secret,
        RELAY_SECRET,
    )


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def require_csrf():
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get("csrf_token", "")
    if not supplied or not expected or not hmac.compare_digest(supplied, expected):
        abort(400, description="Некорректный CSRF-токен")


def client_is_active():
    with state_lock:
        seen = last_seen
    return seen > 0 and (time.time() - seen) <= 15


def current_retention_days():
    try:
        value = int(store.get_setting("retention_days", DEFAULT_RETENTION_DAYS))
    except (TypeError, ValueError):
        value = DEFAULT_RETENTION_DAYS
    return value if value in RETENTION_CHOICES else DEFAULT_RETENTION_DAYS


def human_size(size_bytes):
    size = float(size_bytes or 0)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024


def free_disk_space():
    try:
        return shutil.disk_usage(DATA_DIR).free
    except OSError:
        return 0


def format_timestamp(timestamp):
    if not timestamp:
        return "—"
    return datetime.fromtimestamp(timestamp, MOSCOW_TZ).strftime("%d.%m.%Y %H:%M МСК")


app.jinja_env.globals.update(
    csrf_token=csrf_token,
    human_size=human_size,
    format_timestamp=format_timestamp,
)


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'"
    )
    if session.get("admin_authenticated"):
        response.headers["Cache-Control"] = "private, no-store"
    return response


def send_message(text):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text},
            timeout=60,
        )
        return response.ok
    except requests.RequestException:
        return False


def normalize_command(text):
    if not text.strip():
        return ""
    return text.strip().split()[0].split("@")[0].lower()


def command_worker():
    global last_update_id
    global stop_requested
    global stop_pending
    global client_event_id
    global client_event_kind
    global client_event_message

    while True:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={
                    "offset": last_update_id + 1,
                    "timeout": 50,
                    "allowed_updates": '["message"]',
                },
                timeout=65,
            )
            data = response.json()
            if not data.get("ok"):
                time.sleep(3)
                continue

            for update in data.get("result", []):
                last_update_id = max(last_update_id, int(update.get("update_id", 0)))
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                if str(chat.get("id")) != CHAT_ID:
                    continue

                command = normalize_command(str(message.get("text", "")))
                if command == "/queue":
                    with state_lock:
                        count = last_queue_count
                    if client_is_active():
                        send_message(
                            "Программа активна.\n"
                            f"В очереди {count} скриншотов.\n"
                            f"В веб-архиве {store.stats()['count']} скриншотов."
                        )
                    else:
                        send_message("Программа неактивна.")
                elif command == "/stop":
                    if client_is_active():
                        with state_lock:
                            stop_requested = True
                            stop_pending = True
                            client_event_id += 1
                            client_event_kind = "stop_requested"
                            client_event_message = "Команда завершения отправлена на устройство."
                        send_message("Команда остановки отправлена.")
                    else:
                        send_message("Программа неактивна.")
        except Exception:
            time.sleep(3)


def cleanup_worker():
    while True:
        retention_days = current_retention_days()
        if retention_days > 0:
            cutoff = time.time() - retention_days * 86400
            store.delete_older_than(cutoff)
        time.sleep(60)


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin_authenticated"):
        return redirect(url_for("gallery"))

    if request.method == "POST":
        require_csrf()
        if not ADMIN_PASSWORD_HASH:
            return render_template("login.html", configuration_missing=True), 503

        remote = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        remote = remote.split(",", 1)[0].strip()
        now = time.time()

        with login_lock:
            attempts = [item for item in login_attempts.get(remote, []) if now - item < 900]
            login_attempts[remote] = attempts
            blocked = len(attempts) >= 8

        if blocked:
            flash("Слишком много попыток. Повторите через 15 минут.", "error")
            return render_template("login.html"), 429

        if check_password_hash(ADMIN_PASSWORD_HASH, request.form.get("password", "")):
            with login_lock:
                login_attempts.pop(remote, None)
            session.clear()
            session.permanent = True
            session["admin_authenticated"] = True
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("gallery"))

        with login_lock:
            login_attempts.setdefault(remote, []).append(now)
        flash("Неверный пароль.", "error")

    return render_template("login.html", configuration_missing=not ADMIN_PASSWORD_HASH)


@app.post("/logout")
@admin_required
def logout():
    require_csrf()
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@admin_required
def gallery():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 24
    screenshots, total = store.list(page=page, per_page=per_page)
    statistics = store.stats()
    pages = max(math.ceil(total / per_page), 1)
    if page > pages and total:
        return redirect(url_for("gallery", page=pages))

    with state_lock:
        queue_count = last_queue_count
        seen = last_seen
        event_id = client_event_id

    return render_template(
        "gallery.html",
        screenshots=screenshots,
        stats=statistics,
        page=page,
        pages=pages,
        client_active=client_is_active(),
        queue_count=queue_count,
        last_seen=seen,
        client_event_id=event_id,
        screenshot_capacity_label=human_size(
            free_disk_space() + statistics["size_bytes"]
        ),
        retention_days=current_retention_days(),
        retention_choices=RETENTION_CHOICES,
    )


@app.get("/screenshots/<screenshot_id>/image")
@admin_required
def screenshot_image(screenshot_id):
    record = store.get(screenshot_id)
    if not record:
        abort(404)
    return send_from_directory(
        store.screenshot_dir,
        record["filename"],
        mimetype=record["content_type"],
        max_age=0,
    )


@app.get("/api/gallery-state")
@admin_required
def gallery_state():
    screenshots, total = store.list(page=1, per_page=24)
    statistics = store.stats()
    active = client_is_active()
    with state_lock:
        queue_count = last_queue_count
        pending = stop_pending
        event = {
            "id": client_event_id,
            "kind": client_event_kind,
            "message": client_event_message,
        }
    return jsonify(
        {
            "screenshots": [
                {
                    "id": item["id"],
                    "created_at": item["created_at"],
                    "created_label": format_timestamp(item["created_at"]),
                    "size_label": human_size(item["size_bytes"]),
                    "image_url": url_for("screenshot_image", screenshot_id=item["id"]),
                    "delete_url": url_for("delete_screenshot", screenshot_id=item["id"]),
                    "mark_viewed_url": url_for("mark_screenshot_viewed", screenshot_id=item["id"]),
                    "viewed": bool(item["viewed"]),
                }
                for item in screenshots
            ],
            "total": total,
            "size_label": human_size(statistics["size_bytes"]),
            "screenshot_capacity_label": human_size(
                free_disk_space() + statistics["size_bytes"]
            ),
            "unviewed": statistics["unviewed"],
            "client_active": active,
            "queue_count": queue_count,
            "stop_pending": pending,
            "client_event": event,
            "retention_days": current_retention_days(),
        }
    )


@app.post("/settings/retention")
@admin_required
def update_retention():
    require_csrf()
    try:
        retention_days = int(request.form.get("retention_days", ""))
    except ValueError:
        retention_days = -1

    if retention_days not in RETENTION_CHOICES:
        flash("Не удалось изменить срок хранения.", "error")
        return redirect(url_for("gallery"))

    store.set_setting("retention_days", retention_days)
    deleted = 0
    if retention_days > 0:
        deleted = store.delete_older_than(time.time() - retention_days * 86400)

    if retention_days:
        message = f"Автоочистка установлена: {retention_days} дн. Удалено: {deleted}."
    else:
        message = "Автоочистка отключена."
    flash(message, "success")
    return redirect(url_for("gallery"))


@app.post("/client/stop")
@admin_required
def stop_client():
    global stop_requested
    global stop_pending
    global client_event_id
    global client_event_kind
    global client_event_message
    require_csrf()
    if not client_is_active():
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"ok": False, "message": "Клиент сейчас неактивен."}), 409
        flash("Клиент сейчас неактивен.", "error")
        return redirect(url_for("gallery"))

    with state_lock:
        stop_requested = True
        stop_pending = True
        client_event_id += 1
        client_event_kind = "stop_requested"
        client_event_message = "Команда завершения отправлена на устройство."
        event_id = client_event_id
    message = "Команда завершения отправлена на устройство."
    if request.accept_mimetypes.best == "application/json":
        return jsonify({"ok": True, "message": message, "client_event_id": event_id})
    flash(message, "success")
    return redirect(url_for("gallery"))


@app.post("/screenshots/<screenshot_id>/viewed")
@admin_required
def mark_screenshot_viewed(screenshot_id):
    require_csrf()
    if not store.mark_viewed(screenshot_id):
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True})


@app.post("/screenshots/<screenshot_id>/delete")
@admin_required
def delete_screenshot(screenshot_id):
    require_csrf()
    if store.delete(screenshot_id):
        flash("Скриншот удалён.", "success")
    else:
        flash("Скриншот уже отсутствует.", "error")
    return redirect(request.form.get("return_to") or url_for("gallery"))


@app.post("/screenshots/delete-selected")
@admin_required
def delete_selected():
    require_csrf()
    selected = request.form.getlist("selected")
    deleted = store.delete_many(selected)
    flash(f"Удалено скриншотов: {deleted}.", "success")
    return redirect(url_for("gallery"))


@app.post("/screenshots/clear")
@admin_required
def clear_screenshots():
    require_csrf()
    if request.form.get("confirmation") != "УДАЛИТЬ ВСЕ":
        flash("Очистка отменена: подтверждение не совпало.", "error")
        return redirect(url_for("gallery"))
    deleted = store.clear()
    flash(f"Архив очищен. Удалено скриншотов: {deleted}.", "success")
    return redirect(url_for("gallery"))


@app.post("/startup")
def startup():
    global last_seen
    global last_queue_count
    global stop_requested
    global stop_pending
    if not relay_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    with state_lock:
        last_seen = time.time()
        last_queue_count = int(payload.get("queue_count", 0))
        stop_requested = False
        stop_pending = False
    send_message("Запуск успешен.")
    return jsonify({"ok": True})


@app.post("/heartbeat")
def heartbeat():
    global last_seen
    global last_queue_count
    global stop_requested
    if not relay_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    with state_lock:
        last_seen = time.time()
        last_queue_count = int(payload.get("queue_count", 0))
        command = "stop" if stop_requested else None
        stop_requested = False
    return jsonify({"ok": True, "command": command})


@app.post("/stopped")
def stopped():
    global last_seen
    global last_queue_count
    global stop_pending
    global client_event_id
    global client_event_kind
    global client_event_message
    if not relay_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    with state_lock:
        last_seen = 0.0
        last_queue_count = 0
        stop_pending = False
        client_event_id += 1
        client_event_kind = "stopped"
        client_event_message = "Программа успешно завершила работу."
    send_message("Программа успешно завершила работу.")
    return jsonify({"ok": True})


@app.post("/upload")
def upload():
    if not relay_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    image = request.files.get("image")
    if image is None:
        return jsonify({"ok": False, "error": "image_missing"}), 400

    image_data = image.read()
    if not image_data:
        return jsonify({"ok": False, "error": "empty_image"}), 400

    try:
        record, created = store.save(
            image_data,
            upload_id=request.headers.get("X-Upload-ID", "")[:200],
        )
    except ValueError:
        return jsonify({"ok": False, "error": "unsupported_image"}), 415
    except OSError as error:
        return jsonify({"ok": False, "error": "storage_error", "details": str(error)}), 507

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data={"chat_id": CHAT_ID},
            files={"photo": (record["filename"], image_data, record["content_type"])},
            timeout=60,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {
                "ok": False,
                "error": "telegram_non_json",
                "telegram_status": response.status_code,
            }
        payload["screenshot_id"] = record["id"]
        payload["stored"] = True
        payload["new_screenshot"] = created
        return jsonify(payload), response.status_code
    except requests.RequestException as error:
        return jsonify(
            {
                "ok": False,
                "error": type(error).__name__,
                "details": str(error),
                "screenshot_id": record["id"],
                "stored": True,
            }
        ), 502


if os.environ.get("DISABLE_BACKGROUND_WORKERS") != "1":
    threading.Thread(target=command_worker, daemon=True).start()
    threading.Thread(target=cleanup_worker, daemon=True).start()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
