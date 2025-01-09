import asyncio
import logging
from datetime import datetime, timedelta
from telegram.constants import ParseMode

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler
)

# --------------------------
# 1) НАСТРОЙКИ
# --------------------------
BOT_TOKEN = "7849237623:AAHWd4Gxpczi0QLYFRLEMCXFF611BQQFfMQ"
# КАНАЛ, где бот админ (для публикации аукционов)
CHANNEL_ID = -1002260175630

# Список пользователей, которым разрешено создавать лоты
ALLOWED_USERS = [
    7325459648,
    6862418031,
    1403489343,
    6291760993
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --------------------------
# 2) ХРАНИЛИЩЕ (в памяти)
# --------------------------
USERS = {
    # chat_id: {
    #   "balance": int,
    #   "lots": [lot_id, ...],
    #   "lang": "ru"/"en",
    #   "settings": {
    #       "antisniper": int (сек),
    #       "currency": "USDT"/"TON",
    #       "rules": str,
    #       "notifications": bool,
    #       "blacklist": [...],
    #   }
    # }
}
LOTS = {
    # lot_id: {
    #   "owner_id": int,
    #   "media_type": "photo"/"video",
    #   "file_id": str,
    #   "description": str,
    #   "is_ended": bool,
    #   "end_time": datetime,
    #   "message_id": int (в канале),
    #   "bids": { user_id: {"username": str, "amount": int} }
    # }
}
NEXT_LOT_ID = 1

# --------------------------
# 3) СТЕЙТЫ (ConversationHandler)
# --------------------------
(
    STATE_MENU,
    STATE_CREATE_ASK_DURATION,
    STATE_CREATE_WAIT_MEDIA,
    STATE_CREATE_WAIT_DESCRIPTION,

    STATE_SETTINGS_MENU,
    STATE_SETTINGS_ANTISNIPER,
    STATE_SETTINGS_RULES,
    STATE_SETTINGS_BLACKLIST,
    STATE_SETTINGS_NOTIFICATIONS,
    STATE_SETTINGS_CURRENCY,
    STATE_SETTINGS_LANGUAGE,
) = range(11)

# Доступные варианты длительности (в минутах)
DURATION_CHOICES = {
    "1m": 1,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "5h": 300,
    "6h": 360,
    "12h": 720,
    "24h": 1440,
    "7d": 10080
}


# --------------------------
# 4) ДВЕ ЯЗЫКОВЫЕ ВЕРСИИ СООБЩЕНИЙ
# --------------------------
MESSAGES = {
    "ru": {
        "start": (
            "🔴 **NIKE AUCTIONS** 🔴\n\n"
            "Привет! Я бот для проведения аукционов.\n"
            "У меня есть настройки (антиснайпер, валюта, правила) и поддержка двух языков.\n\n"
            "Выберите действие из меню."
            "Бота разработал @off\_vakuum для @nike\_nikov"
        ),
        "help": (
            "Список команд:\n"
            "• /start — Главное меню\n"
            "• /help — Помощь\n\n"
            "**Из меню:**\n"
            "- Создать лот — начать аукцион\n"
            "- Мои лоты — посмотреть аукционы\n"
            "- Пополнить баланс — псевдо-пополнение\n"
            "- Настройки — антиснайпер, валюта, правила, язык\n"
        ),
        "main_menu": "Выберите действие из меню:",
        "only_allowed": "У вас нет прав для создания лотов.",
        "no_lots": "У вас пока нет лотов.",
        "balance_topped": "Баланс пополнен на 10 $. Текущий баланс: {bal} $",
        "ask_duration": "Выберите, на какой срок создать аукцион:",
        "enter_media": "Отправьте фото или видео для лота.",
        "enter_desc": "Отправьте текст-описание лота.",
        "lot_published": "Лот опубликован в канале!\nУдачных ставок!",
        "lot_cancelled": "Создание лота отменено.",
        "settings_title": "⚙ **Настройки** ⚙",
        "antisniper_info": "Антиснайпер продлевает аукцион на N секунд после последней ставки.\nУкажите число от 0 до 3600.",
        "currency_info": "Выберите валюту для аукционов:",
        "rules_info": "Отправьте новый текст правил аукциона:",
        "rules_updated": "Правила обновлены!",
        "notifications_info": "Вкл/выкл уведомления (демо).",
        "blacklist_info": "Добавить/удалить пользователей (демо).",
        "lang_info": "Выберите язык / Choose language:",
        "lang_switched_ru": "Язык переключён на **русский** (ru).",
        "lang_switched_en": "Язык переключён на **английский** (en).",
        "back": "« Назад",
        "currency_set": "Валюта сохранена: {curr}",
        "antisniper_set": "Антиснайпер установлен: {val} сек",
        "bid_ended": "Аукцион уже завершён!",
        "lot_not_found": "Лот не найден.",
        "time_left": "До конца аукциона осталось: {time}",
        "rules_text": (
            "1. Делая ставку, вы подтверждаете намерение купить.\n"
            "2. В случае отказа — блокировка.\n"
            "3. Доставка за счёт покупателя.\n"
        ),
        "info_example": (
            "Пример лота:\n\n"
            "🖥 **MacBook Air**\n"
            "Стартовая цена: `10`, шаги: `1,5,10`\n"
            "Макс. цена: `200`\n"
            "Валюта: USDT\n"
            "Топ-3 ставок:\n"
            "1) 23$ (M3n)\n"
            "2) 20$ (miu)\n"
            "3) 19$ (SS*)\n"
        ),
    },
    "en": {
        "start": (
            "🔴 **AUCTION 24** 🔴\n\n"
            "Hello! I'm an auction bot.\n"
            "I have settings (anti-sniper, currency, rules) and support for two languages.\n\n"
            "Choose an action from the menu."
        ),
        "help": (
            "Commands:\n"
            "• /start — Main menu\n"
            "• /help — Help\n\n"
            "**From menu:**\n"
            "- Create Lot — start an auction\n"
            "- My Lots — see your auctions\n"
            "- Topup balance — pseudo-topup\n"
            "- Settings — antisniper, currency, rules, language\n"
        ),
        "main_menu": "Choose an action from the menu:",
        "only_allowed": "You have no permission to create lots.",
        "no_lots": "You have no lots yet.",
        "balance_topped": "Balance topped up by 10 $. Current: {bal} $",
        "ask_duration": "Choose auction duration:",
        "enter_media": "Send photo or video for the lot.",
        "enter_desc": "Send lot description text.",
        "lot_published": "Lot published in channel!\nGood luck!",
        "lot_cancelled": "Lot creation cancelled.",
        "settings_title": "⚙ **Settings** ⚙",
        "antisniper_info": "Anti-sniper extends the auction N seconds after the last bid.\nEnter 0..3600.",
        "currency_info": "Choose currency for auctions:",
        "rules_info": "Send new auction rules text:",
        "rules_updated": "Rules updated!",
        "notifications_info": "Enable/disable notifications (demo).",
        "blacklist_info": "Add/remove users (demo).",
        "lang_info": "Choose language / Выберите язык:",
        "lang_switched_ru": "Language switched to **Russian** (ru).",
        "lang_switched_en": "Language switched to **English** (en).",
        "back": "« Back",
        "currency_set": "Currency set: {curr}",
        "antisniper_set": "Antisniper set: {val} sec",
        "bid_ended": "Auction ended!",
        "lot_not_found": "Lot not found.",
        "time_left": "Time left: {time}",
        "rules_text": (
            "1. By bidding, you confirm your intent to buy.\n"
            "2. In case of refusal — block.\n"
            "3. Delivery is paid by buyer.\n"
        ),
        "info_example": (
            "Lot example:\n\n"
            "🖥 **MacBook Air**\n"
            "Start price: `10`, steps: `1,5,10`\n"
            "Max price: `200`\n"
            "Currency: USDT\n"
            "Top-3 bids:\n"
            "1) 23$ (M3n)\n"
            "2) 20$ (miu)\n"
            "3) 19$ (SS*)\n"
        ),
    }
}

# --------------------------
# 5) ФУНКЦИИ ДЛЯ РАБОТЫ С ЯЗЫКОМ
# --------------------------
def get_lang(chat_id: int) -> str:
    if chat_id not in USERS:
        USERS[chat_id] = {
            "balance": 0,
            "lots": [],
            "lang": "ru",
            "settings": {
                "antisniper": 0,
                "currency": "USDT",
                "rules": MESSAGES["ru"]["rules_text"],  # по умолчанию
                "notifications": True,
                "blacklist": []
            }
        }
    return USERS[chat_id].get("lang", "ru")

def L(chat_id, key, **kwargs) -> str:
    """Упрощённый доступ к словарю MESSAGES, с подстановкой параметров."""
    lang = get_lang(chat_id)
    text = MESSAGES[lang].get(key, f"??{key}??")
    if kwargs:
        return text.format(**kwargs)
    return text


# --------------------------
# 6) КНОПКИ МЕНЮ
# --------------------------
def main_menu_kb(chat_id: int) -> ReplyKeyboardMarkup:
    """Главное меню (в зависимости от языка)."""
    lang = get_lang(chat_id)
    if lang == "ru":
        buttons = [
            ["Создать лот", "Мои лоты"],
            ["Пополнить баланс", "Настройки"],
            ["Помощь"]
        ]
    else:
        buttons = [
            ["Create Lot", "My Lots"],
            ["Topup balance", "Settings"],
            ["Help"]
        ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def settings_inline_kb(chat_id: int) -> InlineKeyboardMarkup:
    """Инлайн-клавиатура настроек."""
    lang = get_lang(chat_id)
    s = USERS[chat_id]["settings"]
    antisniper_str = s["antisniper"]
    currency_str = s["currency"]
    # Выводим настройки

    btn_antisniper = f"Антиснайпер: {antisniper_str} сек" if lang == "ru" else f"Antisniper: {antisniper_str} sec"
    btn_currency = f"Валюта: {currency_str}" if lang == "ru" else f"Currency: {currency_str}"
    btn_rules = "Изменить правила" if lang == "ru" else "Change rules"
    btn_blacklist = "Чёрный список" if lang == "ru" else "Blacklist"
    btn_notif = "Уведомления" if lang == "ru" else "Notifications"
    btn_lang = "Язык" if lang == "ru" else "Language"
    btn_back = L(chat_id, "back")

    buttons = [
        [InlineKeyboardButton(btn_antisniper, callback_data="set_antisniper")],
        [InlineKeyboardButton(btn_currency, callback_data="set_currency")],
        [InlineKeyboardButton(btn_rules, callback_data="set_rules")],
        [InlineKeyboardButton(btn_blacklist, callback_data="set_blacklist")],
        [InlineKeyboardButton(btn_notif, callback_data="set_notifications")],
        [InlineKeyboardButton(btn_lang, callback_data="set_language")],
        [InlineKeyboardButton(btn_back, callback_data="settings_back")]
    ]
    return InlineKeyboardMarkup(buttons)

def currency_kb(chat_id: int) -> InlineKeyboardMarkup:
    lang = get_lang(chat_id)
    txt_back = L(chat_id, "back")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("USDT", callback_data="currency_usdt"),
            InlineKeyboardButton("TON", callback_data="currency_ton")
        ],
        [InlineKeyboardButton(txt_back, callback_data="currency_back")]
    ])

