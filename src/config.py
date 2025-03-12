import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Конфигурация бота
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
DATABASE_URL = os.getenv('DATABASE_URL')
RABBITMQ_URL = os.getenv('RABBITMQ_URL')

# Настройки проверки сообщений
MIN_MESSAGE_LENGTH = 10
FORBIDDEN_WORDS = ["спам", "реклама", "казино", "ставки", "букмекер"]
SPAM_SYMBOLS = ["$$$", "!!!", "???", "###"]

# Настройки планировщика
MESSAGE_INTERVAL_HOURS = 8

# Настройки логирования
LOG_LEVEL = "INFO"

# Настройки DeepSeek AI
DEEPSEEK_API_URL = os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1/chat/completions')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat') 