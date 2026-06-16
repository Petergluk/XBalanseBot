#!/bin/bash

# XBalanseBot Test Runner for macOS
echo "================================="
echo "XBalanseBot Test Runner"
echo "Date: $(date)"
echo "================================="
echo ""

# --- Шаг 1: Проверка наличия .env файла ---
if [ ! -f .env ]; then
    echo "[!!!] CRITICAL ERROR: .env file not found in the current directory."
    exit 1
fi

# --- Шаг 2: Запуск контейнеров в Docker ---
echo "[+] Starting Docker containers..."
docker-compose up -d
if [ $? -ne 0 ]; then
    echo ""
    echo "[!!!] CRITICAL ERROR: Failed to start Docker containers."
    echo "    Please check if Docker Desktop is running."
    exit 1
fi
echo "    Done."
echo ""

# --- Шаг 3: Запуск Pytest ---
echo "================================="
echo "[+] Running tests..."
echo "================================="
echo ""

# Запускаем pytest через .venv или poetry
if [ -d ".venv" ]; then
    .venv/bin/pytest -v
elif command -v poetry &> /dev/null; then
    poetry run pytest -v
else
    pytest -v
fi

TEST_EXIT_CODE=$?

# --- Шаг 4: Остановка Docker ---
echo ""
echo "================================="
echo "[+] Shutting down Docker containers..."
echo "================================="
docker-compose down
echo "    Done."

exit $TEST_EXIT_CODE
