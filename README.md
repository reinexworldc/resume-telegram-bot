# Telegram Bot для отправки резюме в канал

Этот бот позволяет пользователям отправлять резюме, которые после проверки с помощью DeepSeek AI будут регулярно публиковаться в указанном Telegram-канале.

## Функциональность

- Проверка резюме на соответствие правилам с использованием DeepSeek AI
- Анализ орфографии, грамматики и структуры резюме
- Автоматическая отправка одобренных резюме в канал каждые 8 часов
- Уведомления пользователей о статусе их резюме
- Хранение резюме в PostgreSQL
- Использование RabbitMQ для очереди сообщений

## Требования

- Python 3.8+
- PostgreSQL
- RabbitMQ
- Доступ к API DeepSeek AI

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/telegram-channel-bot.git
cd telegram-channel-bot
```

2. Создайте виртуальное окружение и установите зависимости:
```bash
python -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Создайте файл `.env` в корневой директории проекта со следующими переменными:
```
BOT_TOKEN='ваш_токен_бота'
CHANNEL_ID='@ваш_канал' или '-100xxxxxxxxxx' для приватных каналов
DATABASE_URL='postgresql+asyncpg://username:password@localhost:5432/database_name'
RABBITMQ_URL='amqp://username:password@localhost:5672/'
DEEPSEEK_API_KEY='ваш_ключ_api_deepseek'
DEEPSEEK_MODEL='deepseek-chat'
DEEPSEEK_API_URL='https://api.deepseek.com/v1/chat/completions'
```

4. Создайте базу данных в PostgreSQL:
```bash
createdb database_name
```

5. Инициализируйте базу данных:
```bash
python src/migrate_db.py
```

## Запуск

1. Запустите RabbitMQ, если он еще не запущен:
```bash
# На Ubuntu/Debian
sudo service rabbitmq-server start

# На macOS с Homebrew
brew services start rabbitmq
```

2. Запустите бота:
```bash
python src/bot.py
```

## Миграция базы данных

Если вы обновили код бота и структура базы данных изменилась, вы можете выполнить миграцию:

1. Проверьте текущую структуру базы данных:
```bash
python src/migrate_db.py --check
```

2. Выполните миграцию (это удалит все данные!):
```bash
python src/migrate_db.py
```

## Команды бота

- `/start` - Начать работу с ботом
- `/status` - Проверить статус вашего резюме
- `/help` - Получить помощь по использованию бота

## Требования к резюме

- Резюме должно содержать хэштег #резюме
- Резюме должно быть грамотно составлено (проверяется с помощью DeepSeek AI)
- Резюме не должно содержать запрещенные слова и спам-символы

## Структура проекта

```
telegram-channel-bot/
├── src/
│   ├── bot.py         # Основной файл бота
│   ├── models.py      # Модели базы данных
│   ├── config.py      # Конфигурация
│   ├── ai_checker.py  # Модуль для проверки резюме с помощью DeepSeek AI
│   ├── safe_migrate.py # Безопасная миграция базы данных
│   └── migrate_db.py  # Скрипт миграции базы данных
├── .env               # Переменные окружения
├── requirements.txt   # Зависимости
└── README.md          # Документация
```

## Лицензия

MIT 