import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Конфигурация бота
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
DATABASE_URL = os.getenv('DATABASE_URL')

# Настройки проверки сообщений
MIN_MESSAGE_LENGTH = 10
FORBIDDEN_WORDS = ["спам", "реклама", "казино", "ставки", "букмекер"]
SPAM_SYMBOLS = ["$$$", "!!!", "???", "###"]

# Настройки планировщика
MESSAGE_INTERVAL_HOURS = 8

# Настройки логирования
LOG_LEVEL = "INFO"

# Настройки X.AI (Grok)
GROK_API_URL = os.getenv('GROK_API_URL', 'https://api.x.ai/v1/chat/completions')
GROK_API_KEY = os.getenv('GROK_API_KEY')
GROK_MODEL = os.getenv('GROK_MODEL', 'grok-2-latest') 