def language_inline_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Русский", callback_data="lang_ru"),
            InlineKeyboardButton("English", callback_data="lang_en")
        ]
    ])


# --------------------------
# 7) ЛОГИКА АУКЦИОНОВ
# --------------------------
def partial_username(full_username: str, user_id: int) -> str:
    """Вернём первые 3 символа username или часть user_id."""
    if full_username:
        return full_username[:3]
    else:
        return str(user_id)[:3]

def build_top3_string(lot_id: int, chat_id: int) -> str:
    """Формирует строку вида «Топ-3 ставок: …» с обрезанными никами."""
    lang = get_lang(chat_id)
    lot = LOTS[lot_id]
    bids_dict = lot["bids"]
    if not bids_dict:
        return "Ставок ещё нет." if lang == "ru" else "No bids yet."

    # сортируем
    sorted_bids = sorted(bids_dict.values(), key=lambda x: x["amount"], reverse=True)
    top3 = sorted_bids[:3]
    lines = []
    if lang == "ru":
        lines.append("Топ-3 ставок:")
    else:
        lines.append("Top-3 bids:")
    place = 1
    for b in top3:
        amt = b["amount"]
        short_name = partial_username(b["username"], 0)
        lines.append(f"{place}) {amt}$ ({short_name})")
        place += 1
    return "\n".join(lines)

