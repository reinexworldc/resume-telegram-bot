import asyncio
import logging
import aio_pika
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

# Пытаемся импортировать как модуль, если не получается - используем относительные пути
try:
    from src.models import Base, UserMessage
    from src.config import (
        BOT_TOKEN, CHANNEL_ID, DATABASE_URL, RABBITMQ_URL,
        MIN_MESSAGE_LENGTH, FORBIDDEN_WORDS, SPAM_SYMBOLS,
        MESSAGE_INTERVAL_HOURS, LOG_LEVEL
    )
    from src.ai_checker import check_resume_with_ai
except ImportError:
    from models import Base, UserMessage
    from config import (
        BOT_TOKEN, CHANNEL_ID, DATABASE_URL, RABBITMQ_URL,
        MIN_MESSAGE_LENGTH, FORBIDDEN_WORDS, SPAM_SYMBOLS,
        MESSAGE_INTERVAL_HOURS, LOG_LEVEL
    )
    from ai_checker import check_resume_with_ai

# Настройка логирования
logging.basicConfig(level=getattr(logging, LOG_LEVEL))
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализация планировщика
scheduler = AsyncIOScheduler()

# Настройка базы данных
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Создание таблиц при запуске
async def init_db():
    try:
        # Проверяем, существуют ли таблицы
        async with engine.connect() as conn:
            # Проверяем наличие таблицы user_messages
            from sqlalchemy import text
            result = await conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_messages')"))
            exists = result.scalar()
            
            if not exists:
                logger.warning("Таблица user_messages не существует! Создаю таблицы...")
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                logger.info("Таблицы созданы")
            else:
                # Проверяем наличие колонки id
                result = await conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'user_messages' AND column_name = 'id')"))
                has_id = result.scalar()
                
                if not has_id:
                    logger.error("Структура базы данных устарела! Запустите скрипт миграции: python src/migrate_db.py")
                    raise Exception("Структура базы данных устарела")
                
                logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise

# Отправка в очередь RabbitMQ
async def send_to_queue(username: str, message: str):
    try:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            # Создаем очередь с параметром durable=True для сохранения сообщений при перезапуске
            queue = await channel.declare_queue('message_check', durable=True)
            
            # Создаем сообщение с параметром delivery_mode=2 для сохранения в RabbitMQ
            # Добавляем timestamp для отслеживания актуальности сообщения
            timestamp = datetime.now().timestamp()
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=f"{username}:{message}:{timestamp}".encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=queue.name
            )
            logger.info(f"Сообщение от {username} успешно отправлено в очередь (timestamp: {timestamp})")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения в очередь: {e}")
        # Повторно выбрасываем исключение, чтобы уведомить пользователя
        raise

# Расширенная проверка сообщения
async def check_message_with_neural_net(message: str) -> tuple[bool, str]:
    """
    Проверяет сообщение с помощью нейронной сети DeepSeek AI.
    
    Args:
        message: Текст сообщения для проверки
        
    Returns:
        tuple: (одобрено, отчет о проверке)
    """
    try:
        # Проверка на минимальную длину
        if len(message) < MIN_MESSAGE_LENGTH:
            return False, f"❌ Сообщение слишком короткое. Минимальная длина - {MIN_MESSAGE_LENGTH} символов."
        
        # Проверка на запрещенные слова
        forbidden_words = FORBIDDEN_WORDS
        for word in forbidden_words:
            if word.lower() in message.lower():
                return False, f"❌ Сообщение содержит запрещенное слово: {word}"
        
        # Проверка на спам-символы
        spam_symbols = SPAM_SYMBOLS
        for symbol in spam_symbols:
            if symbol in message:
                return False, f"❌ Сообщение содержит спам-символы: {symbol}"
        
        # Проверка с помощью DeepSeek AI
        return await check_resume_with_ai(message)
    
    except Exception as e:
        logger.error(f"Ошибка при проверке сообщения: {e}")
        # В случае ошибки лучше отклонить сообщение
        return False, f"❌ Произошла ошибка при проверке: {str(e)}"

