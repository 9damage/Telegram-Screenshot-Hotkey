import json
import sys
import threading
import time
import uuid
from pathlib import Path

import mss
import requests
from pynput import keyboard


VERSION = "3.0"
DEFAULT_SERVER_URL = "https://api.shera2tap.ru/upload"
LEGACY_SERVER_URLS = {
    "http://147.45.38.195/upload",
    "https://147.45.38.195/upload",
}


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(
            sys.executable
        ).resolve().parent

    return Path(
        __file__
    ).resolve().parent


APP_DIR = app_dir()

CONFIG_PATH = (
    APP_DIR
    / "config.json"
)

QUEUE_DIR = (
    APP_DIR
    / "screenshot_queue"
)

LOG_PATH = (
    APP_DIR
    / "screenshot_sender.log"
)

QUEUE_DIR.mkdir(
    exist_ok=True
)

key_down = False

queue_event = (
    threading.Event()
)

stop_event = (
    threading.Event()
)


def normalize_server_url(value):
    server_url = str(
        value or DEFAULT_SERVER_URL
    ).strip().rstrip("/")

    if server_url in LEGACY_SERVER_URLS:
        return DEFAULT_SERVER_URL

    return server_url


def log(message):
    try:
        with LOG_PATH.open(
            "a",
            encoding="utf-8"
        ) as file:
            file.write(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"{message}\n"
            )

    except Exception:
        pass


def load_config():
    with CONFIG_PATH.open(
        "r",
        encoding="utf-8"
    ) as file:
        config = json.load(
            file
        )

    server_url = normalize_server_url(
        config.get(
            "server_url",
            DEFAULT_SERVER_URL
        )
    )

    relay_secret = str(
        config["relay_secret"]
    ).strip()

    hotkey_vk = int(
        config.get(
            "hotkey_vk",
            96
        )
    )

    base_url = (
        server_url.rsplit(
            "/",
            1
        )[0]
    )

    return {
        "server_url":
            server_url,

        "base_url":
            base_url,

        "relay_secret":
            relay_secret,

        "hotkey_vk":
            hotkey_vk
    }


def headers(config):
    return {
        "X-Relay-Secret":
            config["relay_secret"]
    }


def queue_count():
    return sum(
        1
        for _ in
        QUEUE_DIR.glob(
            "*.png"
        )
    )


def notify_startup():
    try:
        config = load_config()

        response = requests.post(
            f"{config['base_url']}/startup",

            headers=headers(
                config
            ),

            json={
                "queue_count":
                    queue_count()
            },

            timeout=30
        )

        if response.ok:
            log(
                "Сообщение о запуске отправлено."
            )

        else:
            log(
                f"Ошибка startup: "
                f"HTTP {response.status_code}"
            )

    except Exception as error:
        log(
            f"Ошибка startup: "
            f"{type(error).__name__}: "
            f"{error}"
        )


def notify_stopped():
    try:
        config = load_config()

        response = requests.post(
            f"{config['base_url']}/stopped",

            headers=headers(
                config
            ),

            timeout=30
        )

        if response.ok:
            log(
                "Сообщение о завершении отправлено."
            )

        else:
            log(
                f"Ошибка stopped: "
                f"HTTP {response.status_code}"
            )

    except Exception as error:
        log(
            f"Ошибка stopped: "
            f"{type(error).__name__}: "
            f"{error}"
        )


def heartbeat_worker():
    while not stop_event.is_set():
        try:
            config = load_config()

            response = requests.post(
                f"{config['base_url']}/heartbeat",

                headers=headers(
                    config
                ),

                json={
                    "queue_count":
                        queue_count()
                },

                timeout=30
            )

            if response.ok:
                data = response.json()

                if (
                    data.get(
                        "command"
                    )
                    == "stop"
                ):
                    log(
                        "Получена команда /stop."
                    )

                    stop_event.set()

                    return

            else:
                log(
                    f"Heartbeat: "
                    f"HTTP "
                    f"{response.status_code}"
                )

        except Exception as error:
            log(
                f"Ошибка heartbeat: "
                f"{type(error).__name__}: "
                f"{error}"
            )

        stop_event.wait(
            5
        )


