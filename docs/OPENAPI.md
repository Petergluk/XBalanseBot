# OpenAPI Specification - XBalanseBot Webhooks

**Version:** 1.0.0  
**Last Updated:** 2026-06-15

## Overview

Этот документ описывает webhook endpoints для XBalanseBot — Telegram-бота для управления экономикой сообщества.

**Base URL:** `https://{WEBHOOK_HOST}`

---

## Endpoints

### 1. Health Check

Проверка работоспособности бота.

```http
GET /
```

**Response:**

```
Status: 200 OK
Content-Type: text/plain
Body: I'm awake!
```

**Use Cases:**
- Мониторинг uptime (UptimeRobot, Pingdom)
- Health checks в Kubernetes
- Проверка перед деплоем

---

### 2. Telegram Webhook

Получение обновлений от Telegram Bot API.

```http
POST /webhook/telegram
```

**Headers:**

| Header | Required | Description |
|--------|----------|-------------|
| `X-Telegram-Bot-Api-Secret-Token` | Yes | Secret token для верификации webhook |
| `Content-Type` | Yes | `application/json` |

**Request Body:**

Telegram отправляет JSON объект с обновлением. См. [Telegram Bot API - Update](https://core.telegram.org/bots/api#update).

**Пример запроса:**

```json
{
  "update_id": 123456789,
  "message": {
    "message_id": 1001,
    "from": {
      "id": 123456789,
      "is_bot": false,
      "first_name": "John",
      "username": "johndoe"
    },
    "chat": {
      "id": 123456789,
      "first_name": "John",
      "username": "johndoe",
      "type": "private"
    },
    "date": 1718445600,
    "text": "/start"
  }
}
```

**Response:**

```
Status: 200 OK
```

**Error Responses:**

| Status | Body | Description |
|--------|------|-------------|
| 403 | (empty) | Invalid secret token |
| 500 | (empty) | Internal server error |

---

### 3. Tribute Payment Webhook

Обработка платежей от платежной системы Tribute.

```http
POST /webhook/tribute
```

**Headers:**

| Header | Required | Description |
|--------|----------|-------------|
| `X-Tribute-Secret` | Yes | Secret key для верификации |
| `Content-Type` | Yes | `application/json` |

**Request Body Schema:**

```json
{
  "id": "payment_12345",
  "payment_id": "payment_12345",
  "transaction_id": "txn_67890",
  "invoice_id": "inv_11111",
  "amount": 100.00,
  "currency": "RUB",
  "status": "completed",
  "payer": {
    "telegram_id": "123456789",
    "username": "johndoe",
    "email": "john@example.com"
  },
  "created_at": "2026-06-15T10:30:00Z"
}
```

**Поля:**

| Поле | Тип | Required | Description |
|------|-----|----------|-------------|
| `id` | string | No | Уникальный ID платежа |
| `payment_id` | string | No | Альтернативный ID платежа (приоритет) |
| `transaction_id` | string | No | Альтернативный ID транзакции |
| `invoice_id` | string | No | Альтернативный ID инвойса |
| `amount` | number | Yes | Сумма в RUB |
| `currency` | string | No | Валюта (по умолчанию RUB) |
| `status` | string | No | Статус платежа |
| `payer.telegram_id` | string | **Yes** | Telegram ID плательщика |
| `payer.username` | string | No | Username плательщика |
| `payer.email` | string | No | Email плательщика |
| `created_at` | string | No | ISO 8601 timestamp |

**Success Response:**

```
Status: 200 OK
Content-Type: text/plain
Body: OK
```

**Duplicate Response (Idempotent):**

```
Status: 200 OK
Content-Type: text/plain
Body: OK (duplicate)
```

**Error Responses:**

| Status | Body | Description |
|--------|------|-------------|
| 200 | OK (duplicate) | Payment already processed |
| 400 | (empty) | Invalid request data (missing telegram_id, invalid amount) |
| 403 | (empty) | Invalid secret token |
| 500 | (empty) | Internal server error |
| 503 | (empty) | Webhook secret not configured (missing TRIBUTE_WEBHOOK_SECRET) |

---

## Idempotency

### Tribute Webhook

Webhook поддерживает идемпотентность через:

1. **Payment ID:** Если `payment_id` присутствует, проверяется уникальность в БД
2. **Payload Hash:** Если payment_id отсутствует, вычисляется SHA-256 hash от payload

**Алгоритм:**

```python
payment_ref_raw = (
    data.get("payment_id")
    or data.get("id")
    or data.get("transaction_id")
    or data.get("invoice_id")
)

if payment_ref_raw:
    payment_ref = f"tribute:{payment_ref_raw}"
else:
    payload_canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    payment_ref = f"tribute:hash:{sha256(payload_canonical)}"
```

**Database Constraint:**

```sql
INSERT INTO transactions (..., external_id)
VALUES (..., 'tribute:payment_12345')
ON CONFLICT (external_id) DO NOTHING
```

---

## Security

### Secret Tokens

| Webhook | Header | Environment Variable |
|---------|--------|---------------------|
| Telegram | `X-Telegram-Bot-Api-Secret-Token` | `WEBHOOK_SECRET_TOKEN` |
| Tribute | `X-Tribute-Secret` | `TRIBUTE_WEBHOOK_SECRET` |

**Требования к Secret Token:**

- Минимум 32 символа
- Криптографически безопасная генерация
- Никогда не коммитьте в git

**Генерация:**

```bash
# OpenSSL
openssl rand -hex 32

# Python
python -c "import secrets; print(secrets.token_hex(32))"

# Node.js
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

### Telegram IP Whitelisting

Telegram отправляет webhook с определённых IP диапазонов:

```
149.154.160.0/20
91.108.4.0/22
```

[Документация Telegram](https://core.telegram.org/bots/webhooks#ip-addresses)

**Пример настройки Nginx:**

```nginx
location /webhook/telegram {
    allow 149.154.160.0/20;
    allow 91.108.4.0/22;
    deny all;
    
    proxy_pass http://127.0.0.1:8080/webhook/telegram;
}
```

---

## Configuration

### Настройка Telegram Webhook

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/webhook/telegram",
    "secret_token": "your_secret_token_here"
  }'
```

### Проверка Статуса Webhook

```bash
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo" | jq
```

**Пример ответа:**

```json
{
  "ok": true,
  "result": {
    "url": "https://your-domain.com/webhook/telegram",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "last_error_date": null,
    "last_synchronization_error_date": null,
    "max_connections": 40,
    "ip_address": "149.154.167.50"
  }
}
```

### Удаление Webhook

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/deleteWebhook"
```

---

## Rate Limiting

### Telegram API Limits

| Operation | Limit |
|-----------|-------|
| Messages per second | ~30 |
| Messages to same chat | ~20/sec |
| Global limits | Зависит от типа операции |

### Tribute Webhook

Ограничения устанавливаются платежной системой. Рекомендации:

- Максимум 100 webhook'ов в минуту
- Retry с exponential backoff при 5xx ошибках

**Retry Logic:**

```python
# При получении 5xx от Tribute
delays = [1, 2, 4, 8, 16]  # seconds
for attempt, delay in enumerate(delays):
    response = send_webhook(data)
    if response.status < 500:
        break
    sleep(delay)
```

---

## Error Handling

### Retry Logic для Tribute

При получении ошибки 5xx:

1. Подождите 1 секунду
2. Повторите запрос
3. Если ошибка сохраняется, увеличьте delay (2s, 4s, 8s, 16s)
4. Максимум 5 попыток
5. После исчерпания — логирование и алерт админу

### Logging

Все webhook запросы логируются:

```
2026-06-15 10:30:00 - app.services.webhook_handler - INFO - Received Tribute webhook: {...}
2026-06-15 10:30:00 - app.services.webhook_handler - INFO - Payment tribute:payment_12345 processed for user 123456789
2026-06-15 10:30:00 - app.services.webhook_handler - WARNING - Received webhook with invalid secret.
2026-06-15 10:30:00 - app.services.webhook_handler - ERROR - Error processing Tribute webhook: Database connection failed
```

---

## Testing

### Local Testing с Ngrok

```bash
# 1. Запустите бота локально (DEV_MODE=True)
python main.py

# 2. В другом терминале запустите ngrok
ngrok http 8080

# 3. Используйте https://<ngrok-id>.ngrok.io/webhook/telegram
# для настройки webhook в Telegram
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://<ngrok-id>.ngrok.io/webhook/telegram",
    "secret_token": "test_token"
  }'
