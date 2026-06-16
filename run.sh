#!/bin/bash

# XBalanseBot Lifecycle Manager for macOS
echo "================================="
echo "XBalanseBot Lifecycle Manager"
echo "Date: $(date)"
python3 --version 2>/dev/null || python --version
echo "Working Directory: $(pwd)"
echo "================================="
echo ""

# --- Шаг 1: Запуск PostgreSQL и Redis в Docker ---
echo "[+] Starting containers via Docker Compose..."
docker-compose up -d
if [ $? -ne 0 ]; then
    echo ""
    echo "[!!!] CRITICAL ERROR: Failed to start Docker containers."
    echo "    Please check if Docker Desktop is running and docker-compose.yml is correct."
    exit 1
fi
echo "    Done."
echo ""

# --- Шаг 2: Запуск основного скрипта бота ---
echo "================================="
echo "[+] Starting the bot..."
echo "[i] To stop the bot AND the database, press Ctrl+C in this window."
echo "================================="
echo ""

# Проверяем, какой способ запуска использовать:
if [ -d ".venv" ]; then
    echo "[i] Using local virtual environment (.venv)..."
    .venv/bin/python main.py
elif command -v poetry &> /dev/null; then
    echo "[i] Using poetry run..."
    poetry run python main.py
else
    echo "[i] Using system python..."
    python3 main.py || python main.py
fi

# Если python-скрипт завершился с ошибкой:
if [ $? -ne 0 ]; then
    echo ""
    echo "[!!!] CRITICAL ERROR: Python script exited with an error."
    echo ""
    echo "[+] Attempting to shut down Docker containers..."
    docker-compose down
fi

echo ""
echo "[+] Bot script has finished."