def get_time_remaining_str(end_time: datetime, chat_id: int) -> str:
    lang = get_lang(chat_id)
    now = datetime.utcnow()
    diff = end_time - now
    if diff.total_seconds() <= 0:
        return "0 мин" if lang == "ru" else "0 min"
    secs = int(diff.total_seconds())
    hours = secs // 3600
    mins = (secs % 3600) // 60
    if hours > 0:
        if lang == "ru":
            return f"{hours} ч {mins} мин"
        else:
            return f"{hours} h {mins} min"
    else:
        if lang == "ru":
            return f"{mins} мин"
        else:
            return f"{mins} min"

def build_lot_caption(lot_id: int, chat_id: int) -> str:
    """Формируем заголовок лота (в канале)."""
    lang = get_lang(chat_id)
    lot = LOTS[lot_id]
    remain = get_time_remaining_str(lot["end_time"], chat_id)
    header = f"**Лот #{lot_id}** (Осталось: {remain})\n\n" if lang == "ru" else f"**Lot #{lot_id}** (Time left: {remain})\n\n"
    desc = lot["description"] + "\n\n"
    top3 = build_top3_string(lot_id, chat_id)
    return header + desc + top3

def get_auction_keyboard(lot_id: int, chat_id: int) -> InlineKeyboardMarkup:
    """Кнопки: +1, +3, +5; антиснайпер учитываем отдельно; кнопка ℹ для инфо, ⌛ для таймера."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("+1", callback_data=f"bid_{lot_id}_1"),
            InlineKeyboardButton("+3", callback_data=f"bid_{lot_id}_3"),
            InlineKeyboardButton("+5", callback_data=f"bid_{lot_id}_5"),
        ],
        [
            InlineKeyboardButton("ℹ Info", callback_data=f"info_{lot_id}"),
            InlineKeyboardButton("⌛", callback_data=f"timer_{lot_id}")
        ]
    ])

async def schedule_auction_end(context: ContextTypes.DEFAULT_TYPE, lot_id: int, duration_minutes: int):
    """Запускаем таймер, по окончании завершаем аукцион."""
    await asyncio.sleep(duration_minutes * 60)  # минуты -> сек
    lot = LOTS.get(lot_id)
    if lot and not lot["is_ended"]:
        await end_auction(context, lot_id)

async def end_auction(context: ContextTypes.DEFAULT_TYPE, lot_id: int):
    """Закрываем лот, уведомляем владельца."""
    lot = LOTS[lot_id]
    lot["is_ended"] = True
    owner_id = lot["owner_id"]
    chat_lang = get_lang(owner_id)

    # Меняем сообщение в канале
    top3_str = build_top3_string(lot_id, owner_id)
    new_caption = f"**Лот #{lot_id}**\n\n{lot['description']}\n\n{top3_str}\n\n"
    new_caption += "Аукцион завершён!" if chat_lang == "ru" else "Auction ended!"

    try:
        await context.bot.edit_message_caption(
            chat_id=CHANNEL_ID,
            message_id=lot["message_id"],
            caption=new_caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=None
        )
    except Exception as e:
        logging.warning(f"Cannot edit message in channel: {e}")

    # формируем топ-3 ПОЛНОСТЬЮ для владельца
    full_top3 = get_full_top3(lot_id)
    if full_top3:
        text_owner = (
            f"Лот #{lot_id} завершён!\n\nТоп-3:\n{full_top3}\n" if chat_lang == "ru"
            else f"Lot #{lot_id} ended!\n\nTop-3:\n{full_top3}\n"
        )
    else:
        text_owner = f"Лот #{lot_id} завершён. Ставок не было." if chat_lang == "ru" else f"Lot #{lot_id} ended. No bids."

    try:
        await context.bot.send_message(owner_id, text_owner)
    except Exception as e:
        logging.warning(f"Cannot notify owner: {e}")

def get_full_top3(lot_id: int) -> str:
    """Возвращает топ-3 ставок c ПОЛНЫМИ никнеймами (для владельца)."""
    lot = LOTS[lot_id]
    bids = lot["bids"]
    if not bids:
        return ""
    sorted_bids = sorted(bids.values(), key=lambda x: x["amount"], reverse=True)
    top3 = sorted_bids[:3]
    lines = []
    place = 1
    for b in top3:
        amt = b["amount"]
        username = b["username"] if b["username"] else "User??"
        lines.append(f"{place}) {amt}$ — @{username}")
        place += 1
    return "\n".join(lines)

async def apply_antisniper(context: ContextTypes.DEFAULT_TYPE, lot_id: int, chat_id: int):
    """Если антиснайпер > 0, и до конца < антиснайпер, то продлеваем."""
    antisniper_val = USERS[chat_id]["settings"]["antisniper"]
    if antisniper_val <= 0:
        return  # не активен

    lot = LOTS[lot_id]
    now = datetime.utcnow()
    remain_secs = (lot["end_time"] - now).total_seconds()
    if remain_secs < antisniper_val:
        # продлеваем на antisniper_val
        new_end = now + timedelta(seconds=antisniper_val)
        lot["end_time"] = new_end
        # перезапустить таймер сложнее (надо хранить Task), но для демо пропустим
        # или можно добавить еще + (antisniper_val - remain_secs), но обычно логика "установить end_time = now + antisniper_val"
        logging.info("Antisniper triggered. Extended lot %s by %s seconds", lot_id, antisniper_val)


# --------------------------
# 8) Хэндлеры команд и меню
# --------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_lang(chat_id)  # ensure user
    text = L(chat_id, "start")
    await update.message.reply_text(text, reply_markup=main_menu_kb(chat_id), parse_mode=ParseMode.MARKDOWN)
    return STATE_MENU

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = L(chat_id, "help")
    await update.message.reply_text(text, reply_markup=main_menu_kb(chat_id), parse_mode=ParseMode.MARKDOWN)
    return STATE_MENU

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Реакция на кнопки главного меню."""
    chat_id = update.effective_chat.id
    msg_text = update.message.text.strip().lower()
    lang = get_lang(chat_id)

    if msg_text in ["создать лот", "create lot"]:
        # Проверяем, есть ли право
        if chat_id not in ALLOWED_USERS:
            await update.message.reply_text(L(chat_id, "only_allowed"), reply_markup=main_menu_kb(chat_id))
            return STATE_MENU

        # Выбор продолжительности
        text = L(chat_id, "ask_duration")
        # сделаем кнопки с популярными вариантами
        buttons = [
            [InlineKeyboardButton("1 мин", callback_data="dur_1m"), InlineKeyboardButton("15 мин", callback_data="dur_15m")],
            [InlineKeyboardButton("30 мин", callback_data="dur_30m"), InlineKeyboardButton("1 час", callback_data="dur_1h")],
            [InlineKeyboardButton("2 часа", callback_data="dur_2h"), InlineKeyboardButton("5 часов", callback_data="dur_5h")],
            [InlineKeyboardButton("6 часов", callback_data="dur_6h"), InlineKeyboardButton("12 часов", callback_data="dur_12h")],
            [InlineKeyboardButton("Сутки", callback_data="dur_24h"), InlineKeyboardButton("Неделя", callback_data="dur_7d")],
            [InlineKeyboardButton(L(chat_id, "back"), callback_data="dur_cancel")]
        ]
        markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(text, reply_markup=markup)
        return STATE_CREATE_ASK_DURATION

    elif msg_text in ["мои лоты", "my lots"]:
        user_lots = USERS[chat_id]["lots"]
        if not user_lots:
            await update.message.reply_text(L(chat_id, "no_lots"), reply_markup=main_menu_kb(chat_id))
            return STATE_MENU
        await update.message.reply_text("...", reply_markup=ReplyKeyboardRemove())
        for lot_id in user_lots:
            lot = LOTS[lot_id]
            status = "Завершён" if lot["is_ended"] else "Активен"
            text2 = f"Лот #{lot_id} — {status}\n{lot['description']}\n"
            remain = get_time_remaining_str(lot["end_time"], chat_id)
            if not lot["is_ended"]:
                text2 += f"(Осталось: {remain})\n"
            top3 = build_top3_string(lot_id, chat_id)
            text2 += top3
            await update.message.reply_text(text2)
        await update.message.reply_text("OK", reply_markup=main_menu_kb(chat_id))
        return STATE_MENU

    elif msg_text in ["пополнить баланс", "topup balance"]:
        USERS[chat_id]["balance"] += 10
        bal = USERS[chat_id]["balance"]
        await update.message.reply_text(L(chat_id, "balance_topped", bal=bal), reply_markup=main_menu_kb(chat_id))
        return STATE_MENU

    elif msg_text in ["настройки", "settings"]:
        await update.message.reply_text(L(chat_id, "settings_title"), reply_markup=settings_inline_kb(chat_id), parse_mode=ParseMode.MARKDOWN)
        return STATE_SETTINGS_MENU

    elif msg_text in ["помощь", "help"]:
        return await help_command(update, context)

    else:
        await update.message.reply_text(L(chat_id, "main_menu"), reply_markup=main_menu_kb(chat_id))
        return STATE_MENU


