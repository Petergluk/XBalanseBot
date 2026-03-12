# Stage 1: Build
FROM python:3.13.4-slim AS builder

# Исключаем создание __pycache__ и .pyc файлов
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Устанавливаем poetry
RUN pip install poetry==2.1.3

# Копируем файлы зависимостей
COPY pyproject.toml ./

# Создаем виртуальное окружение и устанавливаем зависимости без lock проверки
RUN poetry config virtualenvs.in-project true && \
    poetry lock && \
    poetry install --only main --no-root --no-interaction --no-ansi

# Stage 2: Runtime
FROM python:3.13.4-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Копируем только виртуальное окружение из предыдущего билда
COPY --from=builder /app/.venv /app/.venv

# Копируем исходный код
COPY . .

# Добавляем .venv/bin в PATH
ENV PATH="/app/.venv/bin:$PATH"

# При запуске применяем миграции и стартуем бота
CMD ["sh", "-c", "alembic upgrade head && python main.py"]
