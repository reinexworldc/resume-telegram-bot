import asyncio
import logging
import random
import sys
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

# Добавляем родительскую директорию в sys.path для корректного импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Пытаемся импортировать как модуль, если не получается - используем относительные пути
try:
    from src.models import Base, UserMessage
    from src.config import (
        BOT_TOKEN, CHANNEL_ID, DATABASE_URL,
        MIN_MESSAGE_LENGTH, FORBIDDEN_WORDS, SPAM_SYMBOLS,
        MESSAGE_INTERVAL_HOURS, LOG_LEVEL
    )
    from src.ai_checker import check_resume_locally
    from src.safe_migrate import safe_migrate
except ImportError:
    try:
        from models import Base, UserMessage
        from config import (
            BOT_TOKEN, CHANNEL_ID, DATABASE_URL,
            MIN_MESSAGE_LENGTH, FORBIDDEN_WORDS, SPAM_SYMBOLS,
            MESSAGE_INTERVAL_HOURS, LOG_LEVEL
        )
        from ai_checker import check_resume_locally
        from safe_migrate import safe_migrate
    except ImportError as e:
        print(f"Ошибка импорта модулей: {e}")
        print("Убедитесь, что вы запускаете бота из корневой директории проекта или из директории src")
        sys.exit(1)

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

# Глобальная очередь сообщений
queue = None

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

async def send_to_queue(username: str, message: str) -> None:
    """
    Отправляет сообщение на проверку.
    В данной реализации проверка выполняется напрямую, без использования очереди.
    
    Args:
        username: Имя пользователя
        message: Текст сообщения для проверки
    """
    logger.info(f"Отправка сообщения пользователя {username} на проверку")
    
    # Запускаем проверку сообщения асинхронно
    asyncio.create_task(check_message_with_neural_net(username, message))

# Расширенная проверка сообщения
async def check_message_with_neural_net(username: str, message: str) -> None:
    """
    Проверяет сообщение с помощью локальной проверки.
    Обновляет статус сообщения в базе данных и отправляет уведомление пользователю.
    
    Args:
        username: Имя пользователя
        message: Текст сообщения для проверки
    """
    logger.info(f"Проверка сообщения пользователя {username}")
    
    try:
        # Используем локальную проверку резюме
        is_approved, check_result = check_resume_locally(message)
        
        async with async_session() as session:
            async with session.begin():
                # Получаем сообщение пользователя из базы данных
                stmt = select(UserMessage).where(UserMessage.username == username)
                result = await session.execute(stmt)
                user_message = result.scalar_one_or_none()
                
                if not user_message:
                    logger.warning(f"Сообщение пользователя {username} не найдено в базе данных")
                    return
                
                # Проверяем, что сообщение не было обновлено после отправки на проверку
                if user_message.message != message:
                    logger.info(f"Сообщение пользователя {username} было обновлено после отправки на проверку. Игнорируем результат проверки.")
                    return
                
                # Обновляем статус сообщения
                user_message.approved = 1 if is_approved else -1
                user_message.check_result = check_result
                
                await session.commit()
        
        # Отправляем уведомление пользователю
        status_text = "Одобрено" if is_approved else "Отклонено"
        notification_text = f"Статус вашего резюме: {status_text}\n\n{check_result}"
        
        if is_approved:
            notification_text += f"\n\nВаше резюме будет отправляться в канал каждые {MESSAGE_INTERVAL_HOURS} часов."
        else:
            notification_text += "\n\nПожалуйста, исправьте указанные проблемы и отправьте резюме снова."
        
        try:
            await bot.send_message(chat_id=f"@{username}", text=notification_text)
            logger.info(f"Уведомление отправлено пользователю {username}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления пользователю {username}: {e}")
            # Если не удалось отправить сообщение напрямую, сохраняем результат проверки
            # Пользователь сможет увидеть его через команду /status
            logger.info(f"Результат проверки сохранен в базе данных для пользователя {username}")
    
    except Exception as e:
        logger.error(f"Ошибка при проверке сообщения пользователя {username}: {e}")
        
        # В случае ошибки сохраняем информацию об ошибке в базе данных
        async with async_session() as session:
            async with session.begin():
                stmt = select(UserMessage).where(UserMessage.username == username)
                result = await session.execute(stmt)
                user_message = result.scalar_one_or_none()
                
                if user_message:
                    user_message.approved = -1
                    user_message.check_result = f"❌ Произошла ошибка при проверке резюме: {str(e)}"
                    await session.commit()