# ---- Выбор длительности аукциона (CallbackQuery) ----
async def duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data  # dur_1m / dur_cancel
    chat_id = query.message.chat_id
    await query.answer()

    if data == "dur_cancel":
        await query.edit_message_text(L(chat_id, "lot_cancelled"))
        return STATE_MENU

    # data = "dur_1m", ...
    suffix = data.split("_")[1]  # 1m / 15m / etc
    if suffix not in DURATION_CHOICES:
        await query.edit_message_text("Error choosing time.")
        return STATE_MENU

    context.user_data["duration_minutes"] = DURATION_CHOICES[suffix]
    # Следующий шаг - ждем фото/видео
    await query.edit_message_text(L(chat_id, "enter_media"))
    return STATE_CREATE_WAIT_MEDIA


# ---- Получаем фото/видео ----
async def lot_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    photo = update.message.photo
    video = update.message.video
    if not photo and not video:
        await update.message.reply_text(L(chat_id, "enter_media"))
        return STATE_CREATE_WAIT_MEDIA

    if photo:
        file_id = photo[-1].file_id
        context.user_data["media_type"] = "photo"
        context.user_data["file_id"] = file_id
    else:
        file_id = video.file_id
        context.user_data["media_type"] = "video"
        context.user_data["file_id"] = file_id

    await update.message.reply_text(L(chat_id, "enter_desc"))
    return STATE_CREATE_WAIT_DESCRIPTION


