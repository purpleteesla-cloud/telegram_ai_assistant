# api_gateway.py

import logging
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import asyncpg
from dotenv import load_dotenv
import requests 
from typing import List, Dict, Tuple, Optional # <<< Добавили Optional
from contextlib import asynccontextmanager
import sys
import json
import html
import re
import asyncio

from ai_core import get_ai_response 

# --- 1. Настройка ---

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 2. Инициализация ---

db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    logger.info("Попытка подключения к базе данных...")
    try:
        db_pool = await asyncpg.create_pool(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            min_size=1,
            max_size=10
        )
        logger.info("Успешное подключение к PostgreSQL и создание пула.")
    except Exception as e:
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к БД! Ошибка: {e}")
        sys.exit(1)
        
    yield 

    if db_pool:
        await db_pool.close()
        logger.info("Пул соединений с БД закрыт.")


app = FastAPI(
    title="AI Sales Lead Gatekeeper",
    description="API для приема новых ответов от холодной базы и передачи в AI.",
    version="1.0.0",
    lifespan=lifespan
)


# --- 3. Обновленная модель данных ---
class NewLeadMessage(BaseModel):
    user_id: int              
    chat_id: int              
    sender_account_id: int    
    received_message: str     
    username: Optional[str] = None # <<< ПОЛЕ ДЛЯ USERNAME
    timestamp: int | None = None 


# --- 4. Функции БД ---

async def get_chat_history(user_id: int) -> List[Dict[str, str]]:
    if not db_pool: return []
    
    async with db_pool.acquire() as conn:
        record = await conn.fetchrow(
            "SELECT chat_history FROM leads_sessions WHERE user_id = $1", user_id
        )
        
        if record and 'chat_history' in record and record['chat_history'] is not None:
             chat_data = record['chat_history']
             
             if isinstance(chat_data, str):
                 try:
                     return json.loads(chat_data)
                 except json.JSONDecodeError:
                     logger.error("Ошибка декодирования chat_history из строки JSON.", exc_info=True)
                     return []
             
             if isinstance(chat_data, list):
                 return chat_data
                 
        return []


async def update_chat_history(user_id: int, message: str, role: str = 'user'):
    if not db_pool: return 

    new_entry = {"role": role, "text": message} 

    async with db_pool.acquire() as conn:
        update_query = """
            UPDATE leads_sessions
            SET 
                chat_history = chat_history || $1::jsonb,
                last_update = NOW()
            WHERE user_id = $2
        """
        result = await conn.execute(update_query, json.dumps([new_entry]), user_id)
        
        if result == "UPDATE 0":
            insert_query = """
                INSERT INTO leads_sessions (user_id, status, chat_history)
                VALUES ($1, 'AI_ACTIVE', $2::jsonb)
            """
            await conn.execute(insert_query, user_id, json.dumps([new_entry]))
            logger.info(f"Создана НОВАЯ сессия для лида {user_id}")


async def update_lead_status(user_id: int, status: str):
    if not db_pool: return
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE leads_sessions SET status = $1 WHERE user_id = $2", 
            status, user_id
        )

OPERATOR_CHAT_ID = os.getenv("OPERATOR_CHAT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def escape_html(text: str) -> str:
    if text:
        return html.escape(str(text))
    return ""

# --- ОБНОВЛЕННАЯ ФУНКЦИЯ УВЕДОМЛЕНИЯ ---
async def notify_operator(chat_id: int, received_message: str, ai_response_text: str, username: str = None):
    if not OPERATOR_CHAT_ID or not TELEGRAM_BOT_TOKEN:
        logger.error("Не настроены переменные для уведомления оператора.")
        return

    safe_ai_response = escape_html(ai_response_text)
    safe_chat_id = escape_html(str(chat_id))
    
    # Формируем ссылку на пользователя
    if username:
        user_link = f"@{escape_html(username)}"
    else:
        user_link = "Не указан (скрыт)"

    notification_message = (
        f"🚨 <b>HOT ЛИД! СРОЧНО ПЕРЕХВАТ!</b> 🚨\n\n"
        f"<b>ID Лида:</b> <code>{safe_chat_id}</code>\n"
        f"<b>Username:</b> {user_link}\n" # <<< ДОБАВИЛИ СЮДА
        f"<b>Последний запрос:</b> <i>{escape_html(received_message)}</i>\n" 
        f"<b>Ответ AI:</b> {safe_ai_response}"
    )

    telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': OPERATOR_CHAT_ID,
        'text': notification_message,
        'parse_mode': 'HTML'
    }

    try:
        response = await asyncio.to_thread(requests.post, telegram_api_url, data=payload)
        response.raise_for_status()
        logger.warning(f"Уведомление о HOT-лиде {chat_id} (@{username}) отправлено оператору.")
    except Exception as e:
        logger.error(f"Критическая ошибка отправки уведомления: {e}")


# --- 5. Основная Конечная Точка ---
@app.post("/new_reply")
async def handle_new_reply(data: NewLeadMessage):
    logger.info(f"Получено сообщение от {data.user_id} (@{data.username}): {data.received_message[:50]}...")

    try:
        # 1. ПРОВЕРКА НА 6-ЗНАЧНЫЙ КЛЮЧ (HOT)
        match = re.search(r'\b\d{6}\b', data.received_message.strip())
        
        if match:
            q_status = "HOT"
            ai_response_text = "Спасибо! Ваш ключ зафиксирован. Ожидайте подтверждения от специалиста."
            
            await update_chat_history(data.user_id, data.received_message, role='user')
            await update_chat_history(data.user_id, ai_response_text, role='assistant')
            # Передаем username в уведомление
            await notify_operator(data.chat_id, data.received_message, ai_response_text, data.username)
            await update_lead_status(data.user_id, q_status)
            
            return {
                "status": "success",
                "message": "AI successfully detected 6-digit key.",
                "response_text": ai_response_text,
                "qualification_status": q_status
            }

        # 2. ОБЫЧНЫЙ ДИАЛОГ С AI
        
        full_history = await get_chat_history(data.user_id)
        
        # Если это начало диалога (пришла пустая команда старт от бота)
        if data.received_message == "START_DIALOG_FROM_COMMAND":
             pass
        else:
             full_history.append({"role": 'user', "text": data.received_message})
        
        ai_response_text, qualification_data = await get_ai_response(full_history)
        
        if data.received_message != "START_DIALOG_FROM_COMMAND":
             await update_chat_history(data.user_id, data.received_message, role='user')
        
        await update_chat_history(data.user_id, ai_response_text, role='assistant')
        
        q_status = qualification_data.get('qualification_status', 'COLD')
        
        if q_status == "HOT":
            # Передаем username в уведомление
            await notify_operator(data.chat_id, data.received_message, ai_response_text, data.username)
            await update_lead_status(data.user_id, q_status)
        else:
            logger.info(f"Лид {data.user_id} квалифицирован как {q_status}. Продолжаем диалог.")
            await update_lead_status(data.user_id, "AI_ACTIVE")
        
        return {
            "status": "success", 
            "message": f"AI response generated. Qualification: {q_status}",
            "response_text": ai_response_text 
        }

    except Exception as e:
        logger.error(f"Критическая ошибка при обработке лида {data.user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal AI processing error.")


@app.on_event("startup")
async def startup_event():
    logger.info("Запуск сервера...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Остановка сервера...")

if __name__ == "__main__":
    uvicorn.run("api_gateway:app", host="0.0.0.0", port=8000)