# Consumer для RabbitMQ
async def consumer():
    try:
        # Подключение к RabbitMQ
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        async with connection:
            # Создание канала
            channel = await connection.channel()
            # Объявление очереди с параметром durable=True
            queue = await channel.declare_queue('message_check', durable=True)
            
            logger.info("Запущен consumer для обработки сообщений")
            
            # Асинхронная обработка сообщений
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        try:
                            # Обработка сообщения
                            message_body = message.body.decode()
                            logger.info(f"Получено сообщение: {message_body}")
                            
                            # Разбор сообщения
                            parts = message_body.split(':', 2)
                            if len(parts) == 3:
                                username, msg_text, timestamp = parts
                                await process_message(username, msg_text, float(timestamp))
                            else:
                                logger.warning(f"Неверный формат сообщения: {message_body}")
                        except Exception as e:
                            logger.error(f"Ошибка при обработке сообщения из очереди: {e}")
                            # Продолжаем работу, не прерывая цикл обработки
    except Exception as e:
        logger.error(f"Ошибка в consumer: {e}")
        # Пауза перед повторным подключением
        await asyncio.sleep(5)
        # Рекурсивный вызов для перезапуска consumer
        await consumer()

# Отправка одобренных сообщений
async def send_approved_message(username: str, message: str):
    try:
        # Отправка сообщения в канал
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"Сообщение от @{username}:\n\n{message}"
        )
        logger.info(f"Сообщение от {username} отправлено в канал {CHANNEL_ID}")
        
        # Обновление времени последней отправки в базе данных
        async with async_session() as session:
            async with session.begin():
                stmt = select(UserMessage).where(UserMessage.username == username)
                result = await session.execute(stmt)
                user_msg = result.scalar_one_or_none()
                
                if user_msg:
                    user_msg.last_sent = datetime.now()
                    await session.commit()
                    logger.info(f"Обновлено время последней отправки для {username}")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения в канал: {e}")

@dp.message(Command("start"))
async def start_command(message: types.Message):
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 Я бот для отправки резюме в канал.\n\n"
        "📝 Просто отправь мне текст своего резюме с хэштегом #резюме, и я проверю его на соответствие правилам.\n"
        "✅ Если резюме пройдет проверку, оно будет отправляться в канал каждые "
        f"{MESSAGE_INTERVAL_HOURS} часов.\n\n"
        "⚠️ Важно: Ваше сообщение должно содержать хэштег #резюме и быть правильно оформлено!\n\n"
        "📊 Ты можешь проверить статус своего резюме с помощью команды /status\n\n"
        "📋 Доступные команды:\n"
        "/start - Показать это сообщение\n"
        "/status - Проверить статус вашего резюме\n"
        "/help - Получить помощь по использованию бота"
    )
    
    await message.answer(welcome_text)

@dp.message(Command("status"))
async def status_command(message: types.Message):
    username = message.from_user.username or str(message.from_user.id)
    
    async with async_session() as session:
        stmt = select(UserMessage).where(UserMessage.username == username)
        result = await session.execute(stmt)
        user_msg = result.scalar_one_or_none()
        
        if not user_msg:
            await message.answer("❌ У вас нет активных сообщений. Отправьте сообщение для проверки.")
            return
        
        status_text = "📊 Статус вашего сообщения:\n\n"
        status_text += f"📝 Сообщение: {user_msg.message}\n\n"
        
        if user_msg.approved == 0:
            status_text += "⏳ Статус: На проверке\n"
        elif user_msg.approved == 1:
            status_text += "✅ Статус: Одобрено\n"
            if user_msg.last_sent:
                last_sent_time = user_msg.last_sent
                status_text += f"🕒 Последняя отправка: {last_sent_time.strftime('%d.%m.%Y %H:%M:%S')}\n"
                next_send = last_sent_time + timedelta(hours=MESSAGE_INTERVAL_HOURS)
                status_text += f"⏰ Следующая отправка: {next_send.strftime('%d.%m.%Y %H:%M:%S')}\n"
        elif user_msg.approved == -1:
            status_text += "❌ Статус: Отклонено\n"
            if user_msg.check_result:
                status_text += f"\n📋 Результаты проверки:\n{user_msg.check_result}\n"
                status_text += "\nПожалуйста, исправьте сообщение и отправьте снова."
        
        await message.answer(status_text)

