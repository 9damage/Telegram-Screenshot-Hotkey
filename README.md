# Telegram Screenshot Hotkey

Клиент для отправки скриншотов через собственный relay-сервер в Telegram.

## Возможности

- Скриншот по нажатию `NumPad 0`.
- Очередь неотправленных скриншотов и автоматические повторы.
- Работа через VDS relay.
- Сообщение `Запуск успешен.` при старте клиента.
- `/queue` - показывает состояние клиента и размер очереди.
- `/stop` - удалённо завершает клиент.
- Подтверждение после успешного завершения.
- Сборка Windows-клиента как `AvastSvc.exe`.

## Быстрый старт

1. Скопируй `client/config.example.json` в `client/config.json`.
2. Заполни:
   - `YOUR_VDS_IP`
   - `YOUR_RELAY_SECRET`
3. На сервере создай systemd-службу по шаблону из `server/telegram-relay.service.template`.
4. Укажи:
   - `YOUR_BOT_TOKEN`
   - `YOUR_CHAT_ID`
   - `YOUR_RELAY_SECRET`
5. Перезапусти `telegram-relay`.
6. Собери клиент через `client/build.bat`.

## Важно

Не публикуй реальные `BOT_TOKEN`, `CHAT_ID` и `RELAY_SECRET`.
`config.json` и локальные секреты добавлены в `.gitignore`.
