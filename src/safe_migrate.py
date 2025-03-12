import asyncio
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from config import DATABASE_URL

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка базы данных
engine = create_async_engine(DATABASE_URL)

async def safe_migrate():
    """
    Безопасно добавляет новое поле last_update в таблицу user_messages без потери данных.
    """
    try:
        logger.info("Начинаю безопасную миграцию базы данных...")
        
        async with engine.begin() as conn:
            # Проверяем наличие колонки last_update
            result = await conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'user_messages' AND column_name = 'last_update')"))
            has_last_update = result.scalar()
            
            if has_last_update:
                logger.info("Колонка last_update уже существует в таблице user_messages")
            else:
                logger.info("Добавляю колонку last_update в таблицу user_messages...")
                # Добавляем колонку last_update с текущим временем в качестве значения по умолчанию
                await conn.execute(text("ALTER TABLE user_messages ADD COLUMN last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                logger.info("Колонка last_update успешно добавлена")
        
        logger.info("Безопасная миграция базы данных успешно завершена!")
    except Exception as e:
        logger.error(f"Ошибка при безопасной миграции базы данных: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(safe_migrate()) 