def make_screenshot():
    filename = (
        f"{int(time.time() * 1000)}_"
        f"{uuid.uuid4().hex}.png"
    )

    path = (
        QUEUE_DIR
        / filename
    )

    try:
        with mss.mss() as sct:
            sct.shot(
                mon=-1,
                output=str(
                    path
                )
            )

        log(
            f"Добавлен в очередь: "
            f"{filename}"
        )

        queue_event.set()

    except Exception as error:
        log(
            f"Ошибка скриншота: "
            f"{type(error).__name__}: "
            f"{error}"
        )


def send_file(path):
    config = load_config()

    request_headers = headers(
        config
    )

    request_headers[
        "X-Upload-ID"
    ] = path.name

    size_mb = (
        path.stat().st_size
        / 1024
        / 1024
    )

    start = (
        time.monotonic()
    )

    log(
        f"Начало отправки: "
        f"{path.name}, "
        f"{size_mb:.2f} МБ"
    )

    with path.open(
        "rb"
    ) as photo:

        response = requests.post(
            config[
                "server_url"
            ],

            headers=request_headers,

            files={
                "image": (
                    "screenshot.png",
                    photo,
                    "image/png"
                )
            },

            timeout=(
                15,
                180
            )
        )

    elapsed = (
        time.monotonic()
        - start
    )

    log(
        f"Ответ сервера: "
        f"HTTP "
        f"{response.status_code}, "
        f"{elapsed:.1f} сек."
    )

    if not response.ok:
        raise RuntimeError(
            f"HTTP "
            f"{response.status_code}: "
            f"{response.text[:500]}"
        )

    data = response.json()

    if not data.get(
        "ok"
    ):
        raise RuntimeError(
            str(
                data
            )
        )

    return True


def queue_worker():
    retry_delay = 2

    while not stop_event.is_set():

        files = sorted(
            QUEUE_DIR.glob(
                "*.png"
            ),

            key=lambda item:
                item.name
        )

        if not files:
            queue_event.clear()

            queue_event.wait(
                timeout=5
            )

            continue

        path = files[0]

        try:
            send_file(
                path
            )

            log(
                f"Успешно отправлен: "
                f"{path.name}"
            )

            path.unlink(
                missing_ok=True
            )

            retry_delay = 2

        except Exception as error:
            log(
                f"Ошибка отправки "
                f"{path.name}: "
                f"{type(error).__name__}: "
                f"{error}. "
                f"Повтор через "
                f"{retry_delay} сек."
            )

            stop_event.wait(
                retry_delay
            )

            retry_delay = min(
                retry_delay * 2,
                30
            )


def on_press(key):
    global key_down

    if stop_event.is_set():
        return False

    try:
        config = load_config()

        if (
            getattr(
                key,
                "vk",
                None
            )
            == config[
                "hotkey_vk"
            ]
            and not key_down
        ):
            key_down = True

            threading.Thread(
                target=
                    make_screenshot,

                daemon=True
            ).start()

    except Exception as error:
        log(
            f"Ошибка клавиши: "
            f"{error}"
        )


def on_release(key):
    global key_down

    try:
        config = load_config()

        if (
            getattr(
                key,
                "vk",
                None
            )
            == config[
                "hotkey_vk"
            ]
        ):
            key_down = False

    except Exception:
        pass


def main():
    log(
        f"Telegram Screenshot Hotkey v{VERSION} запущен."
    )

    notify_startup()

    threading.Thread(
        target=
            queue_worker,

        daemon=True
    ).start()

    threading.Thread(
        target=
            heartbeat_worker,

        daemon=True
    ).start()

    with keyboard.Listener(
        on_press=
            on_press,

        on_release=
            on_release
    ) as listener:

        while not stop_event.is_set():
            time.sleep(
                0.25
            )

        listener.stop()

    log(
        "Завершение программы."
    )

    notify_stopped()


if __name__ == "__main__":
    main()
