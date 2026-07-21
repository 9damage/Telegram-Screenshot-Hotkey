import getpass
import os
import secrets
import tempfile
from pathlib import Path

from werkzeug.security import generate_password_hash


ENV_PATH = Path("/etc/telegram-relay/admin.env")


def main():
    password = getpass.getpass("Новый пароль панели: ")
    confirmation = getpass.getpass("Повторите пароль: ")

    if password != confirmation:
        raise SystemExit("Пароли не совпадают.")
    if len(password) < 10:
        raise SystemExit("Пароль должен содержать не менее 10 символов.")

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    values = {
        "ADMIN_PASSWORD_HASH": generate_password_hash(password),
        "FLASK_SECRET_KEY": secrets.token_hex(32),
        "COOKIE_SECURE": "1",
        "SCREENSHOT_RETENTION_DAYS": "0",
        "DATA_DIR": "/opt/telegram-relay/data",
    }

    descriptor, temporary_name = tempfile.mkstemp(
        prefix="admin.env.",
        dir=ENV_PATH.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            for key, value in values.items():
                output.write(f"{key}={value}\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, ENV_PATH)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)

    print("Пароль панели настроен. Перезапустите telegram-relay.")


if __name__ == "__main__":
    main()
