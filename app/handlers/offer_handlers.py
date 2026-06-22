# XBalanseBot/app/handlers/offer_handlers.py
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from app.config import CURRENCY_SYMBOL, MAIN_GROUP_ID
from app.database import db
from app.lexicon import LEXICON_RU
from app.callbacks import OfferAction, GeneralAction
from app.states import OfferCreationStates
from app.keyboards import (
    get_offer_group_keyboard,
    get_offer_confirm_keyboard,
    get_offer_photo_skip_keyboard,
    get_offer_desc_skip_keyboard,
    get_offer_quantity_skip_keyboard,
    get_offer_duration_skip_keyboard,
    get_main_menu_keyboard
)
from app.utils import ensure_user_exists, get_user_balance, format_amount, add_message_ids_to_state, check_is_group_member

router = Router()
logger = logging.getLogger(__name__)

async def save_message_ids(state: FSMContext, *msg_ids: int):
    data = await state.get_data()
    capped = add_message_ids_to_state(data, *msg_ids)
    await state.update_data(message_ids=capped)

async def cleanup_offer_dialog(state: FSMContext, bot: Bot, chat_id: int):
    """Удаляет все сообщения, отправленные в ходе диалога создания объявления."""
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    if message_ids:
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=message_ids)
        except Exception as e:
            logger.warning(f"Could not delete messages in offer dialog cleanup: {e}")
    await state.clear()

async def cancel_offer_creation(event: Message | CallbackQuery, state: FSMContext, bot: Bot):
    """Общая функция отмены создания объявления."""
    chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id
    
    # Сначала удалим все сообщения диалога
    await cleanup_offer_dialog(state, bot, chat_id)
    
    # Возвращаем главное меню
    user_id = event.from_user.id
    balance = await get_user_balance(user_id)
    text = LEXICON_RU["msg_main_menu"].format(balance=format_amount(balance), currency_symbol=CURRENCY_SYMBOL)
    is_member = await check_is_group_member(bot, user_id)
    keyboard = get_main_menu_keyboard(is_member=is_member)
    
    if isinstance(event, Message):
        await event.answer(text, reply_markup=keyboard, parse_mode="HTML")
    elif isinstance(event, CallbackQuery):
        try:
            await event.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
            await event.answer()
        except Exception as e:
            logger.warning(f"Error sending main menu on offer cancel: {e}")

# --- Перехват отмены /cancel или слова cancel в состояниях OfferCreationStates ---
@router.message(Command("cancel"), StateFilter(OfferCreationStates))
@router.message(F.text.lower() == "cancel", StateFilter(OfferCreationStates))
async def cmd_cancel_offer_creation(message: Message, state: FSMContext, bot: Bot):
    await cancel_offer_creation(message, state, bot)

# --- Начало создания объявления ---
@router.callback_query(GeneralAction.filter(F.action == "menu_create_offer"))
async def start_offer_creation(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    user = await db.get_user(telegram_id=user_id)
    if not user:
        await callback.answer("❌ Сначала запустите бота в ЛС!", show_alert=True)
        return
        
    await state.clear()
    
    # Запрашиваем название
    prompt = await callback.message.answer(
        LEXICON_RU["msg_offer_prompt_title"],
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack())
        ]])
    )
    
    # Сохраняем ID сообщений для очистки
    message_ids = [callback.message.message_id, prompt.message_id]
    await state.update_data(message_ids=message_ids)
    await state.set_state(OfferCreationStates.waiting_for_title)
    await callback.answer()

# --- Ввод названия ---
@router.message(OfferCreationStates.waiting_for_title)
async def process_offer_title(message: Message, state: FSMContext, bot: Bot):
    title = (message.text or "").strip()
    if not title:
        return # Игнорируем пустые сообщения/медиа
        
    if len(title) > 120:
        title = title[:117] + "..."
        
    await state.update_data(title=title)
    
    # Запрашиваем описание
    prompt = await message.answer(
        LEXICON_RU["msg_offer_prompt_desc"],
        parse_mode="HTML",
        reply_markup=get_offer_desc_skip_keyboard()
    )
    await save_message_ids(state, message.message_id, prompt.message_id)
    await state.set_state(OfferCreationStates.waiting_for_description)