# ---- Получаем описание, публикуем лот ----
async def lot_desc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    desc = update.message.text
    if USERS[chat_id]["balance"] < 1:
        await update.message.reply_text("Не хватает средств (1$)!" if get_lang(chat_id) == "ru" else "Not enough balance (1$)!")
        return STATE_MENU

    # Списываем 1$
    USERS[chat_id]["balance"] -= 1

    global NEXT_LOT_ID
    lot_id = NEXT_LOT_ID
    NEXT_LOT_ID += 1

    LLOTS = {
        "owner_id": chat_id,
        "media_type": context.user_data["media_type"],
        "file_id": context.user_data["file_id"],
        "description": desc,
        "is_ended": False,
        "end_time": None,
        "message_id": None,
        "bids": {}
    }
    LOTS[lot_id] = LLOTS

    USERS[chat_id]["lots"].append(lot_id)

    duration_minutes = context.user_data["duration_minutes"]
    end_time = datetime.utcnow() + timedelta(minutes=duration_minutes)
    LLOTS["end_time"] = end_time

    # Публикуем в канал
    caption = build_lot_caption(lot_id, chat_id)
    kb = get_auction_keyboard(lot_id, chat_id)

    if LLOTS["media_type"] == "photo":
        msg = await context.bot.send_photo(
            CHANNEL_ID,
            photo=LLOTS["file_id"],
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb
        )
    else:
        msg = await context.bot.send_video(
            CHANNEL_ID,
            video=LLOTS["file_id"],
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb
        )

    LLOTS["message_id"] = msg.message_id

    # Запускаем таймер (без учёта антиснайпера на старте, он будет учитываться при ставках)
    asyncio.create_task(schedule_auction_end(context, lot_id, duration_minutes))

    # Чистим временные данные
    context.user_data.pop("media_type")
    context.user_data.pop("file_id")
    context.user_data.pop("duration_minutes")

    await update.message.reply_text(L(chat_id, "lot_published"), reply_markup=main_menu_kb(chat_id))
    return STATE_MENU


