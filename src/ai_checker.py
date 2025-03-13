import logging
import aiohttp
import json
import re
import sys
import os

# Добавляем родительскую директорию в sys.path для корректного импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Пытаемся импортировать как модуль, если не получается - используем относительные пути
try:
    from src import config
except ImportError:
    try:
        import config
    except ImportError as e:
        print(f"Ошибка импорта модуля config: {e}")
        print("Убедитесь, что вы запускаете бота из корневой директории проекта или из директории src")
        sys.exit(1)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_resume_locally(message: str) -> tuple[bool, str]:
    """
    Локальная проверка резюме без использования внешних API.
    Проверяет наличие хэштега #резюме и основных разделов резюме.
    Использует очень лояльные критерии проверки.
    
    Args:
        message: Текст сообщения для проверки
        
    Returns:
        Tuple[bool, str]: (Одобрено/Отклонено, Результат проверки)
    """
    message_lower = message.lower()
    
    # Проверка наличия хэштега #резюме
    if "#резюме" not in message_lower:
        return False, "❌ Резюме отклонено: отсутствует хэштег #резюме"
    
    # Словарь разделов резюме и ключевых слов для их определения
    resume_sections = {
        "опыт": ["опыт", "стаж", "работал", "работаю", "лет опыта", "работа", "должность", "компания", "проект", "занимался", "делал"],
        "образование": ["образование", "учился", "окончил", "диплом", "курсы", "университет", "институт", "школа", "колледж", "вуз", "степень", "учеба"],
        "навыки": ["навыки", "умения", "владею", "знаю", "работаю с", "использую", "технологии", "инструменты", "языки", "фреймворки", "библиотеки", "умею"],
        "контакты": ["контакты", "связь", "телефон", "email", "почта", "@", "telegram", "вконтакте", "linkedin", "тг", "связаться", "номер"]
    }
    
    # Проверка наличия основных разделов
    found_sections = set()
    missing_sections = []
    
    for section, keywords in resume_sections.items():
        for keyword in keywords:
            if keyword in message_lower:
                found_sections.add(section)
                break
        
        if section not in found_sections:
            missing_sections.append(section)
    
    # Проверка минимальной длины резюме - снижаем требование до 20 слов
    if len(message.split()) < 20:
        return False, "❌ Резюме отклонено: слишком короткое описание. Резюме должно содержать не менее 20 слов."
    
    # Если найдено менее 2 разделов, считаем резюме неполным (снижаем с 3 до 2)
    if len(found_sections) < 2:
        missing_sections_str = ", ".join(missing_sections)
        return False, f"❌ Резюме отклонено: недостаточно информации. Рекомендуется добавить следующие разделы: {missing_sections_str}."
    
    # Если найдены не все разделы, но достаточно для одобрения, даем рекомендации
    if missing_sections:
        missing_sections_str = ", ".join(missing_sections)
        return True, f"✅ Резюме одобрено! Для улучшения рекомендуется добавить: {missing_sections_str}."
    
    return True, "✅ Резюме одобрено! Все необходимые разделы присутствуют."

async def check_resume_with_ai(message: str) -> tuple[bool, str]:
    """
    Проверяет резюме с помощью X.AI (Grok).
    
    Args:
        message: Текст сообщения для проверки
        
    Returns:
        Tuple[bool, str]: (одобрено ли резюме, отчет о проверке)
    """
    # Проверяем наличие хэштега #резюме
    if "#резюме" not in message.lower():
        return False, "❌ Сообщение не содержит хэштег #резюме. Пожалуйста, добавьте хэштег #резюме в ваше сообщение."
    
    # Формируем запрос к X.AI
    prompt = f"""
    Проверь следующее резюме на соответствие критериям:
    1. Орфография и грамматика (исправь ошибки, если они есть)
    2. Структура и содержание (предложи улучшения, если необходимо)
    3. Проверь, что это действительно резюме и содержит хэштег #резюме
    
    Резюме для проверки:
    {message}
    
    Дай подробный отчет о проверке и укажи, одобрено ли резюме (да/нет).
    Если резюме не одобрено, объясни причины и дай рекомендации по исправлению.
    """
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.GROK_API_KEY}"
    }
    
    payload = {
        "model": config.GROK_MODEL,
        "messages": [
            {"role": "system", "content": "Ты - помощник по проверке резюме. Твоя задача - проверять резюме на орфографию, грамматику, структуру и содержание."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "stream": False
    }
    
    logger.info(f"Отправляю запрос к X.AI API. URL: {config.GROK_API_URL}, Модель: {config.GROK_MODEL}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(config.GROK_API_URL, headers=headers, json=payload) as response:
                response_text = await response.text()
                logger.info(f"Получен ответ от X.AI API. Статус: {response.status}")
                
                if response.status != 200:
                    logger.error(f"Ошибка X.AI API: {response.status} - {response_text}")
                    
                    # Если API недоступен, используем локальную проверку
                    logger.info("Использую локальную проверку резюме из-за недоступности API")
                    return check_resume_locally(message)
                
                try:
                    result = json.loads(response_text)
                    ai_response = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    logger.info(f"Успешно получен ответ от X.AI. Длина ответа: {len(ai_response)} символов")
                    
                    # Анализируем ответ AI
                    is_approved = "одобрено: да" in ai_response.lower() or "резюме одобрено" in ai_response.lower()
                    
                    # Форматируем отчет
                    report = f"📋 Отчет проверки резюме:\n\n{ai_response}"
                    
                    return is_approved, report
                except Exception as parse_error:
                    logger.error(f"Ошибка при разборе ответа X.AI: {str(parse_error)}. Ответ: {response_text[:200]}...")
                    # Если не удалось разобрать ответ, используем локальную проверку
                    logger.info("Использую локальную проверку резюме из-за ошибки разбора ответа API")
                    return check_resume_locally(message)
                
    except aiohttp.ClientError as client_error:
        logger.error(f"Ошибка соединения с X.AI: {str(client_error)}")
        # Если не удалось соединиться с API, используем локальную проверку
        logger.info("Использую локальную проверку резюме из-за ошибки соединения с API")
        return check_resume_locally(message)
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при обращении к X.AI: {str(e)}")
        # При любой другой ошибке используем локальную проверку
        logger.info("Использую локальную проверку резюме из-за непредвиденной ошибки")
        return check_resume_locally(message) 