```

### Test Payloads

**Telegram Webhook:**

```bash
curl -X POST "http://localhost:8080/webhook/telegram" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: test_token" \
  -d '{
    "update_id": 1,
    "message": {
      "message_id": 1,
      "from": {"id": 123, "first_name": "Test", "username": "testuser"},
      "chat": {"id": 123, "type": "private"},
      "date": 1718445600,
      "text": "/start"
    }
  }'
```

**Tribute Webhook:**

```bash
curl -X POST "http://localhost:8080/webhook/tribute" \
  -H "Content-Type: application/json" \
  -H "X-Tribute-Secret: test_secret" \
  -d '{
    "payment_id": "test_payment_001",
    "amount": 100.00,
    "payer": {
      "telegram_id": "123456789",
      "username": "testuser"
    }
  }'
```

### Postman/Insomnia Collection

Импортируйте эти запросы для тестирования:

```json
{
  "name": "XBalanseBot Webhooks",
  "requests": [
    {
      "name": "Health Check",
      "request": {
        "method": "GET",
        "url": "{{baseUrl}}/"
      }
    },
    {
      "name": "Telegram Webhook",
      "request": {
        "method": "POST",
        "url": "{{baseUrl}}/webhook/telegram",
        "header": [
          {"key": "X-Telegram-Bot-Api-Secret-Token", "value": "{{telegram_secret}}"},
          {"key": "Content-Type", "value": "application/json"}
        ],
        "body": {
          "mode": "raw",
          "raw": "{\"update_id\": 1, \"message\": {\"text\": \"/start\"}}"
        }
      }
    },
    {
      "name": "Tribute Webhook",
      "request": {
        "method": "POST",
        "url": "{{baseUrl}}/webhook/tribute",
        "header": [
          {"key": "X-Tribute-Secret", "value": "{{tribute_secret}}"},
          {"key": "Content-Type", "value": "application/json"}
        ],
        "body": {
          "mode": "raw",
          "raw": "{\"payment_id\": \"test_001\", \"amount\": 100, \"payer\": {\"telegram_id\": \"123\"}}"
        }
      }
    }
  ]
}
```

---

## Monitoring

### Metrics to Track

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| Webhook latency | Время обработки webhook | > 5s |
| Failed webhooks | Количество ошибок 4xx/5xx | > 10/min |
| Duplicate payments | Количество дубликатов | > 5/hour |
| Pending updates | Непришедшие обновления от Telegram | > 100 |

### Health Check Endpoint

Для production рекомендуется расширить health check:

```python
async def health_check(request: web.Request):
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "telegram": await check_telegram_api()
    }
    
    if all(checks.values()):
        return web.json_response({"status": "healthy", "checks": checks})
    else:
        return web.json_response(
            {"status": "unhealthy", "checks": checks},
            status=503
        )
```

---

## Appendix

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `BOT_TOKEN` | Telegram Bot API token | Yes |
| `WEBHOOK_HOST` | Public domain for webhook | Yes (prod) |
| `WEBHOOK_SECRET_TOKEN` | Secret for Telegram webhook | Yes (prod) |
| `TRIBUTE_WEBHOOK_SECRET` | Secret for Tribute webhook | No |
| `DEV_MODE` | Enable polling mode | No (default: False) |
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |

### Related Documentation

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Tribute Payments](https://tribute.finance/docs)
- [aiogram 3.x Documentation](https://docs.aiogram.dev/)

---

*Last Updated: 2026-06-15*