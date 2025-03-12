# Telegram Bot с отложенной отправкой сообщений

Этот бот принимает сообщения от пользователей, сохраняет их в базе данных PostgreSQL и отправляет в указанный Telegram канал каждые 8 часов.

## Требования

- Python 3.7+
- PostgreSQL
- Telegram Bot Token (от @BotFather)
- Telegram канал, где бот является администратором

## Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd <repository-directory>
```

2. Создайте виртуальное окружение и установите зависимости:
```bash
python -m venv .venv
source .venv/bin/activate  # для Linux/Mac
# или
.venv\Scripts\activate  # для Windows
pip install -r requirements.txt
```

3. Создайте базу данных в PostgreSQL:
```bash
createdb telegram_bot
```

4. Настройте файл `.env` с вашими параметрами:
```
BOT_TOKEN=your_bot_token_here
CHANNEL_ID=your_channel_id_here
DATABASE_URL=postgresql://username:password@localhost/telegram_bot
```

## Запуск бота

```bash
python src/bot.py
```

## Структура проекта

- `src/bot.py` - основной файл бота
- `src/database.py` - модуль для работы с базой данных
- `src/scheduler.py` - модуль планировщика для отправки сообщений

## Как это работает

1. Пользователь отправляет сообщение боту
2. Бот сохраняет сообщение в базе данных PostgreSQL с именем пользователя
3. Планировщик каждые 8 часов проверяет наличие неотправленных сообщений
4. Если есть неотправленные сообщения, они отправляются в канал и помечаются как отправленные

## Примечания

- Бот должен быть администратором канала для отправки сообщений
- ID канала должен начинаться с `-100` для публичных каналов
- Для тестирования можно изменить интервал отправки в файле `src/scheduler.py` 