@dp.message(Command("help"))
async def help_command(message: types.Message):
    help_text = (
        "📚 Помощь по использованию бота\n\n"
        "🤖 Этот бот позволяет отправлять резюме в канал после проверки.\n\n"
        "📝 Как использовать бота:\n"
        "1. Отправьте текст резюме боту с хэштегом #резюме\n"
        "2. Бот проверит резюме с помощью DeepSeek AI на соответствие правилам\n"
        "3. Если резюме одобрено, оно будет отправлено в канал\n"
        "4. Одобренные резюме будут отправляться в канал каждые "
        f"{MESSAGE_INTERVAL_HOURS} часов\n\n"
        "❗ Требования к резюме:\n"
        f"- Минимальная длина сообщения: {MIN_MESSAGE_LENGTH} символов\n"
        "- Резюме должно содержать хэштег #резюме\n"
        "- Резюме должно быть грамотно составлено (проверяется с помощью DeepSeek AI)\n"
        "- Резюме не должно содержать запрещенные слова и спам-символы\n\n"
        "📊 Статусы резюме:\n"
        "⏳ На проверке - резюме ожидает проверки\n"
        "✅ Одобрено - резюме прошло проверку и будет отправляться в канал\n"
        "❌ Отклонено - резюме не прошло проверку\n\n"
        "📋 Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/status - Проверить статус вашего резюме\n"
        "/help - Показать это сообщение"
    )
    
    await message.answer(help_text)

@dp.message()
async def process_message_handler(message: types.Message):
    if message.text and message.text.startswith('/'):
        return
    
    username = message.from_user.username or str(message.from_user.id)
    user_id = message.from_user.id  # Получаем числовой ID
    user_message = message.text
    
    if len(user_message) <= 5:
        await message.answer("❌ Сообщение слишком короткое. Минимальная длина - 6 символов.")
        return
    
    # Сохраняем сообщение в базе данных
    async with async_session() as session:
        async with session.begin():
            # Проверяем, есть ли уже сообщение от этого пользователя
            stmt = select(UserMessage).where(UserMessage.username == username)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            is_update = False
            current_time = datetime.now()
            
            if existing:
                is_update = True
                old_message = existing.message
                existing.message = user_message
                existing.approved = 0
                existing.last_sent = None
                existing.check_result = None
                existing.last_update = current_time
                logger.info(f"Обновлено существующее сообщение пользователя {username}. Старое: '{old_message}', Новое: '{user_message}'")
            else:
                new_message = UserMessage(
                    username=username,
                    message=user_message,
                    approved=0,
                    last_update=current_time
                )
                session.add(new_message)
                logger.info(f"Создано новое сообщение от пользователя {username}: '{user_message}'")
            
            await session.commit()
    
    await send_to_queue(username, user_message)
    
    if is_update:
        await message.answer(
            "🔄 Ваше предыдущее сообщение было заменено на новое!\n\n"
            "⏳ Сообщение отправлено на проверку!\n\n"
            "Вы получите уведомление о результате проверки.\n"
            f"Если сообщение будет одобрено, оно будет отправляться в канал каждые {MESSAGE_INTERVAL_HOURS} часов."
        )
    else:
        await message.answer(
            "⏳ Сообщение отправлено на проверку!\n\n"
            "Вы получите уведомление о результате проверки.\n"
            f"Если сообщение будет одобрено, оно будет отправляться в канал каждые {MESSAGE_INTERVAL_HOURS} часов."
        )

