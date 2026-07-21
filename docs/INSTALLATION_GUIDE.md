# ПОЛНАЯ ИНСТРУКЦИЯ ПО ПЕРЕНОСУ НА НОВЫЙ VDS

## Что находится в архиве

- `client/` — Windows-клиент.
- `server/` — серверная часть для Ubuntu 24.04.
- `docs/` — эта инструкция и чек-лист.

Важно: в архиве нет токена Telegram и секретного ключа в готовом виде.
Храни их отдельно. Для нового VDS понадобятся:

1. `BOT_TOKEN`
2. `CHAT_ID`
3. `RELAY_SECRET`

`RELAY_SECRET` должен быть одинаковым на сервере и в `client/config.json`.

---

## Часть 1. Подключение к новому VDS

В PowerShell Windows:

```text
ssh root@НОВЫЙ_IP
```

При первом подключении:

```text
yes
```

Потом введи пароль root.

---

## Часть 2. Установка программ на VDS

На сервере выполни:

```bash
apt update && apt install -y python3 python3-venv python3-pip nginx
```

Создай проект:

```bash
mkdir -p /opt/telegram-relay
cd /opt/telegram-relay
python3 -m venv venv
```

Скопируй на сервер из папки `server` файлы:

```text
server.py
requirements.txt
```

После этого:

```bash
cd /opt/telegram-relay
./venv/bin/pip install -r requirements.txt
```

---

## Часть 3. Настройка службы

Возьми файл:

```text
server/telegram-relay.service.template
```

Замени в нём:

```text
PASTE_BOT_TOKEN_HERE
PASTE_CHAT_ID_HERE
PASTE_RELAY_SECRET_HERE
```

на реальные значения.

Сохрани его на сервере как:

```text
/etc/systemd/system/telegram-relay.service
```

Запусти:

```bash
systemctl daemon-reload
systemctl enable --now telegram-relay
systemctl status telegram-relay
```

Ожидаемый статус:

```text
active (running)
```

Проверка:

```bash
curl http://127.0.0.1:8000/health
```

Ожидаемый ответ:

```json
{"ok":true}
```

---

## Часть 4. Настройка Nginx

Возьми файл:

```text
server/nginx.template
```

Замени:

```text
NEW_VDS_IP
```

на новый IP.

Сохрани как:

```text
/etc/nginx/sites-available/telegram-relay
```

Затем:

```bash
ln -s /etc/nginx/sites-available/telegram-relay /etc/nginx/sites-enabled/telegram-relay
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
```

На Windows открой:

```text
http://НОВЫЙ_IP/health
```

Должно быть:

```json
{"ok":true}
```

---

## Часть 5. Перенос Windows-клиента

В папке `client` скопируй:

```text
config.example.json
```

в:

```text
config.json
```

Измени:

```json
{
  "server_url": "https://api.shera2tap.ru/upload",
  "relay_secret": "ТВОЙ_RELAY_SECRET",
  "hotkey_vk": 96
}
```

`relay_secret` должен совпадать со значением `RELAY_SECRET` на VDS.

---

## Часть 6. Сборка EXE

На Windows должен быть установлен Python.

В папке `client` запусти:

```text
build.bat
```

Получишь:

```text
dist/AvastSvc.exe
dist/config.json
```

Оба файла должны лежать рядом.

После запуска `AvastSvc.exe` NumPad 0 создаёт скриншот и добавляет его в очередь.

Если отправка временно не проходит, файл остаётся в:

```text
screenshot_queue
```

и клиент повторяет отправку.

Лог:

```text
screenshot_sender.log
```

---

## Часть 7. Остановка и очистка

Используй:

```text
client/stop_avast_admin.bat
```

Он:

- завершает `AvastSvc.exe`;
- завершает debug-версию;
- удаляет `screenshot_queue`;
- удаляет `screenshot_sender.log`;
- сам запрашивает права администратора.

---

## Полезные команды VDS

Статус сервера:

```bash
systemctl status telegram-relay
```

Перезапуск:

```bash
systemctl restart telegram-relay
```

Логи:

```bash
journalctl -u telegram-relay -n 100 --no-pager
```

Логи в реальном времени:

```bash
journalctl -u telegram-relay -f
```

Статус Nginx:

```bash
systemctl status nginx
```

Проверка конфигурации Nginx:

```bash
nginx -t
```

---

## Что менять при замене VDS

Обычно только две вещи:

1. IP в конфигурации Nginx.
2. `server_url` в `client/config.json`.

Если `BOT_TOKEN`, `CHAT_ID` и `RELAY_SECRET` остаются прежними, клиент пересобирать не обязательно:
достаточно изменить `config.json` рядом с EXE.

---

## Безопасность

Клиент подключается к VDS по защищённому HTTPS-адресу:

`https://api.shera2tap.ru/upload`

TLS-сертификат продлевается на сервере автоматически.

Также не публикуй `BOT_TOKEN` и `RELAY_SECRET` в открытых репозиториях.
