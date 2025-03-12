from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import logging
from aiogram import Bot
import os
from dotenv import load_dotenv
from .database import get_unsent_messages, mark_message_as_sent

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')

bot = Bot(token=BOT_TOKEN)

# Функция для отправки сообщений из базы данных
async def send_scheduled_messages():
    try:
        logger.info(f"Запуск планировщика отправки сообщений: {datetime.now()}")
        
        messages = get_unsent_messages()
        
        if not messages:
            logger.info("Нет неотправленных сообщений")
            return
        
        logger.info(f"Найдено {len(messages)} неотправленных сообщений")
        
        for message in messages:
            try:
                text = f"Сообщение от {message.username}:\n\n{message.text}"
                
                await bot.send_message(chat_id=CHANNEL_ID, text=text)
                
                mark_message_as_sent(message.id)
                
                logger.info(f"Сообщение #{message.id} от {message.username} успешно отправлено")
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения #{message.id}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Ошибка в планировщике: {str(e)}")

def setup_scheduler():
    scheduler = AsyncIOScheduler()
    
    scheduler.add_job(
        send_scheduled_messages,
        trigger=IntervalTrigger(hours=8),
        id='send_messages',
        replace_existing=True
    )
    
    return scheduler 