# --------------------------
# 9) Ставки +1/+3/+5, таймер, инфо, антиснайпер
# --------------------------
async def auction_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем колбэки: bid_, timer_, info_."""
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    await query.answer()

    if data.startswith("bid_"):
        # bid_<lot_id>_<plus>
        _, lot_id_str, plus_str = data.split("_")
        lot_id = int(lot_id_str)
        plus = int(plus_str)
        if lot_id not in LOTS:
            await query.answer(L(chat_id, "lot_not_found"), show_alert=True)
            return

        lot = LOTS[lot_id]
        if lot["is_ended"]:
            await query.answer(L(chat_id, "bid_ended"), show_alert=True)
            return

        user = query.from_user
        user_id = user.id
        old_amount = lot["bids"].get(user_id, {"amount": 0})["amount"]
        new_amount = old_amount + plus
        lot["bids"][user_id] = {"username": user.username, "amount": new_amount}

        # Антиснайпер
        await apply_antisniper(context, lot_id, lot["owner_id"])

        # Обновляем caption
        new_cap = build_lot_caption(lot_id, lot["owner_id"])
        try:
            await context.bot.edit_message_caption(
                chat_id=CHANNEL_ID,
                message_id=lot["message_id"],
                caption=new_cap,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_auction_keyboard(lot_id, lot["owner_id"])
            )
        except Exception as e:
            logging.warning(f"Cannot edit lot in channel: {e}")

    elif data.startswith("timer_"):
        # Покажем время, оставшееся до конца
        _, lot_id_str = data.split("_")
        lot_id = int(lot_id_str)
        if lot_id not in LOTS:
            await query.answer(L(chat_id, "lot_not_found"), show_alert=True)
            return
        lot = LOTS[lot_id]
        if lot["is_ended"]:
            await query.answer(L(chat_id, "bid_ended"), show_alert=True)
            return
        remain = get_time_remaining_str(lot["end_time"], lot["owner_id"])
        await query.answer(L(chat_id, "time_left", time=remain), show_alert=True)

    elif data.startswith("info_"):
        # Покажем всплывающее окно с примером, как на скриншоте
        _, lot_id_str = data.split("_")
        # Можно вывести «реальную» информацию, но по ТЗ — примерный блок
        await query.answer(L(chat_id, "info_example"), show_alert=True)


# --------------------------
# 10) Настройки (инлайн-кнопки)
# --------------------------
async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий в меню настроек."""
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    await query.answer()

    if data == "settings_back":
        await query.message.delete()
        await query.message.reply_text(L(chat_id, "main_menu"), reply_markup=main_menu_kb(chat_id))
        return STATE_MENU

    elif data == "set_antisniper":
        await query.edit_message_text(L(chat_id, "antisniper_info"), parse_mode=ParseMode.MARKDOWN)
        return STATE_SETTINGS_ANTISNIPER

    elif data == "set_currency":
        await query.edit_message_text(L(chat_id, "currency_info"), parse_mode=ParseMode.MARKDOWN, reply_markup=currency_kb(chat_id))
        return STATE_SETTINGS_CURRENCY

    elif data == "set_rules":
        await query.edit_message_text(L(chat_id, "rules_info"), parse_mode=ParseMode.MARKDOWN,
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton(L(chat_id, "back"), callback_data="settings_back")]
                                      ]))
        return STATE_SETTINGS_RULES

    elif data == "set_blacklist":
        await query.edit_message_text(L(chat_id, "blacklist_info"), parse_mode=ParseMode.MARKDOWN,
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton(L(chat_id, "back"), callback_data="settings_back")]
                                      ]))
        return STATE_SETTINGS_BLACKLIST

    elif data == "set_notifications":
        await query.edit_message_text(L(chat_id, "notifications_info"), parse_mode=ParseMode.MARKDOWN,
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton(L(chat_id, "back"), callback_data="settings_back")]
                                      ]))
        return STATE_SETTINGS_NOTIFICATIONS

    elif data == "set_language":
        await query.edit_message_text(L(chat_id, "lang_info"), parse_mode=ParseMode.MARKDOWN, reply_markup=language_inline_kb(chat_id))
        return STATE_SETTINGS_LANGUAGE


