# Архитектура XBalanseBot

## Обзор Системы

XBalanseBot — это Telegram-бот для управления внутренней экономикой сообщества с собственной валютой (орфы/Ӫ), системой активностей, событий и маркетплейсом.

## Архитектурная Диаграмма

```
┌─────────────────────────────────────────────────────────────────┐
│                        Telegram Bot API                          │
│                     (https://api.telegram.org)                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ Webhook / Polling
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     XBalanseBot Application                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    main.py (Entry Point)                   │  │
│  │  • Инициализация Bot, Dispatcher, Scheduler                │  │
│  │  • Регистрация роутеров и middleware                       │  │
│  │  • Настройка webhook / polling                             │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Middleware Layer                              │  │
│  │  • logging_middleware                                      │  │
│  │  • private_chat_restriction_middleware                     │  │
│  │  • admin_message_middleware                                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │   Handlers     │  │   Handlers     │  │   Handlers     │    │
│  │   (Routers)    │  │   (Routers)    │  │   (Routers)    │    │
│  ├────────────────┤  ├────────────────┤  ├────────────────┤    │
│  │ common.py      │  │ user_commands  │  │ admin_commands │    │
│  │ /start, /help  │  │ /menu, /send   │  │ /settings, ... │    │
│  │ /gdp           │  │ /balance       │  │ /add, /rem     │    │
│  └────────────────┘  └────────────────┘  └────────────────┘    │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │ activity_      │  │ event_         │  │ tag_reward_    │    │
│  │ handlers.py    │  │ handlers.py    │  │ handler.py     │    │
│  │ Активности     │  │ События        │  │ Награды        │    │
│  └────────────────┘  └────────────────┘  └────────────────┘    │
│  ┌────────────────┐                                            │
│  │ offer_         │                                            │
│  │ handlers.py    │                                            │
│  │ Биржа/Объявления│                                           │
│  └────────────────┘                                            │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Services Layer                           │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │ scheduler_jobs.py         │ webhook_handler.py            │  │
│  │ • process_demurrage       │ • handle_tribute_webhook      │  │
│  │ • schedule_event_jobs     │ • health_check                │  │
│  │ • run_event_payment       │ • run_webhook_server          │  │
│  │ • run_event_reminder      │                               │  │
│  └───────────────────────────┴───────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Database Layer                           │  │
│  │                   database.py                              │  │
│  │  ┌────────────────────────────────────────────────────┐   │  │
│  │  │  AsyncConnectionPool (psycopg3)                    │   │  │
│  │  │  • Max connections: 10 (configurable)              │   │  │
│  │  │  • Connection string: DATABASE_URL or individual   │   │  │
│  │  └────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Support Modules                          │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │ config.py      │ Конфигурация, env variables              │  │
│  │ keyboards.py   │ Inline клавиатуры                        │  │
│  │ callbacks.py   │ CallbackData фабрики                     │  │
│  │ states.py      │ FSM состояния                            │  │
│  │ utils.py       │ Вспомогательные функции                  │  │
│  │ lexicon.py     │ Все тексты бота (i18n ready)             │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│    PostgreSQL   │ │     Redis       │ │  File System    │
│  (Supabase/Local)│ │   (Upstash)    │ │                 │
├─────────────────┤ ├─────────────────┤ ├─────────────────┤
│ • users         │ │ • FSM storage   │ │ • data/logs/    │
│ • transactions  │ │ • Tag rules     │ │   (бот логи)    │
│ • activities    │ │   cache         │ │                 │
│ • events        │ │                 │ │                 │
│ • offers        │ │                 │ │                 │
│ • tag_rules     │ │                 │ │                 │
│ • settings      │ │                 │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

## Поток Данных

### 1. Пользовательская Команда

```
User → Telegram API → Webhook → main.py → Middleware → Handler → Database → Response
```

**Пример:** `/send @user 100`

1. Telegram отправляет webhook на `/webhook/telegram`
2. `main.py` получает обновление через `SimpleRequestHandler`
3. `logging_middleware` логирует событие
4. `private_chat_restriction_middleware` проверяет тип чата
5. `user_commands.cmd_send` обрабатывает команду
6. `db.transfer()` выполняет транзакцию в БД
7. Ответ отправляется пользователю

### 2. Фоновая Задача (Демерредж)

```
Scheduler → scheduler_jobs.process_demurrage → Database (batch update) → Log
```

**Расписание:** Ежедневно в 00:01 MSK

1. APScheduler триггерит `process_demurrage`
2. Проверка настроек (enabled, interval, last_run)
3. Выборка пользователей с положительным балансом (`FOR UPDATE`)
4. Расчёт налога (balance × rate)
5. Пакетное обновление балансов и транзакций
6. Обновление `demurrage_last_run`

### 3. Webhook Платежа (Tribute)

```
Tribute → POST /webhook/tribute → webhook_handler → Database → Telegram Notification
```

1. Проверка `X-Tribute-Secret` заголовка
2. Парсинг payload (telegram_id, amount)
3. Генерация idempotency key (payment_id или hash)
4. Проверка дубликатов (`ON CONFLICT DO NOTHING`)
5. Обновление баланса пользователя
6. Отправка уведомления в Telegram

## Компоненты

### Handlers (Роутеры)

| Модуль | Ответственность | Ключевые команды |
|--------|----------------|------------------|
| `common.py` | Базовые команды | `/start`, `/help`, `/gdp`, `/cancel` |
| `user_commands.py` | Пользовательские операции | `/menu`, `/balance`, `/send`, `/history` |
| `admin_commands.py` | Админ-панель | `/settings`, `/add`, `/rem`, `/users`, `/create_act` |
| `activity_handlers.py` | Управление активностями | Inline: act:, act_edit: |
| `event_handlers.py` | Управление событиями | Inline: evt:, evt_edit:, evt_create: |
| `tag_reward_handler.py` | Награды за хэштеги | Автоматическая обработка постов |
| `offer_handlers.py` | Биржа объявлений | Inline: offer:, buy_offer: |

### Services

| Модуль | Функции |
|--------|---------|
| `scheduler_jobs.py` | `process_demurrage()`, `schedule_event_jobs()`, `run_event_payment()`, `run_event_reminder()` |
| `webhook_handler.py` | `handle_tribute_webhook()`, `health_check()`, `run_webhook_server()` |

### Database Schema

```sql
-- Основные таблицы
users              -- Пользователи (id, telegram_id, username, balance, is_admin, ...)
transactions       -- История транзакций (from_user_id, to_user_id, amount, type, comment, ...)
activities         -- Активности (name, description, is_active, end_date, ...)
user_subscriptions -- Подписки на активности (user_id, activity_id)
events             -- События (activity_id, name, event_type, cost, event_date, weekday, ...)
event_registration_overrides -- Исключения регистрации (user_id, event_id, override_date, status)
offers             -- Объявления (seller_id, title, price, status, quantity, expires_at, ...)
tag_rules          -- Правила наград (hashtag, min_chars, reward, limit_amount, ...)
tag_rewards_log    -- Лог наград (user_telegram_id, message_id, rule_id, rewarded_at)
settings           -- Настройки бота (key, value)
```

## Развёртывание

### Режимы Работы

| Режим | Переменная | Описание |
|-------|-----------|----------|
| Development | `DEV_MODE=True` | Polling, MemoryStorage (опционально) |
| Production | `DEV_MODE=False` | Webhook, Redis storage |

### Платформы

- **Koyeb:** Git-based deployment, Docker builder
- **Render:** Web service, Docker
- **Local:** Docker Compose или прямой запуск

## Безопасность

### Уровни Доступа

1. **Пользователь:** Базовые команды (баланс, переводы, активности)
2. **Администратор:** Команды управления (`/add`, `/rem`, `/settings`)
3. **Супер-администратор:** `SUPER_ADMIN_ID` из env, полный доступ

### Middleware Protection

```python
@router.message.middleware()
async def admin_message_middleware(handler, event, data):
    if not await is_admin(data['event_from_user'].id):
        await event.reply("❌ У вас нет прав администратора")
        return
    return await handler(event, data)
```

## Масштабируемость

### Bottlenecks

1. **Database connections:** Max 10 (настраивается через `DB_POOL_SIZE`)
2. **Telegram rate limits:** ~30 сообщений/секунду
3. **Demurrage batch processing:** Блокировка пользователей при обработке

### Рекомендации

- Пакетная обработка демерреджа по 100 пользователей
- Semaphore для ограничения параллельных отправок
- Connection pooling с правильным размером

## Мониторинг

### Логи

- Расположение: `data/logs/bot_YYYY-MM-DD_HH-MM-SS.log`
- Формат: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

### Метрики (рекомендуется добавить)

- Транзакции в минуту
- Ошибки в час
- Активные пользователи (DAU/MAU)
- Общий объём экономики (total_supply)

---

*Версия документа: 1.0*  
*Дата обновления: 2026-06-15*