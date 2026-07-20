НАЧНИ С ЭТОГО

Полная инструкция:
docs/INSTALLATION_GUIDE.md

Реальные секреты:
docs/CREDENTIALS.txt

Готовый service-файл с реальными секретами:
server/telegram-relay.service

Готовый текущий config:
client/config.json

При переносе на новый VDS:
1. Разверни server.py и requirements.txt.
2. Используй server/telegram-relay.service.
3. Настрой nginx на новый IP.
4. В client/config.json поменяй только server_url на новый IP.

Остановка клиента:
client/stop_avast_admin.bat

Если он не завершает процесс, запусти:
client/stop_avast_debug.bat
и посмотри, как именно Windows видит имя процесса.

Текущий процесс ожидается как:
AvastSvc.exe
