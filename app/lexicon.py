# XBalanseBot/app/lexicon.py
"""
Словарь всех пользовательских текстов интерфейса (LEXICON).
Упрощает поддержку и локализацию бота.
"""

LEXICON_RU: dict[str, str] = {
    # === Стартовые и приветственные сообщения по умолчанию ===
    "default_welcome_bot": (
        "Привет, {username}! 👋\n\n"
        "Добро пожаловать в Лабораторию Смысла — сообщество для обмена ценностями и взаимной поддержки.\n\n"
        "У нас всего три простых правила:\n\n"
        "1️⃣ Используем «Я-сообщения».\n"
        "2️⃣ Не занимаем без запроса экспертную позицию по отношению к другим.\n"
        "3️⃣ В любой непонятной ситуации прислушиваемся к себе и своим чувствам.\n\n"
        "Если ты согласен с этими правилами — жми кнопку ниже, и я выдам тебе ссылку для вступления в группу 👇"
    ),
    
    "default_welcome_group": (
        "👋 Добро пожаловать в Лабораторию Смысла, {username}!\n\n"
        "Это сообщество для обмена ценностями и взаимной поддержки.\n\n"
        "Чтобы начать работу с экономикой сообщества:\n"
        "1. Поздоровайтесь с участниками и расскажите немного о себе!\n"
        "2. Напишите боту @{bot_username} команду /start\n"
        "3. Ознакомьтесь со справкой /help в личном сообщении с ботом.\n\n"
        "Удачи в нашем путешествии! 🚀"
    ),
    
    "default_welcome_bonus": (
        "🎉 Добро пожаловать в группу!\n\n"
        "💰 Тебе начислен welcome-бонус: <b>{amount} {currency_symbol}</b>\n\n"
        "⚠️ Важно: '{currency_symbol}' (орфы) — условная единица учета для внутреннего нелинейного обмена практиками внутри клуба. "
        "Они не имеют реальной денежной стоимости и не подлежат обратному обмену на фиатные деньги."
    ),

    # === Справка и руководства ===
    "help_group": (
        "📖 <b>Основные команды</b>\n\n"
        "Для взаимодействия с ботом, пожалуйста, напишите ему в личные сообщения: @{bot_username}\n\n"
        "В личных сообщениях используйте команду /menu, чтобы открыть удобное меню со всеми функциями.\n\n"
        "<b>Команды, доступные в группе:</b>\n"
        "/send @username сумма [комментарий] - Быстрый перевод {currency_symbol} другому участнику\n"
        "/gdp - Общая статистика экономики сообщества\n"
        "/help - Эта справка (рекомендуется читать в ЛС)"
    ),
    
    "help_user": (
        "📖 <b>Как устроена Игровая Экономика</b>\n\n"
        "Мы используем концептуальную расчетную единицу — <b>{currency_symbol} (орфы)</b>. "
        "Она помогает нам обмениваться ценностью и поддерживать баланс вкладов участников.\n\n"
        "🔹 <b>Ценность вкладов:</b> За организацию активностей, ведение встреч, поддержку сообщества "
        "участники получают орфы друг от друга.\n"
        "🔹 <b>Оплата участия:</b> Орфы используются для записи и участия во внутренних мероприятиях "
        "и практиках.\n"
        "🔹 <b>Фонд и Демерредж:</b> Чтобы энергия не застаивалась, периодически может списываться небольшой "
        "процент с балансов в общий фонд. Из фонда поощряются волонтеры проекта!\n\n"
        "Все ваши действия (баланс, переводы, подписки на активности) доступны в удобном виде через главное меню: /menu\n"
        "Для быстрого перевода благодарности участнику можно использовать команду <code>/send @username сумма</code> прямо в группе."
    ),

    "help_admin_addon": (
        "\n<b>🔐 Административные команды</b>\n\n"
        "<b>🎯 Управление активностями и событиями:</b>\n"
        "Осуществляется через инлайн-кнопки в меню /activity.\n"
        "Зайдите в нужную активность или событие, чтобы увидеть панель администратора.\n"
        "/create_act - Создать новую активность\n"
        "/create_event - Создать новое событие\n\n"
        "<b>📢 Рассылка:</b>\n"
        "Запускается кнопкой «📢 Рассылка» внутри любой активности.\n"
        "Поддерживаются текст, фото, видео, файлы. Можно отложить отправку — бот вернёт ID задачи.\n"
        "/cancel_broadcast &lt;job_id&gt; — Отменить отложенную рассылку\n\n"
        "<b>🏷 Начисления за хэштеги:</b>\n"
        "Бот мониторит все посты в группе и начисляет орфы за нужные хэштеги.\n"
        "/add_tag_rule — Создать правило (хэштег → мин. символов → сумма → ...)\n"
        "/list_tag_rules — Список всех правил с ID\n"
        "/del_tag_rule &lt;id&gt; — Удалить правило\n"
        "/get_thread_id — Узнать ID топика (написать в нужной теме)\n\n"
        "<b>👤 Пользователи и начисления:</b>\n"
        "/users - Показать список всех пользователей\n"
        "/check @username - Проверить баланс, статус и историю пользователя\n"
        "/add @username сумма [комментарий] - Начислить {currency_symbol}\n"
        "/rem @username сумма [комментарий] - Списать {currency_symbol}\n\n"
        "<b>⚙️ Управление системой:</b>\n"
        "/settings - Открыть меню настроек (демерредж, бонусы, курс, шаблоны)\n\n"
        "<b>👮 Управление администраторами:</b>\n"
        "/make_admin @username - Назначить администратора\n"
        "/remove_admin @username - Снять права администратора\n\n"
        "<b>ℹ️ Руководства:</b>\n"
        "/gide - Подробное руководство для администратора\n"
        "/test - Показать тестовые команды\n"
    ),
    
    "gide_text": (
        "📜 <b>Руководство для Администратора</b>\n\n"
        "Этот бот управляет внутренней экономикой сообщества. Вот ключевые концепции:\n\n"
        "<b>1. Пользователи и Баланс:</b>\n"
        "- Каждый участник группы, запустивший бота, имеет свой баланс в <b>{currency_symbol}</b>.\n"
        "- Команда <code>/check @username</code> позволяет увидеть полную информацию о пользователе.\n\n"
        "<b>2. Активности (Activities):</b>\n"
        "- Это долгосрочные направления деятельности (кружки, группы, проекты). Например, \"Йога\" или \"Книжный клуб\".\n"
        "- Пользователи могут <b>подписываться</b> на активности (<code>/activity</code>), чтобы участвовать в связанных с ними событиях.\n"
        "- Для управления активностями (создание, редактирование, удаление) используйте меню /activity. Внутри каждой активности администратору доступна специальная панель.\n\n"
        "<b>3. События (Events):</b>\n"
        "- Это конкретные мероприятия с датой и стоимостью. Событие может быть привязано к активности или быть общим для всех.\n"
        "- <b>Типы событий:</b>\n"
        "    - <u>Разовое</u>: Происходит один раз в указанную дату и время.\n"
        "    - <u>Регулярное</u>: Повторяется по правилу (например, \"каждый вторник в 19:00\").\n"
        "- При наступлении события с подписчиков автоматически списывается плата.\n"
        "- Для управления событиями используйте меню /activity. Внутри каждого события администратору доступна панель редактирования и удаления.\n\n"
        "<b>4. Демередж (Demurrage):</b>\n"
        "- Механизм \"отрицательного процента на остаток\". Если включен, ежедневно с баланса каждого пользователя списывается небольшой процент в общий фонд.\n"
        "- Стимулирует оборот средств, а не их накопление.\n"
        "- Команды: <code>/demurrage_on</code>, <code>/demurrage_off</code>, <code>/set_demurrage</code>.\n\n"
        "<b>5. Фонд Сообщества:</b>\n"
        "- Это специальный системный пользователь (<code>@fund</code>), на счет которого поступают средства от демерреджа и других системных операций.\n"
        "- Пользователи могут добровольно пополнять фонд командой <code>/send @fund сумма</code>.\n"
        "- Из фонда можно делать выплаты пользователям (<code>/pay_from_fund</code>), например, за волонтерскую работу.\n\n"
        "<b>6. Welcome-бонус:</b>\n"
        "- Сумма, которая автоматически начисляется новому пользователю при первом запуске бота (<code>/start</code>) или при вступлении в группу.\n"
        "- Команда: <code>/welcome_bonus [сумма]</code>.\n\n"
        "<b>Ваши основные задачи:</b>\n"
        "- Создавать и поддерживать актуальность активностей и событий.\n"
        "- Отвечать на вопросы пользователей.\n"
        "- Управлять системными настройками (демередж, курс обмена).\n"
        "- Модерировать экономику: делать начисления (<code>/add</code>), списания (<code>/rem</code>) и выплаты из фонда.\n"
    ),
    
    "test_commands": (
        "🧪 <b>Набор команд для тестирования</b>\n\n"
        "<i>(Пользователь @fedorern должен существовать)</i>\n\n"
        "<b>🔹 Основные команды:</b>\n"
        "/help -  справка\n\n"
        "<b>2. Начисление и списание:</b>\n"
        "<code>/add @fedorern 1000 Начисление для теста</code>\n"
        "<code>/rem @fedorern 500 Списание для теста</code>\n"
        "<code>/send @fedorern 150 Тестовый перевод</code>\n"
        "<code>/send @fund 1000 Пополнение фонда</code>\n"
        "<code>/check @fedorern</code>\n"
        "<code>/check @fund</code>\n\n"
        "/balance - баланс и количество транзакций\n"
        "/history [дней] - История транзакций (по умолчанию за 30 дней)\n"
        "/gdp - Общая статистика экономики сообщества\n"
        "---\n"
        "<b>5. Управление активностями:</b>\n"
        "/activity - Управление подписками на активности (теперь содержит и админ. функции)\n"
        "/event - Просмотр ближайших событий\n"
        "---\n"
        "/create_act - Создать новую активность\n"
        "/create_event - Создать новое событие\n\n"
        "<b>⚙️ Управление системой:</b>\n"
        "/settings - Открыть меню настроек системы\n"
        "/edit_welcome_bot - Редактировать приветствие в боте\n"
        "/edit_welcome_group - Редактировать приветствие в группе\n"
        "/welcome_bonus [сумма] - Установить welcome-бонус\n"
        "---\n"
        "/demurrage_status - Статус демереджа\n"
        "/demurrage_on - Включить демередж\n"
        "/demurrage_off - Выключить демередж\n"
        "/set_demurrage [процент] - Установить процент демереджа\n"
        "/set_exchange [курс] - Установить курс обмена\n\n"
        "<b>👮 Управление администраторами:</b>\n"
        "<code>/make_admin @fedorern</code> - Назначить администратора\n"
        "<code>/remove_admin @fedorern</code> - Снять права администратора\n"
        "<code>/check @fedorern</code>\n\n"
        "<b>ℹ️ Руководства:</b>\n"
        "/gide - Подробное руководство для администратора\n"
        "/test - Показать тестовые команды\n\n"
        "/cancel - Отменить текущий диалог\n"
    ),

    # === Шаблоны ===
    "default_reminder": (
        "🔔 Через {reminder_minutes} минут начинаем:\n"
        "<b>{event_name}</b>\n\n"
        "{event_description}\n"
        "Время начала: {start_date} в {start_time}\n"
        "Стоимость участия: {cost} {currency_symbol}\n\n"
        "Заходите по ссылке: {link}\n"
    ),
    
    # === Общие кнопки ===
    "btn_back": "⬅️ Назад",
    "btn_cancel": "❌ Отмена",
    "btn_confirm": "✅ Подтвердить",
    
    # === Инлайн Кнопки ===
    "btn_menu_send": "💸 Перевести Ӫ другому участнику",
    "btn_menu_activity": "🎨 Активности сообщества",
    "btn_menu_event": "📅 Ближайшие события",
    "btn_menu_balance": "💰 Баланс и история",
    "btn_menu_help": "📖 Справка",
    
    # === Клавиатура онбординга ===
    "btn_onboarding_agree": "✅ Согласен",
    
    # === Общие кнопки ===
    "btn_back_to_menu": "⬅️ Назад в меню",
    "btn_edit_message": "📝 Редактировать сообщение",
    "btn_yes_delete": "✅ Да, удалить",
    "btn_save": "✅ Сохранить",
    
    # === Обучение / События / Активности ===
    "msg_event_reminder_vars_help": (
        "<b>Доступные переменные:</b>\n"
        "<code>{event_name}</code> - название события\n"
        "<code>{event_description}</code> - описание события\n"
        "<code>{start_date}</code> - дата события (ДД.ММ.ГГГГ)\n"
        "<code>{start_time}</code> - время события (ЧЧ:ММ)\n"
        "<code>{cost}</code> - стоимость участия\n"
        "<code>{currency_symbol}</code> - символ валюты\n"
        "<code>{reminder_minutes}</code> - за сколько минут напоминание\n"
        "<code>{link}</code> - ссылка на событие\n"
    ),
    "msg_events_none_soon": "В ближайшее время событий не запланировано.",
    "msg_events_none_this_week": "На ближайшую неделю событий не запланировано.",
    "msg_events_this_week_header": "📅 События на ближайшие 7 дней (время указывается в MSK):",
    "msg_event_schedule_recurring_next": "📅 Регулярность: {weekdays}\n📅 Следующее: {next_date_str} ({msk_label})",
    "msg_event_schedule_recurring_only": "📅 Регулярность: {weekdays} в {time_str} ({msk_label})",
    "msg_event_view_details": (
        "<b>{event_name}</b>\n\n"
        "<i>{event_description}</i>\n\n"
        "{schedule_str}\n"
        "💰 Стоимость: {cost} {currency_symbol}\n"
        "🔗 Ссылка будет отправлена подписчикам в личные сообщения."
    ),
    "msg_event_ask_activity": "К какой активности относится событие?",
    "msg_event_ask_name": "Введите название для события. Отправьте `.` чтобы использовать название активности.\n\n*Для отмены введите /cancel*",
    "msg_event_ask_description": (
        "Отлично! Теперь введите описание для события.\n\n"
        "<i>Описание активности для справки:</i>\n<code>{activity_desc}</code>\n\n"
        "Для отмены введите /cancel"
    ),
    "btn_use_activity_desc": "Использовать описание активности",
    "msg_event_ask_type": "Выберите тип события:",
    "btn_event_type_single": "Разовое",
    "btn_event_type_recurring": "Регулярное",
    "msg_event_ask_date_single": "Введите дату и время события в формате <b>ДД.ММ.ГГГГ ЧЧ:ММ</b> (время в MSK)\n\nДля отмены введите /cancel",
    "msg_event_ask_weekdays": "Выберите дни недели для регулярного события:",
    "msg_event_ask_cost": "Отлично. Теперь введите стоимость участия (число, 0 для бесплатного).\n\n*Для отмены введите /cancel*",
    "err_event_date_past": "❌ Нельзя создать событие в прошлом. Пожалуйста, введите будущую дату и время (MSK).",
    "err_event_invalid_date_format": "❌ Неверный формат. Введите дату и время в формате <b>ДД.ММ.ГГГГ ЧЧ:ММ</b> (MSK).",
    "err_event_no_weekdays_selected": "Выберите хотя бы один день!",
    "msg_event_ask_time_recurring": "Вы выбрали: <b>{weekdays}</b>.\nТеперь введите время в формате <b>ЧЧ:ММ</b> (MSK).",
    "err_event_invalid_time_format": "❌ Неверный формат. Введите время в формате <b>ЧЧ:ММ</b> (MSK).",
    "msg_event_ask_end_date": (
        "Вы выбрали: <b>{weekdays}</b>, в <b>{time_str}</b> (MSK).\n\n"
        "После какой даты прекратить проведение? Введите дату в формате <b>ДД.ММ.ГГГГ</b>\n"
        "или нажмите кнопку ниже, чтобы оставить без ограничений."
    ),
    "btn_event_no_end_date": "♾️ Без ограничений",
    "msg_event_ask_link": "Теперь введите ссылку на событие (например, на чат или видеоконференцию).\n\n*Для отмены введите /cancel*",
    "err_event_invalid_cost": "❌ Введите корректное неотрицательное число.",
    "msg_event_ask_reminder_time": "За сколько минут до начала отправлять напоминание? Введите число (0 - не отправлять).\n\n*Для отмены введите /cancel*",
    "msg_event_ask_reminder_text": (
        "Введите текст напоминания.\n\n"
        "<i>Текущий шаблон по умолчанию:</i>\n<code>{default_reminder}</code>\n\n"
        "{vars_help}\n\n"
        "Для отмены введите /cancel"
    ),
    "btn_use_default_reminder": "Использовать шаблон по умолчанию",
    "err_event_invalid_reminder_time": "❌ Введите целое неотрицательное число.",
    "msg_event_preview_schedule_single": "📅 Разовое: {date_str} ({msk_label})",
    "msg_event_preview_schedule_recurring": "📅 Регулярное: {weekdays} в {time_str} ({msk_label})",
    "msg_event_no_reminder": "Нет",
    "msg_event_end_date_label": "до {end_date}",
    "msg_event_no_end_date_label": "без ограничений",
    "msg_event_preview_details": (
        "<b>💡 Предпросмотр события</b>\n\n"
        "<b>Название:</b> {name}\n"
        "<b>Активность:</b> {activity_name}\n"
        "<b>Описание:</b> {description}\n\n"
        "<b>Расписание:</b> {schedule_str}\n"
        "<b>Стоимость:</b> {cost} {currency_symbol}\n"
        "<b>Ссылка:</b> {link}\n"
        "<b>Напоминание за:</b> {reminder}\n\n"
        "Сохранить событие?"
    ),
    "msg_event_created_success": "✅ Событие успешно создано и запланировано (ID: {event_id}).",
    "err_event_already_deleted": "Событие уже удалено.",
    "msg_event_edit_menu": "<b>📝 Редактирование события:</b>\n<code>{event_name}</code>\n\nЧто вы хотите изменить?",
    "msg_event_delete_confirm": "Вы уверены, что хотите удалить событие «<b>{event_name}</b>»?\n\nЭто действие необратимо.",
    "msg_event_deleted": "✅ Событие «<b>{event_name}</b>» успешно удалено.",
    "msg_event_edit_name": (
        "Текущее название: <code>{current_name}</code>\n\n"
        "Введите новое название или `.` чтобы использовать название активности.\n\n"
        "Для отмены введите /cancel"
    ),
    "msg_event_name_updated": "✅ Название события обновлено.",
    "msg_event_edit_description": (
        "Текущее описание: <code>{current_desc}</code>\n\n"
        "Введите новое описание или `.` чтобы использовать описание активности.\n\n"
        "Для отмены введите /cancel"
    ),
    "msg_event_description_updated": "✅ Описание события обновлено.",
    "msg_event_edit_date": "Введите новую дату и время в формате <b>ДД.ММ.ГГГГ ЧЧ:ММ</b> (MSK)\n\nДля отмены введите /cancel",
    "msg_event_edit_weekdays": "Выберите дни недели:",
    "msg_event_date_updated": "✅ Дата события обновлена и перепланирована.",
    "msg_event_edit_time_recurring": "Выбрано: <b>{weekdays}</b>.\nТеперь введите новое время в формате <b>ЧЧ:ММ</b> (MSK).",
    "msg_event_schedule_updated": "✅ Расписание события обновлено и перепланировано.",
    "msg_event_edit_cost": "Текущая стоимость: <code>{current_cost} {currency_symbol}</code>\n\n",
    "msg_event_edit_cost_warning": "⚠️ <b>Внимание!</b> Это общее событие. Изменение стоимости затронет всех пользователей!\n\n",
    "msg_event_edit_cost_prompt": "Введите новую стоимость (число).\n\nДля отмены введите /cancel",
    "msg_event_cost_updated": "✅ Стоимость события обновлена.",
    "msg_event_edit_link": (
        "Текущая ссылка: <code>{current_link}</code>\n\n"
        "Введите новую ссылка.\n\n"
        "Для отмены введите /cancel"
    ),
    "msg_event_link_updated": "✅ Ссылка на событие обновлена.",
    "msg_event_edit_reminder_time": (
        "Текущее время напоминания: <code>{current_time_str}</code>\n\n"
        "Введите за сколько минут до события отправлять напоминание (0 - отключить).\n\n"
        "Для отмены введите /cancel"
    ),
    "msg_event_edit_reminder_text": (
        "Введите новый текст напоминания или `.` для шаблона по умолчанию.\n\n"
        "{vars_help}\n\n"
        "Для отмены введите /cancel"
    ),
    "msg_event_reminder_disabled": "✅ Напоминание отключено.",
    "msg_event_reminder_updated": "✅ Параметры напоминания обновлены.",
    
    "msg_activities_default_desc": (
        "<b>🎨 Активности сообщества</b>\n\n"
        "«Активность» — это направление (курс, клуб), которое содержит одно или несколько событий.\n\n"
        "✅ - вы подписаны на все события\n"
        "🧘‍♀️ и др. - вы не подписаны\n\n"
        "Выберите направление, чтобы увидеть список событий и записаться:"
    ),
    "msg_activities_empty": "На данный момент нет ни одной доступной активности.",
    "msg_activity_details_header": "<b>{name}</b>\n\n{description}\n\n",
    "msg_activity_no_description": "Описание уточняется...",
    "msg_activity_general_events_desc": (
        "<b>📢 ОБЩИЕ СОБЫТИЯ</b>\n\n"
        "Это открытые встречи и общесистемные события, на которые автоматически подписаны все участники сообщества.\n\n"
    ),
    "msg_activity_upcoming_events": "<b>Ближайшие события:</b>",
    "msg_activity_no_events": "\n\n<i>В этом направлении пока нет запланированных событий.</i>",
    
    "err_event_not_found": "Событие не найдено.",
    "msg_event_no_future_runs": "У этого события нет запланированных запусков в будущем.",
    "msg_event_schedule_not_determined": "Не определено",
    "msg_event_schedule_single": "📅 Дата: {date_str} ({msk_label})",
    "msg_event_schedule_recurring": "📅 Регулярность: {weekdays} в {time_str} ({msk_label})\n🗓️ Следующее занятие: {next_date_str}",
    "msg_event_details": "<b>{event_name}</b>\n\n<i>{event_description}</i>\n\n{schedule_str}\n💰 Стоимость: {cost} {currency_symbol}\n",
    "msg_event_subscribed_globally": "\n<i>✅ Вы получаете рассылку об этом событии (подписаны на активность).</i>",
    "msg_event_needs_global_subscription": "\n<i>❌ Для участия в этом событии необходимо подписаться на всю активность.</i>",
    
    "msg_activity_subscribed": "✅ Вы подписались на все события активности '{activity_name}'!",
    "msg_activity_unsubscribed": "✅ Вы отписались от активности '{activity_name}'.",
    "msg_unsubscribe_confirm": "❓ Хотите отписаться от активности <b>{activity_name}</b>?",
    "btn_unsubscribe_yes": "✅ Да, отписаться",
    "btn_unsubscribe_no": "❌ Нет, остаться",
    "msg_event_registered": "✅ Вы записаны на это событие!",
    "msg_event_registration_cancelled": "✅ Ваша запись на это событие отменена.",
    
    "msg_activity_ask_name": "Введите название новой активности:\n\n*Для отмены введите /cancel*",
    "msg_activity_ask_description": "Отлично! Теперь введите описание активности:\n\n*Для отмены введите /cancel*",
    "msg_activity_ask_end_date": "Теперь введите дату окончания активности в формате ДД.ММ.ГГГГ или напишите 'нет', если она бессрочная.\n\n*Для отмены введите /cancel*",
    "err_activity_invalid_date": "❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ или 'нет'.\n\n*Для отмены введите /cancel*",
    "msg_activity_created": "✅ Новая активность '{activity_name}' успешно создана!",
    "err_activity_creation_failed": "❌ Активность с названием '{activity_name}' уже существует или произошла ошибка БД. Пожалуйста, выберите другое название или отмените операцию (/cancel).",
    "msg_activity_ask_name_retry": "Введите название новой активности:",
    "msg_activity_edit_menu": "<b>Управление активностью:</b>\n{activity_name}",
    "msg_activity_edit_name": "Текущее название: `{current_value}`\n\nВведите новое:",
    "msg_activity_edit_description": "Текущее описание: `{current_value}`\n\nВведите новое:",
    "msg_activity_name_updated": "✅ Название активности обновлено.",
    "msg_activity_description_updated": "✅ Описание активности обновлено.",
    "err_activity_cannot_delete": "Эту активность нельзя удалить.",
    "msg_activity_delete_confirm": "Вы уверены, что хотите удалить активность «{activity_name}»?\n<b>Это действие необратимо и удалит все связанные подписки и события!</b>",
    "err_activity_already_deleted": "Активность уже удалена.",
    "msg_activity_deleted": "✅ Активность «{activity_name}» была удалена.",
    "btn_activity_create_event": "Создать событие для этой активности",
    
    # === Активности ===
    "text_general_events": "ОБЩИЕ СОБЫТИЯ",
    "btn_create_activity": "➕ Создать новую активность",
    "btn_edit_activities_desc": "📝 Изменить описание раздела",
    "btn_unsubscribe_activity": "✅ Вы подписаны",
    "btn_subscribe_all_events": "🔔 Подписаться на все события",
    "btn_edit": "✏️ Редактировать",
    "btn_create_event": "➕ Создать событие",
    "btn_list_subscribers": "👥 Список подписчиков",
    "btn_back_to_activities": "⬅️ Назад к списку",
    "btn_edit_name": "📝 Изменить название",
    "btn_edit_desc": "📄 Изменить описание",
    "btn_delete_activity": "🗑️ Удалить активность",
    "btn_back_to_activity_view": "⬅️ Назад к просмотру",
    
    # === События ===
    "btn_registered_manual": "✅ Вы записаны на {date_str} (Отменить)",
    "btn_registered_auto": "✅ Авто-запись на {date_str} (Отменить)",
    "btn_register_event": "➕ Записаться на {date_str}",
    "btn_cancelled_auto": "❌ Вы отменили запись на {date_str} (Вернуть)",
    "btn_delete": "🗑️ Удалить",
    "btn_back_to_activity": "⬅️ Назад к активности",
    "text_general_events_for_all": "ОБЩИЕ СОБЫТИЯ (для всех)",
    "btn_back_to_events": "⬅️ Назад к списку",
    
    "btn_event_name": "Название",
    "btn_event_desc": "Описание",
    "btn_event_schedule": "Расписание",
    "btn_event_cost": "Стоимость",
    "btn_event_link": "Ссылку",
    "btn_event_reminder": "Напоминание",
    "btn_back_to_event_view": "⬅️ Назад к просмотру события",
    "btn_done_confirm": "✅ Готово (Подтвердить)",
    "btn_broadcast": "📢 Рассылка",
    "msg_broadcast_ask_message": (
        "📢 <b>Рассылка подписчикам «{activity_name}»</b>\n\n"
        "Подписчиков: <b>{count}</b>\n\n"
        "Отправьте сообщение для рассылки — текст, фото, видео или файл.\n\n"
        "<i>Для отмены введите /cancel</i>"
    ),
    "msg_broadcast_no_subscribers": "ℹ️ На активность «{activity_name}» пока никто не подписан.",
    "msg_broadcast_preview": (
        "📨 <b>Предпросмотр рассылки</b>\n\n"
        "Активность: <b>{activity_name}</b>\n"
        "Получателей: <b>{count}</b>\n\n"
        "Разослать это сообщение всем подписчикам?"
    ),
    "btn_broadcast_confirm": "✅ Разослать",
    "msg_broadcast_done": "✅ Рассылка завершена: {success} из {total} доставлено.",
    "msg_broadcast_cancelled": "❌ Рассылка отменена.",
    "msg_broadcast_ask_schedule": (
        "⏱ <b>Когда отправить рассылку?</b>\n\n"
        "Нажмите «Отправить сейчас» или введите дату и время в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code> (время MSK)"
    ),
    "btn_broadcast_now": "🚀 Отправить сейчас",
    "msg_broadcast_scheduled": "🕒 Рассылка запланирована на <b>{dt_str}</b> (MSK). ID задачи: <code>{job_id}</code>",
    "err_broadcast_past_datetime": "❌ Это время уже прошло. Введите будущую дату и время.",
    "err_broadcast_invalid_datetime": "❌ Неверный формат. Введите дату и время: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
    
    # === Настройки ===
    # === Тег-награды ===
    "msg_tag_reward_default_dm": (
        "🏅 <b>Начислено!</b>\n\n"
        "За пост с #{hashtag} вам начислено <b>{amount} {currency_symbol}</b>.\n"
        "Баланс: <b>{balance} {currency_symbol}</b>"
    ),
    "btn_tag_rules": "� Поощрения",
    "msg_tag_rules_list_empty": "ℹ️ Нет активных правил. Добавьте первое: /add_tag_rule",
    "msg_tag_rules_list_header": "🏷 <b>Правила начисления по хэштегам:</b>\n\n",
    "msg_tag_rule_row": (
        "#{hashtag} — мин. {min_chars} симв. → <b>{reward} {currency_symbol}</b>"
        "{limit_str}{thread_str}\n"
        "ID: <code>{rule_id}</code>\n\n"
    ),
    "msg_add_tag_rule_hashtag": "🏷 Введите хэштег (можно с # или без):\n\n<i>Например: feedback</i>",
    "msg_add_tag_rule_min_chars": "Минимальное количество символов в посте (0 = без ограничения):",
    "msg_add_tag_rule_reward": "Сумма начисления в орфах (например: 100):",
    "msg_add_tag_rule_limit_amount": "Сколько раз можно получить награду (лимит срабатываний)? 0 = без лимита:",
    "msg_add_tag_rule_limit_period": "За какой период действует этот лимит (в днях)?\n0 = навсегда (например, разовый бонус)\n1 = в день\n7 = в неделю",
    "msg_add_tag_rule_thread_id": (
        "ID топика (темы) для ограничения — введите число или нажмите Skip.\n"
        "Узнать ID: скопируйте и отправьте <code>/get_thread_id</code> прямо в нужном топике.\n\n"
        "<i>Нажмите кнопку, чтобы пропустить (ловить во всех темах).</i>"
    ),
    "msg_add_tag_rule_group_msg": (
        "Сообщение в группу при начислении (reply на пост).\n"
        "Переменные: {mention}, {amount}, {currency_symbol}, {hashtag}\n\n"
        "<i>Нажмите Skip, чтобы не отправлять сообщение в группу.</i>"
    ),
    "msg_add_tag_rule_bot_msg": (
        "Личное сообщение пользователю (DM).\n"
        "Переменные: те же + {balance}\n\n"
        "<i>Нажмите Skip, чтобы использовать стандартное уведомление.</i>"
    ),
    "msg_add_tag_rule_reaction": "Реакция-эмодзи на пост (одно), или Skip для 🏅:",
    "btn_skip": "⏭ Skip",
    "msg_tag_rule_created": "✅ Правило создано (ID: <code>{rule_id}</code>): #{hashtag} → {reward} {currency_symbol}.",
    "msg_tag_rule_deleted": "✅ Правило <code>{rule_id}</code> удалено.",
    "err_tag_rule_not_found": "❌ Правило с таким ID не найдено.",
    "msg_get_thread_id": "🧵 Этот топик/тема: <code>{thread_id}</code>",
    "btn_menu_demurrage": "📉 Настройки демерреджа",
    "btn_menu_welcome_group": "👋 Приветствие в группе",
    "btn_back": "⬅️ Назад",
    "btn_demurrage_on": "✅ Демерредж ВКЛЮЧЕН",
    "btn_demurrage_off": "❌ Демерредж ВЫКЛЮЧЕН",
    "btn_welcome_group_on": "✅ Приветствие в группе ВКЛЮЧЕНО",
    "btn_welcome_group_off": "❌ Приветствие в группе ВЫКЛЮЧЕНО",
    "btn_welcome_bonus": "🎁 Welcome-бонус",
    "btn_exchange_rate": "💱 Курс обмена",
    "btn_demurrage_rate": "📉 % Демерреджа",
    "btn_demurrage_save": "💾 Сохранить изменения",
    "btn_edit_reminder": "📝 Шаблон напоминания",
    "btn_edit_welcome_bot": "📝 Приветствие (бот)",
    "btn_edit_welcome_group": "📝 Приветствие (группа)",
    "btn_demurrage_status": "📊 Статус демерреджа",
    
    # === Ошибки и уведомления ===
    "msg_action_cancelled": "❌ Действие отменено.",
    "msg_action_cancelled_plain": "Действие отменено.",
    "msg_welcome_back": (
        "🎉 С возвращением, {mention}! Вы улетали, но обещали вернуться!\n"
        "Где вы пропадали и почему решили зайти? Нечего тут шастать туда-сюда! 😅\n\n"
        "📊 <b>Ваша статистика:</b>\n"
        "💰 Текущий баланс: <b>{balance} {currency_symbol}</b>\n"
        "📤 Отправлено: <b>{sent} {currency_symbol}</b>\n"
        "📥 Получено: <b>{received} {currency_symbol}</b>\n"
        "📉 Списано системой: <b>{deducted} {currency_symbol}</b>"
    ),
    "msg_welcome_back_simple": (
        "👋 И снова здрасьте, {mention}!\n\n"
        "Что-то вы быстро вернулись — соскучились? 😄\n"
        "Всё на месте, меню ждёт вас."
    ),
    "msg_invite_link": "Отлично! Вот твоя индивидуальная ссылка для вступления в группу:\n\n{invite_link}",
    "err_invite_link": "Произошла ошибка при создании ссылки. Пожалуйста, обратитесь к администратору.",
    "msg_already_subscribed": "Вы уже подписаны на эту активность.",

    # === Главное меню и Баланс ===
    "msg_user_not_found_profile": "Не удалось найти ваш профиль в системе.",
    "msg_no_transactions": "За последние {days} дней транзакций не найдено.",
    "msg_history_header": "📊 <b>История транзакций за последние {days} дней:</b>",
    "msg_current_balance": "\n💰 <b>Текущий баланс:</b> {balance} {currency_symbol}",
    "msg_main_menu": (
        "🤖 <b>Главное меню</b>\n"
        "💰 Ваш баланс: <b>{balance} {currency_symbol}</b>\n\n"
        "Выберите действие:"
    ),
    "msg_balance_and_history": (
        "💰 Ваш баланс: <b>{balance} {currency_symbol}</b>\n\n"
        "{history_text}"
    ),

    # === Переводы ===
    "msg_transfer_ask_recipient": "Кому вы хотите сделать перевод? Укажите @username получателя.\n\nДля отмены введите /cancel",
    "err_transfer_self": "❌ Нельзя отправить средства самому себе.",
    "err_transfer_self_dialog": "❌ Нельзя отправить средства самому себе. Укажите другой @username.",
    "err_transfer_invalid_amount": "❌ Неверная сумма. Пожалуйста, укажите положительное число.",
    "err_transfer_invalid_amount_dialog": "❌ Сумма должна быть положительным числом. Попробуйте еще раз.\n\nДля отмены введите /cancel",
    "err_user_not_found": "❌ Пользователь @{recipient_username} не найден или не является участником группы.",
    "err_user_not_found_dialog": "❌ Пользователь @{recipient_username} не найден или не является участником группы. Попробуйте еще раз.\n\nДля отмены введите /cancel",
    "err_transfer_format": "❌ Неверный формат. Используйте:\n`/send @username сумма [комментарий]`\nили просто `/send` для запуска диалога.",
    "msg_transfer_ask_amount": "Отлично. Какую сумму в {currency_symbol} вы хотите перевести @{recipient_username}?\n\nДля отмены введите /cancel",
    "err_insufficient_funds": "❌ Недостаточно средств. Ваш баланс: <b>{balance} {currency_symbol}</b>. Введите другую сумму.\n\nДля отмены введите /cancel",
    "err_insufficient_funds_plain": "❌ Недостаточно средств. Ваш баланс: <b>{balance} {currency_symbol}</b>",
    "err_sender_not_found": "❌ Ваш профиль не найден в системе.",
    "msg_transfer_ask_comment": "Теперь добавьте короткий комментарий к переводу (например, 'За кофе').\n\nДля отмены введите /cancel",
    "msg_transfer_confirm": (
        "Пожалуйста, проверьте детали перевода:\n\n"
        "➡️ <b>Получатель:</b> @{recipient_username}\n"
        "💰 <b>Сумма:</b> {amount} {currency_symbol}\n"
        "💬 <b>Комментарий:</b> {comment}\n\n"
        "Всё верно?"
    ),
    "msg_transfer_success": (
        "✅ Перевод выполнен!\n\n"
        "<b>Получатель:</b> @{recipient_username}\n"
        "<b>Сумма:</b> {amount} {currency_symbol}\n"
        "<b>Комментарий:</b> {comment}"
    ),
    "msg_transfer_received": (
        "💸 Вам поступил перевод!\n\n"
        "<b>Отправитель:</b> @{sender_username}\n"
        "<b>Сумма:</b> {amount} {currency_symbol}\n"
        "<b>Комментарий:</b> {comment}"
    ),
    "err_transfer_failed": "❌ Произошла ошибка при выполнении перевода. Попробуйте позже.",

    # === GDP (ВВП) ===
    "msg_gdp_stats": (
        "📊 <b>Экономика сообщества:</b>\n\n"
        "💱 <b>Оборот (переводы между пользователями):</b>\n"
        "• За 7 дней: {turnover_7d} {currency_symbol} ({tx_count_7d} транзакций)\n"
        "• За 30 дней: {turnover_30d} {currency_symbol} ({tx_count_30d} транзакций)\n"
        "• За все время: {turnover_all} {currency_symbol} ({tx_count_all} транзакций)\n\n"
        "💰 <b>Денежная масса:</b>\n"
        "• Всего в системе: {total_supply} {currency_symbol}\n"
        "• В фонде сообщества: {fund_balance} {currency_symbol}"
    ),

    # === Администрирование ===
    "err_no_admin_rights": "❌ У вас нет прав для выполнения этой команды.",
    "err_no_admin_rights_alert": "❌ У вас нет прав для этого действия.",
    "err_admin_format": "❌ Неверный формат. Используйте:\n`{command} @username сумма [комментарий]`",
    "err_admin_format_username": "❌ Формат: {command} @username",
    "err_admin_format_retry": "❌ Неверный формат. Попробуйте еще раз.",
    "err_admin_invalid_amount": "❌ Неверная сумма. Укажите положительное число.",
    "err_admin_user_not_found": "❌ Пользователь @{username} не найден.",
    "err_admin_specify_username": "❌ Укажите @username пользователя для проверки.",
    "msg_admin_balance_changed": "✅ {action_word} <b>{amount} {currency_symbol}</b> {preposition} счет пользователя @{username}.",
    "msg_admin_notified_user": "ℹ️ Администратор @{admin_username} выполнил операцию с вашим счетом.\n<b>{action_word}:</b> {amount} {currency_symbol}\n<b>Комментарий:</b> {comment}",
    "err_admin_operation_failed": "❌ Произошла ошибка при выполнении операции.",
    "msg_admin_no_users": "В системе пока нет пользователей.",
    "msg_admin_users_header": "👥 <b>Всего пользователей: {total_users}</b>\n\n",
    "msg_admin_user_row": "{index}. {admin_mark}{username} — {balance} {currency_symbol}\n",
    "msg_admin_users_footer": "\n<i>Показаны первые {page_size} из {total_users} пользователей</i>",
    "msg_admin_no_transactions": "<i>Нет транзакций</i>",
    "msg_admin_check_user": (
        "👤 <b>Информация о пользователе @{username}</b>\n\n"
        "<b>Telegram ID:</b> <code>{telegram_id}</code>\n"
        "<b>Баланс:</b> {balance} {currency_symbol}\n"
        "<b>Админ:</b> {is_admin}\n"
        "<b>Всего транзакций:</b> {transaction_count}\n\n"
        "<b>Последние 10 транзакций:</b>\n{history_text}"
    ),
    "msg_admin_status_already_set": "✅ Пользователь @{username} {status} администратором.",
    "msg_admin_status_changed": "✅ Пользователь @{username} {action} администратором.",
    "msg_admin_settings_menu": "⚙️ <b>Меню настроек системы</b>",
    
    # Промпты настроек
    "msg_admin_prompt_set_welcome_bonus": "Введите новую сумму welcome-бонуса",
    "msg_admin_prompt_set_exchange_rate": "Введите новый курс обмена (например, 1.0)",
    "msg_admin_prompt_set_demurrage_rate": "Введите новый процент демерреджа (например, 1.5 для 1.5%)",
    "msg_admin_prompt_edit_welcome_bot": "Введите новый текст приветствия для бота",
    "msg_admin_prompt_edit_welcome_group": "Введите новый текст приветствия для группы",
    "msg_admin_prompt_edit_reminder": "Введите новый шаблон напоминания",
    "msg_admin_prompt_edit_activities_desc": "Введите новое описание раздела активностей",
    "msg_admin_prompt_edit_bonus_message": "Введите текст начисления бонуса",
    "msg_admin_default_activities_desc": "<b>🎨 Активности сообщества</b>\n\nВыберите направление:",
    
    "msg_admin_prompt_current_long": "✏️ {desc}:\n\n<i>Текущее значение:</i>\n<pre>{current_val}</pre>",
    "msg_admin_prompt_current_short": "✏️ {desc}:\n\n<i>Текущее значение:</i>\n<code>{current_val}</code>",
    "msg_admin_prompt_variables": "\n\n<b>Доступные переменные (нажми, чтобы скопировать):</b>\n{tips}",
    "msg_admin_demurrage_toggled": "Демерредж {status}",
    "msg_admin_welcome_group_toggled": "Приветствие в группе {status}",
    "msg_admin_demurrage_status": (
        "📊 <b>Статус демерреджа</b>\n\n"
        "<b>Состояние:</b> {enabled}\n"
        "<b>Процент:</b> {rate}%\n"
        "<b>Интервал:</b> {interval} день/дней\n"
        "<b>Последний запуск:</b> {last_run}"
    ),
    "err_admin_validation": "❌ {error_msg}",
    "msg_admin_setting_updated": "✅ Настройка успешно обновлена.",
    "err_admin_rate_validation": "Процент демерреджа должен быть от 0 до 100 (например, 1 = 1%).",
    "err_admin_negative_validation": "Значение не может быть отрицательным.",
    "err_admin_positive_validation": "Значение должно быть положительным числом.",
    "msg_admin_activities_desc_updated": "✅ Описание раздела активностей успешно обновлено!",
    "msg_admin_creating_activity": "Запускаем процесс создания активности...",
    "err_activity_not_found": "Активность не найдена.",
    "msg_admin_subscribers_header": "<b>Подписчики активности «{activity_name}»:</b>\n",
    "msg_admin_no_subscribers": "\n<i>На эту активность пока никто не подписан.</i>",
    "msg_admin_subscriber_row": "\n{index}. {username}",
    "msg_admin_subscribers_found": "Найдено {count} подписчиков.",
}