# --- Ввод описания (или пропуск) ---
@router.callback_query(GeneralAction.filter(F.action == "skip_desc"), OfferCreationStates.waiting_for_description)
async def process_offer_desc_skip(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(description=None)
    
    # Запрашиваем цену
    prompt = await callback.message.answer(
        LEXICON_RU["msg_offer_prompt_price"].format(currency_symbol=CURRENCY_SYMBOL),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack())
        ]])
    )
    await save_message_ids(state, callback.message.message_id, prompt.message_id)
    await state.set_state(OfferCreationStates.waiting_for_price)
    await callback.answer()

@router.message(OfferCreationStates.waiting_for_description)
async def process_offer_desc(message: Message, state: FSMContext, bot: Bot):
    desc = (message.text or "").strip()
    if not desc:
        return
        
    await state.update_data(description=desc)
    
    # Запрашиваем цену
    prompt = await message.answer(
        LEXICON_RU["msg_offer_prompt_price"].format(currency_symbol=CURRENCY_SYMBOL),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack())
        ]])
    )
    await save_message_ids(state, message.message_id, prompt.message_id)
    await state.set_state(OfferCreationStates.waiting_for_price)

# --- Ввод цены ---
@router.message(OfferCreationStates.waiting_for_price)
async def process_offer_price(message: Message, state: FSMContext, bot: Bot):
    price_str = (message.text or "").strip().replace(",", ".")
    try:
        price = Decimal(price_str)
        if price <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        # Ошибка ввода цены
        prompt = await message.answer(
            LEXICON_RU["err_offer_price_invalid"],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack())
            ]])
        )
        await save_message_ids(state, message.message_id, prompt.message_id)
        return
        
    await state.update_data(price=float(price))
    
    # Запрашиваем количество
    prompt = await message.answer(
        LEXICON_RU["msg_offer_prompt_quantity"],
        parse_mode="HTML",
        reply_markup=get_offer_quantity_skip_keyboard()
    )
    await save_message_ids(state, message.message_id, prompt.message_id)
    await state.set_state(OfferCreationStates.waiting_for_quantity)


