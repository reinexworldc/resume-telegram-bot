import logging
import aiohttp
import json

# Пытаемся импортировать как модуль, если не получается - используем относительные пути
try:
    from src import config
except ImportError:
    import config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_resume_with_ai(message: str) -> tuple[bool, str]:
    """
    Проверяет резюме с помощью DeepSeek AI.
    
    Args:
        message: Текст сообщения для проверки
        
    Returns:
        Tuple[bool, str]: (одобрено ли резюме, отчет о проверке)
    """
    # Проверяем наличие хэштега #резюме
    if "#резюме" not in message.lower():
        return False, "❌ Сообщение не содержит хэштег #резюме. Пожалуйста, добавьте хэштег #резюме в ваше сообщение."
    
    # Формируем запрос к DeepSeek AI
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
        "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"
    }
    
    payload = {
        "model": config.DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "Ты - помощник по проверке резюме. Твоя задача - проверять резюме на орфографию, грамматику, структуру и содержание."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(config.DEEPSEEK_API_URL, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ошибка API DeepSeek: {response.status} - {error_text}")
                    return False, f"❌ Ошибка при проверке резюме: {response.status}"
                
                result = await response.json()
                ai_response = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Анализируем ответ AI
                is_approved = "одобрено: да" in ai_response.lower() or "резюме одобрено" in ai_response.lower()
                
                # Форматируем отчет
                report = f"📋 Отчет проверки резюме:\n\n{ai_response}"
                
                return is_approved, report
                
    except Exception as e:
        logger.error(f"Ошибка при обращении к DeepSeek AI: {str(e)}")
        return False, f"❌ Произошла ошибка при проверке резюме: {str(e)}" 