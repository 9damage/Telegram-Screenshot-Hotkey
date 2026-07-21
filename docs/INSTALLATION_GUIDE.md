# Установка Telegram Screenshot Hotkey 3.0

## 1. Подготовка Ubuntu 24.04

```bash
apt update
apt install -y python3-venv nginx certbot python3-certbot-nginx
install -d -m 755 /opt/telegram-relay
install -d -m 700 /etc/telegram-relay
```

Скопируйте в `/opt/telegram-relay`:

- `server.py`;
- `storage.py`;
- `set_admin_password.py`;
- `requirements.txt`;
- `telegram-relay.service.template`;
- `nginx.template`;
- каталоги `templates/` и `static/`.

## 2. Окружение Python

```bash
cd /opt/telegram-relay
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 3. Секреты сервера

Создайте `/etc/telegram-relay/relay.env` по образцу `server/.env.example` и заполните:

```text
BOT_TOKEN=...
CHAT_ID=...
RELAY_SECRET=...
COOKIE_SECURE=1
SCREENSHOT_RETENTION_DAYS=0
DATA_DIR=/opt/telegram-relay/data
```

Ограничьте доступ:

```bash
chmod 600 /etc/telegram-relay/relay.env
```

Настройте пароль панели длиной не менее 10 символов:

```bash
cd /opt/telegram-relay
./venv/bin/python set_admin_password.py
```

## 4. Служба systemd

```bash
cp /opt/telegram-relay/telegram-relay.service.template /etc/systemd/system/telegram-relay.service
systemctl daemon-reload
systemctl enable --now telegram-relay
systemctl status telegram-relay --no-pager
```

Проверка приложения:

```bash
curl http://127.0.0.1:8000/health
```

Ожидаемый ответ: `{"ok":true}`.

## 5. Nginx и HTTPS

Скопируйте `server/nginx.template`:

```bash
cp /opt/telegram-relay/nginx.template /etc/nginx/sites-available/telegram-relay
ln -s /etc/nginx/sites-available/telegram-relay /etc/nginx/sites-enabled/telegram-relay
nginx -t
systemctl reload nginx
```

Выпустите сертификат:

```bash
certbot --nginx --redirect -d shera2tap.ru -d www.shera2tap.ru -d api.shera2tap.ru
```

Проверьте:

```bash
curl https://api.shera2tap.ru/health
systemctl status certbot.timer --no-pager
```

## 6. Клиент Windows

Создайте `client/config.json`:

```json
{
  "server_url": "https://api.shera2tap.ru/upload",
  "relay_secret": "ВАШ_RELAY_SECRET",
  "hotkey_vk": 96
}
```

Соберите клиент:

```text
client\build.bat
```

Перенесите `AvastSvc.exe` и `config.json` из `client/dist/` в одну папку.

## 7. Проверка

1. Откройте `https://shera2tap.ru` и войдите в панель.
2. Запустите `AvastSvc.exe`.
3. Нажмите `NumPad 0`.
4. Убедитесь, что новый снимок появился без обновления страницы.
5. Проверьте `/queue` и `/stop` в Telegram.

## Обновление

Перед заменой клиента завершите `AvastSvc.exe`. На сервере замените код, затем выполните:

```bash
systemctl restart telegram-relay
systemctl is-active telegram-relay
```

Данные галереи находятся в `/opt/telegram-relay/data` и при обновлении не удаляются.
