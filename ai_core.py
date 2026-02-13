# ai_core.py

from openai import OpenAI
from typing import List, Dict, Tuple
from dotenv import load_dotenv
import os
import logging
import asyncio 
import json
import re
from openai import AuthenticationError

load_dotenv()
logger = logging.getLogger(__name__)

openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logger.error("❌ OPENAI_API_KEY не найден в .env файле!")
    raise ValueError("OPENAI_API_KEY не найден в .env файле!")

client = OpenAI(api_key=openai_api_key)

# --- СТРУКТУРА ДАННЫХ ---
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "response_text": {
            "type": "string",
            "description": "Краткий ответ клиенту."
        },
        "qualification_status": {
            "type": "string",
            "description": "Статус: 'COLD', 'WARM', 'HOT', 'HANDOVER'."
        },
        "reasoning": {
            "type": "string",
            "description": "Обоснование."
        }
    },
    "required": ["response_text", "qualification_status", "reasoning"]
}

# --- СИСТЕМНАЯ ИНСТРУКЦИЯ ---
SYSTEM_PROMPT = f"""
Ты — профессиональный ассистент, помогающий сотрудникам и бывшим сотрудникам актуализировать данные для оцифровки трудовых книг в электронный архив СФР.

ПРАВИЛА:
1. Если это ПЕРВОЕ сообщение, представься: "Привет! Я ассистент по актуализации данных для оцифровки трудовых книжек."
2. Если клиент пишет "не работаю", объясни важность для пенсии и стажа.
3. Ссылка на бот: http://t.me/socfond_checker_bot (ВНИМАНИЕ: используй ТОЛЬКО эту ссылку).
4. Если клиент прислал ключ (6 цифр) -> HOT.
5. Не повторяй приветствие.

Отвечай JSON.
{json.dumps(RESPONSE_SCHEMA, indent=2)}
"""

AI_MODEL = "gpt-4o-mini"

async def get_ai_response(chat_history: List[Dict[str, str]]) -> Tuple[str, Dict]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    
    for message in chat_history:
        role = message.get('role')
        text = message.get('text')
        if role and text:
            messages.append({"role": role, "content": text}) 

    logger.info(f"Отправка {len(messages)} сообщений в AI...")

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create, 
            model=AI_MODEL,
            messages=messages,
            response_format={"type": "json_object"}, 
            temperature=0.7 
        )
        
        json_output = response.choices[0].message.content
        
        try:
            data = json.loads(json_output)
            ai_text = data.get('response_text', 'Ошибка.')
            # Удаление приветствия
            greetings = ["Здравствуйте!", "Привет!", "Добрый день"]
            if len(chat_history) > 1: # Если это не первое сообщение
                 for g in greetings:
                     if ai_text.startswith(g):
                         ai_text = ai_text[len(g):].strip()
            return ai_text, data
        except json.JSONDecodeError:
            return "Ошибка чтения ответа AI.", {"qualification_status": "ERROR"}
        
    except Exception as e:
        logger.error(f"Ошибка AI: {e}")
        return "Ошибка сервиса.", {"qualification_status": "ERROR"}