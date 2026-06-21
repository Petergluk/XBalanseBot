# Руководство по Развёртыванию XBalanseBot

## Требования

### Минимальные

- Python 3.13.4+
- PostgreSQL 14+
- Redis 6+ (опционально для dev)
- Docker 20+ (рекомендуется)

### Для Продакшена

| Ресурс | Минимум | Рекомендовано | Комфорт (1000+ пользователей) |
|--------|---------|---------------|-------------------------------|
| **RAM** | 256 MB | 512 MB | 1 GB |
| **Disk** | 512 MB | 1 GB | 2-5 GB |
| **CPU** | 0.1 vCPU | 0.25 vCPU | 0.5-1 vCPU |

**Примечания:**

- **512 MB диск:** Хватит на ~1-2 месяца (код ~200MB + логи + БД ~50MB)
- **1 GB диск:** Запас на 6-12 месяцев без беспокойства
- **Логи:** Могут расти на 10-50 MB/месяц в зависимости от активности
- **БД:** ~10-50 MB для 1000-5000 пользователей (транзакции + пользователи)
- **Docker overlay:** +50-100 MB накладных расходов

---

## Локальная Разработка


1. Как перезапустить локальную версию?
Если бот запущен через Docker Compose (рекомендуется): Для перезапуска с пересборкой (чтобы применились все наши изменения в Python-файлах) выполните в терминале Mac:

```bash
docker compose down && docker compose up -d --build
```

Если нужно просто перезапустить контейнеры без пересборки:

```bash
docker compose restart
```

Если запускаете вручную через Python/Poetry: Остановите текущий процесс в терминале нажатием Ctrl + C и запустите заново:

```bash
poetry run python main.py
```bash

если активировано виртуальное окружение:
```bash
python main.py
```

### 1. Клонирование

```bash
git clone https://github.com/Petergluk/XBalanseBot.git
cd XBalanseBot
```

### 2. Установка Зависимостей

```bash
# Создание виртуального окружения
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Установка Poetry (если не установлен)
curl -sSL https://install.python-poetry.org | python3 -

# Установка зависимостей
poetry install
```

### 3. Настройка Переменных Окружения

Создайте файл `.env` в корне проекта:

```bash
# Telegram Bot
BOT_TOKEN=your_bot_token_from_botfather
MAIN_GROUP_ID=-1001234567890
SUPER_ADMIN_ID=123456789

# Database (локальная)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=xbalansebot
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password

# Redis (опционально)
REDIS_HOST=localhost
REDIS_URL=redis://localhost:6379/0

# Webhook (для прода)
WEBHOOK_HOST=your-domain.com
WEBHOOK_SECRET_TOKEN=your_secret_token

# Tribute (опционально)
TRIBUTE_WEBHOOK_SECRET=your_tribute_secret

# Режим разработки
DEV_MODE=True
```

### 4. Запуск Базы Данных (Docker)

```bash
docker run -d \
  --name xbalansebot-postgres \
  -e POSTGRES_DB=xbalansebot \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=your_password \
  -p 5432:5432 \
  postgres:15

docker run -d \
  --name xbalansebot-redis \
  -p 6379:6379 \
  redis:7-alpine
```

### 5. Применение Миграций

```bash
poetry run alembic upgrade head
```

### 6. Запуск Бота

```bash
# Режим разработки (polling)
poetry run python main.py

# Или через Docker Compose
docker-compose up --build
```

---

## Docker Compose (Локальный Продакшен)

### `docker-compose.yml`

```yaml
version: '3.8'

services:
  bot:
    build: .
    ports:
      - "8080:8080"
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - DATABASE_URL=postgresql://postgres:password@db:5432/xbalansebot
      - REDIS_URL=redis://redis:6379/0
      - DEV_MODE=False
      - WEBHOOK_HOST=${WEBHOOK_HOST}
    depends_on:
      - db
      - redis
    restart: unless-stopped

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=xbalansebot
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### Запуск

```bash
docker-compose up -d
docker-compose logs -f bot
```

---

## Деплой на Koyeb

### 1. Подготовка

1. Forkните репозиторий на GitHub
2. **ВАЖНО:** Удалите секреты из `koyeb.yaml` перед пушем!

```bash
# Очистите koyeb.yaml от реальных значений
git rm --cached koyeb.yaml
echo "koyeb.yaml" >> .gitignore
git commit -m "Remove secrets from version control"
```

### 2. Настройка в Koyeb Panel

1. Создайте новый сервис типа **Web**
2. Выберите **Git** как источник
3. Подключите GitHub репозиторий
4. Выберите ветку `master`

### 3. Конфигурация Сервиса

```yaml
# Builder
Builder: Docker
Dockerfile: Dockerfile

# Ports
Port: 8080
Protocol: HTTP

# Scaling
Min instances: 0 (для free tier)
Max instances: 1

# Region
Region: was (Washington D.C.) или fra (Frankfurt)

