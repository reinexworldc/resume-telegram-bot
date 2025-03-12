import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import create_engine, Column, String, Integer, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import pika
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
DB_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://user:password@localhost:5432/bot_db')
RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')

# База данных
Base = declarative_base()
engine = create_async_engine(DB_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class UserMessage(Base):
    __tablename__ = 'user_messages'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    message = Column(String)
    last_sent = Column(Integer)
    approved = Column(Integer, default=0)  # 0 - не проверено, 1 - одобрено

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

def get_rabbit_connection():
    return pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))

def send_to_queue(username, message):
    connection = get_rabbit_connection()
    channel = connection.channel()
    channel.queue_declare(queue='message_check')
    channel.basic_publish(
        exchange='',
        routing_key='message_check',
        body=f"{username}:{message}".encode()
    )
    connection.close()

# Имитация проверки нейросетью (заглушка)
async def check_message_with_neural_net(message: str) -> bool:
    # Здесь будет ваша нейросеть
    # Пример: return True если сообщение прошло проверку
    return len(message) > 5 

def start_message_consumer():
    connection = get_rabbit_connection()
    channel = connection.channel()
    channel.queue_declare(queue='message_check')

    def callback(ch, method, properties, body):
        username, message = body.decode().split(':', 1)
        approved = asyncio.run(check_message_with_neural_net(message))
        
        async def update_db():
            async with async_session() as session:
                async with session.begin():
                    stmt = select(UserMessage).where(UserMessage.username == username)
                    result = await session.execute(stmt)
                    user_msg = result.scalar_one_or_none()
                    if user_msg:
                        user_msg.approved = 1 if approved else -1
                        await session.commit()
        
        asyncio.run(update_db())
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue='message_check', on_message_callback=callback)
    channel.start_consuming()

async def send_approved_message(username: str, message: str):
    await bot.send_message(CHANNEL_ID, f"Сообщение от @{username}:\n{message}")
    async with async_session() as session:
        async with session.begin():
            stmt = select(UserMessage).where(UserMessage.username == username)
            result = await session.execute(stmt)
            user_msg = result.scalar_one_or_none()
            if user_msg:
                user_msg.last_sent = int(datetime.now().timestamp())
                await session.commit()

async def schedule_messages():
    async with async_session() as session:
        stmt = select(UserMessage).where(UserMessage.approved == 1)
        result = await session.execute(stmt)
        messages = result.scalars().all()
        for msg in messages:
            if not msg.last_sent or (int(datetime.now().timestamp()) - msg.last_sent) >= 8 * 3600:
                scheduler.add_job(
                    send_approved_message,
                    trigger='interval',
                    hours=8,
                    args=(msg.username, msg.message),
                    id=f'msg_{msg.username}',
                    replace_existing=True
                )

@dp.message(Command("start"))
async def start_command(message: Message):
    await message.answer("Отправь сообщение, оно будет проверено и отправлено каждые 8 часов!")

@dp.message()
async def process_message(message: Message):
    if message.text and message.text.startswith('/'):
        return
    
    username = message.from_user.username or str(message.from_user.id)
    user_message = message.text
    
    async with async_session() as session:
        async with session.begin():
            stmt = select(UserMessage).where(UserMessage.username == username)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                existing.message = user_message
                existing.approved = 0
                existing.last_sent = None
            else:
                new_message = UserMessage(username=username, message=user_message)
                session.add(new_message)
            await session.commit()
    
    send_to_queue(username, user_message)
    await message.answer("Сообщение отправлено на проверку!")

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    scheduler.start()
    await schedule_messages()
    
    from threading import Thread
    consumer_thread = Thread(target=start_message_consumer, daemon=True)
    consumer_thread.start()
    
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())