import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine
from models import Base
from config import DATABASE_URL

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка базы данных
engine = create_async_engine(DATABASE_URL)

async def migrate_db():
    """
    Пересоздает таблицы в базе данных.
    ВНИМАНИЕ: Это удалит все существующие данные!
    """
    try:
        logger.info("Начинаю миграцию базы данных...")
        
        async with engine.begin() as conn:
            # Удаляем существующие таблицы
            logger.info("Удаляю существующие таблицы...")
            await conn.run_sync(Base.metadata.drop_all)
            
            # Создаем новые таблицы
            logger.info("Создаю новые таблицы...")
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Миграция базы данных успешно завершена!")
    except Exception as e:
        logger.error(f"Ошибка при миграции базы данных: {e}")
        raise

async def check_db():
    """
    Проверяет структуру базы данных без изменений.
    """
    try:
        logger.info("Проверяю структуру базы данных...")
        
        # Получаем информацию о таблицах
        async with engine.connect() as conn:
            # Проверяем наличие таблицы user_messages
            from sqlalchemy import text
            result = await conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_messages')"))
            exists = result.scalar()
            
            if exists:
                logger.info("Таблица user_messages существует")
                
                # Проверяем наличие колонки id
                result = await conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'user_messages' AND column_name = 'id')"))
                has_id = result.scalar()
                
                if has_id:
                    logger.info("Колонка id существует в таблице user_messages")
                else:
                    logger.warning("Колонка id НЕ существует в таблице user_messages! Требуется миграция.")
            else:
                logger.warning("Таблица user_messages НЕ существует! Требуется миграция.")
        
        logger.info("Проверка структуры базы данных завершена")
    except Exception as e:
        logger.error(f"Ошибка при проверке базы данных: {e}")
        raise

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        # Только проверка без миграции
        asyncio.run(check_db())
    else:
        # Запрос подтверждения перед миграцией
        confirm = input("Вы собираетесь пересоздать все таблицы в базе данных. Все данные будут удалены! Продолжить? (y/n): ")
        
        if confirm.lower() == 'y':
            asyncio.run(migrate_db())
        else:
            print("Миграция отменена.") 