# Instance Type
Type: free (или eco-nano для прода)
```

### 4. Переменные Окружения (Koyeb Secrets)

В панели Koyeb добавьте secrets:

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | Токен от @BotFather |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `MAIN_GROUP_ID` | ID основной группы |
| `SUPER_ADMIN_ID` | Ваш Telegram ID |
| `WEBHOOK_HOST` | `your-app.koyeb.app` |
| `DEV_MODE` | `False` |

### 5. Деплой

```bash
git push origin master
```

Koyeb автоматически запустит сборку и деплой.

---

## Деплой на Render

### 1. Подготовка

1. Создайте аккаунт на [render.com](https://render.com)
2. Подключите GitHub репозиторий

### 2. Создание Web Service

1. **New** → **Web Service**
2. Выберите репозиторий
3. Конфигурация:

```
Name: xbalansebot
Region: Washington, D.C.
Branch: master
Root Directory: (оставить пустым)
Runtime: Docker
Build Command: (оставить пустым)
Start Command: (оставить пустым)
```

### 3. Environment Variables

Добавьте переменные в панели Render:

```
BOT_TOKEN=your_token
DATABASE_URL=postgresql://...
REDIS_URL=rediss://...
MAIN_GROUP_ID=-1001234567890
SUPER_ADMIN_ID=123456789
WEBHOOK_HOST=your-app.onrender.com
DEV_MODE=False
```

### 4. Database (Render PostgreSQL)

1. **New** → **PostgreSQL**
2. Скопируйте **External Database URL**
3. Используйте как `DATABASE_URL`

### 5. Redis (Render Redis)

1. **New** → **Redis**
2. Скопируйте **Connection String**
3. Используйте как `REDIS_URL`

---

## Деплой на VPS (Ubuntu 22.04)

### 1. Установка Зависимостей

```bash
sudo apt update
sudo apt install -y python3.13 python3.13-venv postgresql redis-server nginx certbot
```

### 2. Настройка PostgreSQL

```bash
sudo -u postgres psql
CREATE DATABASE xbalansebot;
CREATE USER xbalanse WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE xbalansebot TO xbalanse;
\q
```

### 3. Установка Бота

```bash
cd /opt
git clone https://github.com/Petergluk/XBalanseBot.git
cd XBalanseBot

python3.13 -m venv .venv
source .venv/bin/activate
pip install poetry
poetry install --no-dev
```

### 4. Создание .env

```bash
nano .env
# Добавьте переменные окружения (см. выше)
```

### 5. Применение Миграций

```bash
poetry run alembic upgrade head
```

### 6. Systemd Service

```bash
sudo nano /etc/systemd/system/xbalansebot.service
```

```ini
[Unit]
Description=XBalanseBot Telegram Bot
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/opt/XBalanseBot
Environment="PATH=/opt/XBalanseBot/.venv/bin"
ExecStart=/opt/XBalanseBot/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable xbalansebot
sudo systemctl start xbalansebot
```

### 7. Nginx Reverse Proxy

```bash
sudo nano /etc/nginx/sites-available/xbalansebot
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /webhook/telegram {
        proxy_pass http://127.0.0.1:8080/webhook/telegram;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Telegram-Bot-Api-Secret-Token $http_x_telegram_bot_api_secret_token;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/xbalansebot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 8. HTTPS (Let's Encrypt)

```bash
sudo certbot --nginx -d your-domain.com
```

---

## Проверка Работоспособности

### Health Check

```bash
curl https://your-domain.com/
# Ответ: "I'm awake!"
```

### Webhook Status

```bash
curl -s https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo | jq
```

Ожидаемый ответ:

```json
{
  "ok": true,
  "result": {
    "url": "https://your-domain.com/webhook/telegram",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "last_error_date": null,
    "last_synchronization_error_date": null
  }
}
```

### Логи

```bash
# Systemd
sudo journalctl -u xbalansebot -f

# Docker
docker-compose logs -f bot

# Файл
tail -f data/logs/bot_*.log
```

---

## Troubleshooting

### Бот не запускается

```bash
# Проверьте логи
journalctl -u xbalansebot -n 50

# Проверьте переменные окружения
systemctl cat xbalansebot

# Проверьте подключение к БД
poetry run python -c "from app.database import db; import asyncio; asyncio.run(db.initialize())"
```

### Webhook не работает

1. Проверьте SSL сертификат:
   ```bash
   sudo certbot certificates
   ```

2. Проверьте Nginx:
   ```bash
   sudo nginx -t
   sudo systemctl status nginx
   ```

3. Проверьте firewall:
   ```bash
   sudo ufw status
   sudo ufw allow 80,443/tcp
   ```

### Database Connection Errors

```bash
# Проверьте PostgreSQL
sudo systemctl status postgresql

# Проверьте подключения
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Перезапустите
sudo systemctl restart postgresql
```

### Redis Connection Errors

```bash
sudo systemctl status redis
redis-cli ping  # Должен вернуть PONG
```

---

## Миграции

### Создание новой миграции

```bash
poetry run alembic revision -m "add_new_column"
```

### Применение миграций

```bash
poetry run alembic upgrade head
```

### Откат миграций

```bash
poetry run alembic downgrade -1  # На одну назад
poetry run alembic downgrade base  # Полностью
```

### Проверка статуса

```bash
poetry run alembic current   # Текущая версия
poetry run alembic history   # История миграций
```

---

## Бэкапы

### Database Backup

```bash
# Создать бэкап
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# Восстановить
psql $DATABASE_URL < backup_20260615.sql
```

### Автоматический Бэкап (Cron)

```bash
crontab -e

# Ежедневный бэкап в 3:00
0 3 * * * pg_dump $DATABASE_URL > /backups/xbalansebot_$(date +\%Y\%m\%d).sql
```

---

## Обновление

```bash
cd /opt/XBalanseBot
git pull origin master
source .venv/bin/activate
poetry install --no-dev
poetry run alembic upgrade head
sudo systemctl restart xbalansebot
```

---

*Версия документа: 1.0*  
*Дата обновления: 2026-06-15*