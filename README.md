# P2C Crypto Sniper Bot

---

**🚀 Нужна максимальная скорость?** Это публичная версия. Для приобретения Private-версии (оптимизированный код, который ловит намного быстрее) и настройки правильного сервера под Low Latency обращайтесь в ЛС: [@ReNothingg](https://t.me/ReNothingg)

---

Автоматический перехват (снайпинг) P2C-ордеров с минимальной задержкой.

**Основные возможности:**

* **Гибридный мониторинг:** Одновременная работа через WebSockets и Polling для минимальной задержки.
* **Гибкие фильтры:** Настройка минимальной и максимальной суммы (Min/Max).
* **Скорость:** Оптимизированные TCP-соединения, uvloop и конкурентные запросы.
* **Аналитика:** Ежедневные отчеты и статистика пойманных объемов.
* **Безопасность:** Поддержка HTTP-прокси и безопасное хранение токенов.

---

## ЛИЦЕНЗИЯ И ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ

> **Данное ПО разработано исключительно в ознакомительных целях. Разработчик не несет ответственности за блокировки аккаунтов или финансовые потери. Используйте на свой страх и риск.**

Этот код распространяется под **гибридной лицензией**. Если решишь быть хитрожопым — у тебя будут проблемы. Читать внимательно:

1. **COPYLEFT (ТЫ ОБЯЗАН ДЕЛИТЬСЯ):**
В соответствии с принципами **GNU GPLv3**: если ты взял этот код, изменил хоть одну строчку и используешь его (даже для себя) — ты **ОБЯЗАН** выложить свой измененный код в **ОТКРЫТЫЙ ДОСТУП**.
*Никаких "приватных сборок" на основе моего кода. Взял бесплатно — отдавай бесплатно.*
2. **ОТСУТСТВИЕ ГАРАНТИЙ (AS IS):**
ПО предоставляется "КАК ЕСТЬ". Если из-за этого бота у тебя:
* Списали все деньги с карты;
* Забанили аккаунт;
* Взорвался сервер;
* Пришла полиция.
* Твоя мама забрала у тебя карточку

**ЭТО ТВОИ ЛИЧНЫЕ ПРОБЛЕМЫ.** Я не даю никаких гарантий работоспособности и безопасности.

**Скачивая и запуская этот скрипт, ты автоматически соглашаешься с тем, что ты сам отвечаешь за свои действия.**

---

## Установка на сервер (VPS)

### Подготовка окружения

Обновляем систему и ставим необходимые пакеты (Python, Git, Rust для быстрой компиляции библиотек):

```bash
apt update && apt upgrade -y
apt install python3-pip python3-venv git pkg-config libssl-dev -y

curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
```

### Установка бота

Клонируем репозиторий и ставим зависимости:

```bash
git clone https://github.com/ReNothingg/P2C-Crypto-Sniper-Bot.git
cd crypto

# Создаем виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Ставим библиотеки
pip3 install -r requirements.txt
```

### Первый запуск

Запуск с высоким приоритетом процесса (требует прав root):

```bash
sudo taskset -c 1 chrt -f 99 venv/bin/python3 main.py
```

*После запуска перейдите в Telegram-бота и нажмите /start для настройки токена и лимитов.*

---

## Запуск в режиме 24/7 (Daemon)

Чтобы бот работал вечно и запускался сам после перезагрузки:

1. **Создайте файл службы:**
```bash
nano /etc/systemd/system/crypto_bot.service
```

2. **Вставьте этот код (проверьте пути):**
```ini
[Unit]
Description=Crypto Sniper Bot
After=network.target

[Service]
User=root
# Путь к рабочей директории (проверьте командой pwd)
WorkingDirectory=/root/crypto
# Путь к python внутри виртуального окружения
ExecStart=/root/crypto/.venv/bin/python main.py
Restart=always
RestartSec=5
# Оптимизация приоритета (опционально)
CPUSchedulingPolicy=fifo
CPUSchedulingPriority=99

[Install]
WantedBy=multi-user.target
```


3. **Активируйте службу:**
```bash
systemctl daemon-reload
systemctl enable crypto_bot
systemctl start crypto_bot
```



### Полезные команды

* Статус: `systemctl status crypto_bot`
* Логи (смотреть в реальном времени): `journalctl -u crypto_bot -f`
* Перезапуск: `systemctl restart crypto_bot`
* Остановка: `systemctl stop crypto_bot`

---

## Обновление бота

**Важно:** Если структура базы данных изменилась, старую БД лучше удалить (или сделать бэкап).

```bash
systemctl stop crypto_bot
cd crypto
git config pull.rebase false
git pull
# Если нужно сбросить базу:
# rm bot_users.db
systemctl start crypto_bot
```

## Тестирование задержек (Ping)

Проверка связи с сервером Crypto Bot:

```bash
curl -w "DNS: %{time_namelookup}s | Connect: %{time_connect}s | SSL: %{time_appconnect}s | Total: %{time_total}s\n" -o /dev/null -s https://app.cr.bot/
ping -c 20 app.cr.bot
```