# ---- Антиснайпер: ввод числа ----
async def antisniper_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    txt = update.message.text
    try:
        val = int(txt)
        if val < 0 or val > 3600:
            raise ValueError
    except:
        await update.message.reply_text("Введите число 0..3600" if get_lang(chat_id) == "ru" else "Enter 0..3600")
        return STATE_SETTINGS_ANTISNIPER

    USERS[chat_id]["settings"]["antisniper"] = val
    await update.message.reply_text(L(chat_id, "antisniper_set", val=val), reply_markup=main_menu_kb(chat_id))
    return STATE_MENU


# ---- Валюта (инлайн) ----
async def currency_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    await query.answer()

    if data == "currency_back":
        # возвращаемся в меню настроек
        await query.message.delete()
        await query.message.reply_text(L(chat_id, "settings_title"), reply_markup=settings_inline_kb(chat_id), parse_mode=ParseMode.MARKDOWN)
        return STATE_SETTINGS_MENU
    elif data in ["currency_usdt", "currency_ton"]:
        new_curr = "USDT" if data.endswith("usdt") else "TON"
        USERS[chat_id]["settings"]["currency"] = new_curr
        await query.message.delete()
        await query.message.reply_text(L(chat_id, "currency_set", curr=new_curr), reply_markup=main_menu_kb(chat_id))
        return STATE_MENU