# Функция для обработки сообщений из очереди
async def process_message(username: str, msg_text: str, timestamp: float):
    try:
        logger.info(f"Обработка сообщения от пользователя {username} (timestamp: {timestamp})")
        
        # Проверяем сообщение
        approved, check_report = await check_message_with_neural_net(msg_text)
        logger.info(f"Результат проверки для {username}: {'Одобрено' if approved else 'Отклонено'}")
        
        # Обновляем статус в базе данных
        async with async_session() as session:
            async with session.begin():
                stmt = select(UserMessage).where(UserMessage.username == username)
                result = await session.execute(stmt)
                user_msg = result.scalar_one_or_none()
                
                if user_msg:
                    # Проверяем, что сообщение в базе данных совпадает с проверенным
                    # Если не совпадает, значит пользователь отправил новое сообщение
                    if user_msg.message != msg_text:
                        logger.warning(f"Сообщение от {username} в базе данных не совпадает с проверенным. Пропускаем обновление статуса.")
                        return
                    
                    # Проверяем, что сообщение не устарело (пользователь мог отправить новое сообщение)
                    if hasattr(user_msg, 'last_update') and user_msg.last_update:
                        last_update_timestamp = user_msg.last_update.timestamp()
                        if last_update_timestamp > timestamp:
                            logger.warning(f"Сообщение от {username} устарело (timestamp: {timestamp}, last_update: {last_update_timestamp}). Пропускаем обновление статуса.")
                            return
                    
                    user_msg.approved = 1 if approved else -1
                    user_msg.check_result = check_report
                    await session.commit()
                    logger.info(f"Статус сообщения от {username} обновлен в базе данных")
                else:
                    logger.warning(f"Пользователь {username} не найден в базе данных")
                    return
        
        # Пытаемся отправить уведомление пользователю
        try:
            # Проверяем, является ли username числом (ID пользователя)
            chat_id = int(username) if username.isdigit() else username
            
            if approved:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"✅ Ваше сообщение прошло проверку и будет отправлено в канал!\n\nРезультаты проверки:\n{check_report}"
                    )
                    logger.info(f"Уведомление об одобрении отправлено пользователю {username}")
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление пользователю {username}: {e}")
                
                # Отправляем сообщение в канал в любом случае
                await send_approved_message(username, msg_text)
                
                # Планируем повторения каждые MESSAGE_INTERVAL_HOURS часов
                scheduler.add_job(
                    send_approved_message,
                    trigger='interval',
                    hours=MESSAGE_INTERVAL_HOURS,
                    start_date=datetime.now() + timedelta(hours=MESSAGE_INTERVAL_HOURS),
                    args=(username, msg_text),
                    id=f"msg_{username}",
                    replace_existing=True
                )
                logger.info(f"Запланирована регулярная отправка сообщения от {username}")
            else:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ Ваше сообщение не прошло проверку и не будет отправлено.\n\nРезультаты проверки:\n{check_report}\n\nПожалуйста, исправьте сообщение и отправьте снова."
                    )
                    logger.info(f"Уведомление об отклонении отправлено пользователю {username}")
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление пользователю {username}: {e}")
        except Exception as e:
            logger.error(f"Общая ошибка при обработке сообщения: {e}")
    except Exception as e:
        logger.error(f"Критическая ошибка в обработчике сообщений: {e}")

async def restore_scheduled_messages():
    """Восстанавливает запланированные сообщения из базы данных"""
    try:
        logger.info("Восстановление запланированных сообщений...")
        async with async_session() as session:
            # Получаем все одобренные сообщения
            stmt = select(UserMessage).where(UserMessage.approved == 1)
            result = await session.execute(stmt)
            approved_messages = result.scalars().all()
            
            count = 0
            for msg in approved_messages:
                # Планируем отправку сообщения
                scheduler.add_job(
                    send_approved_message,
                    trigger='interval',
                    hours=MESSAGE_INTERVAL_HOURS,
                    start_date=datetime.now() + timedelta(minutes=1),  # Начинаем через минуту
                    args=(msg.username, msg.message),
                    id=f"msg_{msg.username}",
                    replace_existing=True
                )
                count += 1
            
            logger.info(f"Восстановлено {count} запланированных сообщений")
    except Exception as e:
        logger.error(f"Ошибка при восстановлении запланированных сообщений: {e}")

async def main():
    try:
        # Запускаем безопасную миграцию
        from safe_migrate import safe_migrate
        await safe_migrate()
        logger.info("Безопасная миграция выполнена")
        
        # Инициализируем базу данных
        await init_db()
        logger.info("База данных инициализирована")
        
        # Запускаем планировщик
        scheduler.start()
        logger.info("Планировщик запущен")
        
        # Запускаем consumer в отдельной задаче
        consumer_task = asyncio.create_task(consumer())
        logger.info("Consumer запущен в отдельной задаче")
        
        # Восстанавливаем запланированные задачи из базы данных
        await restore_scheduled_messages()
        logger.info("Запланированные сообщения восстановлены")
        
        # Запускаем бота
        logger.info("Запускаем бота...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())