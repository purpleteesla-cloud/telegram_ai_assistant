# telegram_bot.py

import logging
import os
from telegram import Update
from telegram.ext import (
    Application, 
    MessageHandler, 
    filters, 
    ContextTypes,
    CommandHandler
)
from telegram.constants import ParseMode 
from dotenv import load_dotenv
import httpx
import html
import json

# --- 1. Настройка и Загрузка переменных ---
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Константы ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_GATEWAY_URL = "http://127.0.0.1:8000/new_reply" 

if not BOT_TOKEN:
    logger.error("КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN не найден в .env")
    exit(1)

def escape_html(text: str) -> str:
    if text:
        return html.escape(str(text))
    return ""

# --- 2. Обработчик команд ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /start. 
    Передает команду в AI, чтобы тот представился сам.
    """
    await handle_message(update, context)


# --- 3. Обработчик сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message.text is None:
        return 
        
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username # <<< ИЗВЛЕКАЕМ USERNAME
    received_message = update.effective_message.text
    
    logger.info(f"Сообщение от {user_id} (@{username}): {received_message[:50]}...")

    payload = {
        "user_id": user_id, 
        "chat_id": chat_id, 
        "sender_account_id": user_id, 
        "received_message": received_message,
        "username": username # <<< ДОБАВЛЯЕМ В ЗАПРОС
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(API_GATEWAY_URL, json=payload)
            response.raise_for_status() 

            api_data = response.json()
            ai_response_text = api_data.get("response_text", "Извините, произошла внутренняя ошибка AI.")
            qualification_status = api_data.get("qualification_status")
            
        await update.effective_message.reply_text(ai_response_text)
        
        logger.info(f"Ответ AI отправлен (Квалификация: {qualification_status}).")

    except Exception as e:
        logger.error(f"Непредвиденная ошибка в обработчике Telegram: {e}")

# --- 4. Главная функция ---
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен. Начните общение в Telegram!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()