# ---- Правила (ввод текста) ----
async def rules_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    new_rules = update.message.text
    USERS[chat_id]["settings"]["rules"] = new_rules
    await update.message.reply_text(L(chat_id, "rules_updated"), reply_markup=main_menu_kb(chat_id))
    return STATE_MENU


# ---- Смена языка (инлайн) ----
async def language_change_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data  # lang_ru / lang_en
    chat_id = query.message.chat_id
    await query.answer()

    if data == "lang_ru":
        USERS[chat_id]["lang"] = "ru"
        await query.message.reply_text(L(chat_id, "lang_switched_ru"), reply_markup=main_menu_kb(chat_id), parse_mode=ParseMode.MARKDOWN)
    elif data == "lang_en":
        USERS[chat_id]["lang"] = "en"
        await query.message.reply_text(L(chat_id, "lang_switched_en"), reply_markup=main_menu_kb(chat_id), parse_mode=ParseMode.MARKDOWN)
    return STATE_MENU


# --------------------------
# 11) MAIN + ConversationHandler
# --------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            STATE_MENU: [
                MessageHandler(filters.Regex("^(Создать лот|Create Lot|Мои лоты|My Lots|Пополнить баланс|Topup balance|Настройки|Settings|Помощь|Help)$"), menu_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler),
                CommandHandler("help", help_command),
            ],

            STATE_CREATE_ASK_DURATION: [
                CallbackQueryHandler(duration_callback, pattern=r"^dur_"),
            ],
            STATE_CREATE_WAIT_MEDIA: [
                MessageHandler((filters.PHOTO | filters.VIDEO), lot_media_handler)
            ],
            STATE_CREATE_WAIT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lot_desc_handler)
            ],

            STATE_SETTINGS_MENU: [
                CallbackQueryHandler(settings_callback_handler, pattern=r"^(set_|settings_back)")
            ],
            STATE_SETTINGS_ANTISNIPER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, antisniper_input_handler)
            ],
            STATE_SETTINGS_CURRENCY: [
                CallbackQueryHandler(currency_callback_handler, pattern=r"^currency_")
            ],
            STATE_SETTINGS_RULES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rules_input_handler)
            ],
            STATE_SETTINGS_BLACKLIST: [],
            STATE_SETTINGS_NOTIFICATIONS: [],
            STATE_SETTINGS_LANGUAGE: [
                CallbackQueryHandler(language_change_handler, pattern=r"^lang_")
            ],
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("help", help_command)
        ]
    )

    app.add_handler(conv_handler)

    # Ставки (bid_), таймер (timer_), инфо (info_)
    app.add_handler(CallbackQueryHandler(auction_callback_handler, pattern=r"^(bid_|timer_|info_)"))

    # Запуск
    app.run_polling()

if __name__ == "__main__":
    main()