FROM python:3.10-slim

WORKDIR /app

# Устанавливаем зависимости из твоего requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все исходники: api_gateway.py, telegram_bot.py, rag_processor_final.py и т.д.
COPY . .

# Оставляем CMD пустым или дефолтным, так как compose его переопределит
CMD ["python", "api_gateway.py"]