# --- Ввод количества (или пропуск) ---
@router.callback_query(GeneralAction.filter(F.action == "skip_quantity"), OfferCreationStates.waiting_for_quantity)
async def process_offer_quantity_skip(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(quantity=1)
    
    # Запрашиваем срок действия
    prompt = await callback.message.answer(
        LEXICON_RU["msg_offer_prompt_duration"],
        parse_mode="HTML",
        reply_markup=get_offer_duration_skip_keyboard()
    )
    await save_message_ids(state, callback.message.message_id, prompt.message_id)
    await state.set_state(OfferCreationStates.waiting_for_duration)
    await callback.answer()


@router.message(OfferCreationStates.waiting_for_quantity)
async def process_offer_quantity(message: Message, state: FSMContext, bot: Bot):
    qty_str = (message.text or "").strip()
    try:
        quantity = int(qty_str)
        if quantity <= 0:
            raise ValueError()
    except ValueError:
        # Ошибка ввода количества
        prompt = await message.answer(
            LEXICON_RU["err_offer_quantity_invalid"],
            reply_markup=get_offer_quantity_skip_keyboard()
        )
        await save_message_ids(state, message.message_id, prompt.message_id)
        return
        
    await state.update_data(quantity=quantity)
    
    # Запрашиваем срок действия
    prompt = await message.answer(
        LEXICON_RU["msg_offer_prompt_duration"],
        parse_mode="HTML",
        reply_markup=get_offer_duration_skip_keyboard()
    )
    await save_message_ids(state, message.message_id, prompt.message_id)
    await state.set_state(OfferCreationStates.waiting_for_duration)


# --- Ввод срока действия (или пропуск) ---
@router.callback_query(GeneralAction.filter(F.action == "skip_duration"), OfferCreationStates.waiting_for_duration)
async def process_offer_duration_skip(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(duration_days=14)
    
    # Запрашиваем фото
    prompt = await callback.message.answer(
        LEXICON_RU["msg_offer_prompt_photo"],
        parse_mode="HTML",
        reply_markup=get_offer_photo_skip_keyboard()
    )
    await save_message_ids(state, callback.message.message_id, prompt.message_id)
    await state.set_state(OfferCreationStates.waiting_for_photo)
    await callback.answer()


@router.message(OfferCreationStates.waiting_for_duration)
async def process_offer_duration(message: Message, state: FSMContext, bot: Bot):
    dur_str = (message.text or "").strip()
    try:
        duration_days = int(dur_str)
        if duration_days <= 0:
            raise ValueError()
    except ValueError:
        # Ошибка ввода срока действия
        prompt = await message.answer(
            LEXICON_RU["err_offer_duration_invalid"],
            reply_markup=get_offer_duration_skip_keyboard()
        )
        await save_message_ids(state, message.message_id, prompt.message_id)
        return
        
    await state.update_data(duration_days=duration_days)
    
    # Запрашиваем фото
    prompt = await message.answer(
        LEXICON_RU["msg_offer_prompt_photo"],
        parse_mode="HTML",
        reply_markup=get_offer_photo_skip_keyboard()
    )
    await save_message_ids(state, message.message_id, prompt.message_id)
    await state.set_state(OfferCreationStates.waiting_for_photo)


# --- Ввод фото (или пропуск) ---
async def show_offer_preview(chat_id: int, state: FSMContext, bot: Bot):
    """Показывает предпросмотр объявления перед подтверждением публикации."""
    data = await state.get_data()
    title = data['title']
    description = data.get('description')
    price = data['price']
    quantity = data.get('quantity', 1)
    duration_days = data.get('duration_days', 14)
    photo_id = data.get('photo_id')
    message_ids = data.get('message_ids', [])
    
    escaped_title = escape(title)
    escaped_desc = escape(description) if description else ""
    desc_part = f"<b>Описание:</b> {escaped_desc}\n" if description else ""
    
    user = await db.get_user(telegram_id=chat_id)
    raw_seller_username = user['username'] if user and user['username'] else f"id{chat_id}"
    seller_username = escape(raw_seller_username)
    
    quantity_part = f"<b>Количество:</b> {quantity} шт.\n" if quantity > 1 else ""
    
    from datetime import datetime, timedelta
    expires_dt = datetime.now() + timedelta(days=duration_days)
    expires_str = expires_dt.strftime("%d.%m.%Y")
    expiry_part = f"<b>Срок действия:</b> до {expires_str}\n"
    
    card_text = LEXICON_RU["msg_offer_card"].format(
        title=escaped_title,
        desc_part=desc_part,
        price=price,
        currency_symbol=CURRENCY_SYMBOL,
        seller_username=seller_username,
        quantity_part=quantity_part,
        expiry_part=expiry_part
    )
    
    preview_text = LEXICON_RU["msg_offer_preview_header"] + card_text + LEXICON_RU["msg_offer_preview_confirm"]
    
    keyboard = get_offer_confirm_keyboard(offer_id=0) # 0 означает, что объявление еще не создано в БД
    
    if photo_id:
        prompt = await bot.send_photo(
            chat_id=chat_id,
            photo=photo_id,
            caption=preview_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        prompt = await bot.send_message(
            chat_id=chat_id,
            text=preview_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
    capped = add_message_ids_to_state({'message_ids': message_ids}, prompt.message_id)
    await state.update_data(message_ids=capped, confirm_msg_id=prompt.message_id)
    await state.set_state(OfferCreationStates.waiting_for_confirmation)


@router.callback_query(GeneralAction.filter(F.action == "skip_photo"), OfferCreationStates.waiting_for_photo)
async def process_offer_photo_skip(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(photo_id=None)
    await save_message_ids(state, callback.message.message_id)
    await show_offer_preview(callback.message.chat.id, state, bot)
    await callback.answer()


@router.message(OfferCreationStates.waiting_for_photo)
async def process_offer_photo(message: Message, state: FSMContext, bot: Bot):
    if not message.photo:
        # Требуем именно фото
        prompt = await message.answer(
            LEXICON_RU["err_offer_photo_invalid"],
            reply_markup=get_offer_photo_skip_keyboard()
        )
        await save_message_ids(state, message.message_id, prompt.message_id)
        return
        
    # Берем фото наибольшего разрешения (последнее в списке)
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await save_message_ids(state, message.message_id)
    await show_offer_preview(message.chat.id, state, bot)


# --- Подтверждение публикации (кнопка Опубликовать) ---
@router.callback_query(OfferAction.filter(F.action == "publish"), OfferCreationStates.waiting_for_confirmation)
async def process_offer_publish(callback: CallbackQuery, callback_data: OfferAction, state: FSMContext, bot: Bot):
    data = await state.get_data()
    title = data['title']
    description = data.get('description')
    price = data['price']
    photo_id = data.get('photo_id')
    quantity = data.get('quantity', 1)
    duration_days = data.get('duration_days', 14)
    
    user_id = callback.from_user.id
    user = await db.get_user(telegram_id=user_id)
    if not user:
        await callback.answer("Ошибка пользователя.")
        return
        
    # 1. Создаем предложение в базе данных
    try:
        offer_id = await db.create_offer(
            seller_telegram_id=user_id,
            title=title,
            description=description,
            price=price,
            photo_id=photo_id,
            quantity=quantity,
            duration_days=duration_days
        )
    except Exception as e:
        logger.error(f"Error creating offer: {e}")
        await callback.answer("❌ Произошла ошибка при сохранении объявления.")
        return
        
    # 2. Очищаем диалог создания в ЛС
    await cleanup_offer_dialog(state, bot, callback.message.chat.id)
    
    # 3. Форматируем карточку для группы
    offer = await db.get_offer(offer_id)
    expires_str = offer['expires_at'].strftime("%d.%m.%Y")
    
    quantity_part = f"<b>Количество:</b> {quantity} шт.\n" if quantity > 1 else ""
    expiry_part = f"<b>Срок действия:</b> до {expires_str}\n"
    
    escaped_title = escape(title)
    escaped_desc = escape(description) if description else ""
    desc_part = f"<b>Описание:</b> {escaped_desc}\n" if description else ""
    raw_seller_username = user['username'] if user['username'] else f"id{user_id}"
    seller_username = escape(raw_seller_username)
    card_text = LEXICON_RU["msg_offer_card"].format(
        title=escaped_title,
        desc_part=desc_part,
        price=price,
        currency_symbol=CURRENCY_SYMBOL,
        seller_username=seller_username,
        quantity_part=quantity_part,
        expiry_part=expiry_part
    )
    
    keyboard = get_offer_group_keyboard(offer_id, price)
    
    # Получаем ID топика для биржи обмена
    market_thread_str = await db.get_setting("market_thread_id")
    message_thread_id = None
    if market_thread_str and market_thread_str.isdigit():
        thread_val = int(market_thread_str)
        if thread_val > 0:
            message_thread_id = thread_val
            
    # 4. Отправляем в группу
    try:
        if photo_id:
            msg = await bot.send_photo(
                chat_id=MAIN_GROUP_ID,
                photo=photo_id,
                caption=card_text,
                parse_mode="HTML",
                reply_markup=keyboard,
                message_thread_id=message_thread_id
            )
        else:
            msg = await bot.send_message(
                chat_id=MAIN_GROUP_ID,
                text=card_text,
                parse_mode="HTML",
                reply_markup=keyboard,
                message_thread_id=message_thread_id
            )
            
        # Записываем ID сообщения в БД
        await db.update_offer_message(offer_id, int(MAIN_GROUP_ID), msg.message_id)
    except Exception as e:
        logger.error(f"Error publishing offer to group: {e}")
        await callback.message.answer("⚠️ Объявление сохранено, но не удалось опубликовать его в группе. Обратитесь к администратору.")
        return
        
    # 5. Сообщаем об успехе
    await callback.message.answer(LEXICON_RU["msg_offer_created_success"])
    await callback.answer()


# --- Отмена диалога создания (по кнопке Отмена) ---
@router.callback_query(GeneralAction.filter(F.action == "cancel_dialog"), OfferCreationStates)
async def process_offer_cancel_btn(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await cancel_offer_creation(callback, state, bot)


# --- Покупка предложения (Callback в группе) ---
@router.callback_query(OfferAction.filter(F.action == "buy"))
async def process_offer_buy(callback: CallbackQuery, callback_data: OfferAction, bot: Bot):
    buyer_telegram_id = callback.from_user.id
    offer_id = callback_data.offer_id
    
    # Сначала проверяем, зарегистрирован ли покупатель
    buyer = await db.get_user(telegram_id=buyer_telegram_id)
    if not buyer:
        await callback.answer("❌ Сначала запустите бота в личных сообщениях!", show_alert=True)
        return
        
    try:
        # Выполняем покупку в атомарной транзакции
        res = await db.execute_offer_purchase(offer_id, buyer_telegram_id)
        
        offer = res['offer']
        seller = res['seller']
        buyer = res['buyer']
        price = res['price']
        remaining_quantity = res['remaining_quantity']
        
        # Сделка успешна!
        # 1. Отвечаем во всплывающем окне
        await callback.answer("✅ Покупка успешно совершена!", show_alert=True)
        
        # 2. Обновляем сообщение в группе
        raw_seller_username = seller['username'] if seller['username'] else f"id{seller['telegram_id']}"
        raw_buyer_username = buyer['username'] if buyer['username'] else f"id{buyer['telegram_id']}"
        seller_username = escape(raw_seller_username)
        buyer_username = escape(raw_buyer_username)
        
        escaped_title = escape(offer['title'])
        
        if remaining_quantity > 0:
            # Сделка совершена, но товар еще остался
            escaped_desc = escape(offer['description']) if offer['description'] else ""
            desc_part = f"<b>Описание:</b> {escaped_desc}\n" if offer['description'] else ""
            quantity_part = f"<b>Количество:</b> {remaining_quantity} шт.\n" if remaining_quantity > 1 else ""
            
            expires_str = offer['expires_at'].strftime("%d.%m.%Y")
            expiry_part = f"<b>Срок действия:</b> до {expires_str}\n"
            
            updated_card_text = LEXICON_RU["msg_offer_card"].format(
                title=escaped_title,
                desc_part=desc_part,
                price=price,
                currency_symbol=CURRENCY_SYMBOL,
                seller_username=seller_username,
                quantity_part=quantity_part,
                expiry_part=expiry_part
            )
            keyboard = get_offer_group_keyboard(offer_id, price)
            
            try:
                if offer['photo_id']:
                    await bot.edit_message_caption(
                        chat_id=callback.message.chat.id,
                        message_id=callback.message.message_id,
                        caption=updated_card_text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                else:
                    await bot.edit_message_text(
                        chat_id=callback.message.chat.id,
                        message_id=callback.message.message_id,
                        text=updated_card_text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
            except Exception as e:
                logger.error(f"Error editing message caption on decrement: {e}")
        else:
            # Товара больше нет — сделка полностью завершена
            sold_text = LEXICON_RU["msg_offer_card_sold"].format(
                title=escaped_title,
                seller_username=seller_username,
                buyer_username=buyer_username,
                price=price,
                currency_symbol=CURRENCY_SYMBOL
            )
            
            try:
                if offer['photo_id']:
                    await bot.edit_message_caption(
                        chat_id=callback.message.chat.id,
                        message_id=callback.message.message_id,
                        caption=sold_text,
                        parse_mode="HTML",
                        reply_markup=None # Убираем кнопку
                    )
                else:
                    await bot.edit_message_text(
                        chat_id=callback.message.chat.id,
                        message_id=callback.message.message_id,
                        text=sold_text,
                        parse_mode="HTML",
                        reply_markup=None # Убираем кнопку
                    )
            except Exception as e:
                logger.error(f"Error editing message to sold: {e}")
            
        # 3. Отправляем уведомления продавцу и покупателю
        # Продавцу
        seller_notified = True
        try:
            await bot.send_message(
                chat_id=seller['telegram_id'],
                text=LEXICON_RU["msg_offer_purchase_success_seller"].format(
                    title=offer['title'],
                    buyer_username=buyer_username,
                    price=price,
                    currency_symbol=CURRENCY_SYMBOL
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Could not notify seller {seller['telegram_id']}: {e}")
            seller_notified = False
            
        # Покупателю
        try:
            buyer_msg = LEXICON_RU["msg_offer_purchase_success_buyer"].format(
                title=offer['title'],
                seller_username=seller_username,
                price=price,
                currency_symbol=CURRENCY_SYMBOL
            )
            if not seller_notified:
                buyer_msg += LEXICON_RU["warning_seller_not_notified"].format(seller_username=seller_username)
                
            await bot.send_message(
                chat_id=buyer['telegram_id'],
                text=buyer_msg,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Could not notify buyer {buyer['telegram_id']}: {e}")
            
    except ValueError as e:
        err_msg = str(e)
        if err_msg == "cannot_buy_own_offer":
            await callback.answer(LEXICON_RU["err_offer_own_purchase"], show_alert=True)
        elif err_msg == "insufficient_funds":
            await callback.answer(LEXICON_RU["err_offer_insufficient_funds"], show_alert=True)
        elif err_msg == "offer_already_sold":
            await callback.answer(LEXICON_RU["err_offer_already_sold"], show_alert=True)
        elif err_msg == "offer_already_cancelled":
            await callback.answer(LEXICON_RU["err_offer_already_cancelled"], show_alert=True)
        elif err_msg == "offer_not_found":
            await callback.answer(LEXICON_RU["err_offer_not_found"], show_alert=True)
        elif err_msg == "offer_expired":
            await callback.answer(LEXICON_RU["err_offer_expired"], show_alert=True)
        else:
            logger.error(f"Purchase error: {err_msg}")
            await callback.answer("❌ Ошибка при проведении сделки.", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected purchase error: {e}")
        await callback.answer("❌ Произошла непредвиденная ошибка.", show_alert=True)