async def schedule_message_sending(username: str) -> None:
    """
    Планирует отправку сообщения в канал.
    Проверяет, одобрено ли сообщение, и если да, планирует его отправку.
    
    Args:
        username: Имя пользователя
    """
    logger.info(f"Планирование отправки сообщения для пользователя {username}")
    
    async with async_session() as session:
        async with session.begin():
            # Получаем сообщение пользователя из базы данных
            stmt = select(UserMessage).where(UserMessage.username == username)
            result = await session.execute(stmt)
            user_message = result.scalar_one_or_none()
            
            if not user_message:
                logger.warning(f"Сообщение пользователя {username} не найдено в базе данных")
                return
            
            # Проверяем, одобрено ли сообщение
            if user_message.approved != 1:
                logger.info(f"Сообщение пользователя {username} не одобрено, отправка не планируется")
                return
            
            # Проверяем, когда сообщение было отправлено в последний раз
            current_time = datetime.now()
            
            if user_message.last_sent:
                time_since_last_sent = current_time - user_message.last_sent
                hours_since_last_sent = time_since_last_sent.total_seconds() / 3600
                
                if hours_since_last_sent < MESSAGE_INTERVAL_HOURS:
                    logger.info(f"Сообщение пользователя {username} было отправлено менее {MESSAGE_INTERVAL_HOURS} часов назад, отправка не планируется")
                    return
            
            # Отправляем сообщение в канал
            try:
                # Формируем сообщение для отправки в канал
                channel_message = f"📝 Резюме от @{username}:\n\n{user_message.message}"
                
                await bot.send_message(chat_id=CHANNEL_ID, text=channel_message)
                logger.info(f"Сообщение пользователя {username} отправлено в канал")
                
                # Обновляем время последней отправки
                user_message.last_sent = current_time
                await session.commit()
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения пользователя {username} в канал: {e}")

@dp.message(Command("start"))
async def start_command(message: types.Message):
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 Я бот для отправки резюме в канал.\n\n"
        "📝 Просто отправь мне текст своего резюме с хэштегом #резюме, и я проверю его на соответствие правилам.\n"
        "✅ Если резюме пройдет проверку, оно будет отправляться в канал каждые "
        f"{MESSAGE_INTERVAL_HOURS} часов.\n\n"
        "⚠️ Важно: Ваше резюме должно содержать:\n"
        "- Хэштег #резюме\n"
        "- Не менее 20 слов\n"
        "- Информацию как минимум о двух из следующих разделов: опыт работы, образование, навыки, контакты\n\n"
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
    # Убираем символ @ из username, если он есть
    if username.startswith('@'):
        username = username[1:]
    
    async with async_session() as session:
        stmt = select(UserMessage).where(UserMessage.username == username)
        result = await session.execute(stmt)
        user_msg = result.scalar_one_or_none()
        
        if not user_msg:
            await message.answer("❌ У вас нет активных сообщений. Отправьте сообщение для проверки.")
            return
        
        status_text = "📊 Статус вашего сообщения:\n\n"
        
        # Ограничиваем длину сообщения для отображения
        message_preview = user_msg.message[:100] + "..." if len(user_msg.message) > 100 else user_msg.message
        status_text += f"📝 Сообщение: {message_preview}\n\n"
        
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
        "2. Бот проверит резюме на соответствие правилам\n"
        "3. Если резюме одобрено, оно будет отправлено в канал\n"
        "4. Одобренные резюме будут отправляться в канал каждые "
        f"{MESSAGE_INTERVAL_HOURS} часов\n\n"
        "❗ Требования к резюме:\n"
        "- Резюме должно содержать хэштег #резюме\n"
        "- Резюме должно содержать не менее 20 слов\n"
        "- Резюме должно содержать информацию как минимум о двух из следующих разделов: опыт работы, образование, навыки, контакты\n\n"
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
    
    # Получаем username пользователя
    username = message.from_user.username or str(message.from_user.id)
    # Убираем символ @ из username, если он есть
    if username.startswith('@'):
        username = username[1:]
    
    user_message = message.text
    
    if len(user_message) <= 5:
        await message.answer("❌ Сообщение слишком короткое. Минимальная длина - 6 символов.")
        return
    
    # Проверяем наличие хэштега #резюме
    if "#резюме" not in user_message.lower():
        await message.answer(
            "❌ Сообщение не содержит хэштег #резюме. Пожалуйста, добавьте хэштег #резюме в ваше сообщение.\n\n"
            "Пример правильного резюме:\n\n"
            "#резюме\n\n"
            "Опыт работы: 3 года в разработке ПО\n"
            "Образование: Высшее техническое\n"
            "Навыки: Python, JavaScript, SQL\n"
            "Контакты: email@example.com, @username\n\n"
            "Важно: Ваше резюме должно содержать как минимум два из следующих разделов:\n"
            "- Опыт работы\n"
            "- Образование\n"
            "- Навыки\n"
            "- Контакты\n\n"
            "Ключевые слова, которые помогут системе распознать разделы:\n"
            "- Опыт: опыт, стаж, работал, работаю, лет опыта, занимался, делал\n"
            "- Образование: образование, учился, окончил, диплом, курсы, учеба\n"
            "- Навыки: навыки, умения, владею, знаю, работаю с, использую, умею\n"
            "- Контакты: контакты, связь, телефон, email, почта, @, тг"
        )
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
            "Вы получите результат проверки через команду /status.\n"
            f"Если сообщение будет одобрено, оно будет отправляться в канал каждые {MESSAGE_INTERVAL_HOURS} часов."
        )
    else:
        await message.answer(
            "⏳ Сообщение отправлено на проверку!\n\n"
            "Вы можете проверить статус через команду /status.\n"
            f"Если сообщение будет одобрено, оно будет отправляться в канал каждые {MESSAGE_INTERVAL_HOURS} часов."
        )

async def main():
    """Основная функция запуска бота."""
    # Инициализируем базу данных
    await init_db()
    
    # Запускаем планировщик
    scheduler.start()
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main())