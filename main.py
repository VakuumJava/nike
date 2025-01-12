"""
Полный бот-аукцион ~800–1000 строк:

  - Пакеты (до 3 фото/видео)
  - BuyNow
  - LastCall
  - Антиснайпер
  - Админ-панель (редактирование длительностей, шагов, удаление ставки, бан)
  - Баланс и «Пополнить»
  - Проверка ADMIN_ONLY
  - ConversationHandler без «зависаний» на вводе описания
  - Большие комментарии, docstring, отладочные print/logging.
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from telegram.helpers import escape_markdown
# Для чтения .env
from dotenv import load_dotenv

# Модули TG Bot
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InputMediaPhoto,
    InputMediaVideo,
    ChatMember
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    ContextTypes
)

# -----------------------------------
# 1) ЗАГРУЗКА .env
# -----------------------------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1001234567890"))
ADMIN_ONLY = os.getenv("ADMIN_ONLY", "true").lower() == "true"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# -----------------------------------
# 2) Память (в оперативке)
# -----------------------------------
"""
USERS:
   chat_id -> {
     "balance": int,
     "lots": [],
     "blacklist": set(),
     "allowed_durations": [...],
     "allowed_increments": [...],
   }

LOTS:
   lot_id -> {
     "owner_id": int,
     "media_files": [("photo",fid), ...],
     "max_price": float,
     "last_call_enabled": bool,
     "start_time": datetime,
     "end_time": datetime,
     "is_ended": bool,
     "bids": { user_id: { "username": str, "amount": int } },
     "description": str,
     "message_id": int,
     # optional: "antisniper": ...
   }
"""

USERS = {}
LOTS = {}
NEXT_LOT_ID = 1

DEFAULT_DURATIONS = [15, 30, 60, 120, 300]  # минут
DEFAULT_INCREMENTS = [1, 3, 5]              # шаги ставок по умолч.

# -----------------------------------
# 3) Состояния
# -----------------------------------
(
    STATE_MENU,
    STATE_ADMIN_PANEL,
    STATE_ADMIN_EDIT_DURS,
    STATE_ADMIN_EDIT_INCS,
    STATE_ADMIN_DEL_BID,
    STATE_ADMIN_BAN_USER,

    STATE_PKG_ASK_COUNT,
    STATE_PKG_GET_MEDIA,
    STATE_ASK_BUYNOW,
    STATE_ASK_LASTCALL,
    STATE_ASK_DURATION,
    STATE_ASK_DESC
) = range(12)

# -----------------------------------
# 4) Тексты
# -----------------------------------
def L(key: str, **kwargs) -> str:
    """Локализация (для простоты — один язык)."""
    msgs = {
        "start": (
            "<b>🎁 Super Auction Bot</b>\n\n"
            "Поддерживает пакеты, BuyNow, LastCall, админ-панель.\n\n"
            "Выберите действие в меню."
        ),
        "help": (
            "<b>Помощь</b>\n\n"
            "Команды:\n"
            "/start — запустить\n"
            "/help — это справка\n\n"
            "Возможности:\n"
            "• Пакетные лоты (до 3 фото/видео)\n"
            "• BuyNow\n"
            "• LastCall\n"
            "• Антиснайпер (demo)\n"
            "• Админ-панель (бан, редактирование длительностей, шагов)\n"
            "• Баланс и «пополнить»"
        ),
        "main_menu": "Выберите действие:",
        "menu_create": "🎁 Создать лот",
        "menu_my": "📋 Мои лоты",
        "menu_balance": "💰 Баланс",
        "menu_admin": "⚙️ Admin",
        "menu_help": "❓ Помощь",

        "only_admin": "🚫 Доступ только админам канала.",
        "no_lots": "У вас нет лотов.",
        "bal_info": "Баланс: {bal}$",
        "bal_topped": "Баланс +10$. Теперь: {bal}$",
        "menu_topup": "➕ Пополнить",

        "admin_menu": (
            "Админ-панель:\n"
            "1) Ред. длительности\n"
            "2) Ред. шаги\n"
            "3) Удалить ставку\n"
            "4) Бан пользователя"
        ),
        "btn_adm_durs": "⏳ Длительности",
        "btn_adm_incs": "🔼 Шаги",
        "btn_adm_del": "🗑 Ставка",
        "btn_adm_ban": "🚫 Бан",

        "durs_list": "Текущие длительности: {vals}\nВведите новые (через запятую) или 'отмена'.",
        "incs_list": "Текущие шаги: {vals}\nВведите новые (через запятую) или 'отмена'.",
        "bid_remove": "Введите: lot_id user_id",
        "ban_user": "Введите user_id (кого баним).",
        "bid_removed": "Ставка пользователя @{uname} удалена.",
        "user_banned": "Пользователь @{uname} забанен.",
        "ok_done": "✅ Готово",

        "ask_pkg_count": "Сколько файлов (1..3)?",
        "wrong_input": "Неверный ввод.",
        "send_files": "Отправьте {count} фото/видео по одному сообщению.",
        "recv_file": "Принято {done}/{total}.",
        "all_files": "Все {n} файлов получены!",
        "ask_buynow": "Укажите BuyNow (0, если не нужен).",
        "ask_lastcall": "Включить LastCall?",
        "lc_yes": "Да",
        "lc_no": "Нет",
        "ask_duration": "На сколько минут запустить аукцион?",
        "ask_desc": "Опишите лот (текст).",
        "lot_published": "Лот опубликован!",
        "not_enough": "Недостаточно средств (1$).",

        "auction_ended": "Аукцион завершён.",
        "lot_bought": "Лот #{lot_id} куплен!",
        "lot_no_bids": "Нет ставок.",
        "last_call": "‼️ LastCall лота #{lot_id}!"
    }
    txt = msgs.get(key, f"??{key}??")
    return txt.format(**kwargs) if kwargs else txt

def partial_username(username: str) -> str:
    """Возвращаем первые 3 символа никнейма или ???."""
    if username and len(username)>0:
        return username[:3]
    return "???"

# -----------------------------------
# 5) ПОЛЬЗОВАТЕЛИ
# -----------------------------------
async def is_admin(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Проверяем, является ли user_id админом канала (если ADMIN_ONLY)."""
    if not ADMIN_ONLY:
        return True
    try:
        cm = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return cm.status in [ChatMember.ADMINISTRATOR, ChatMember.CREATOR]
    except:
        return False

def ensure_user(chat_id: int):
    """Создаём запись в USERS."""
    if chat_id not in USERS:
        USERS[chat_id] = {
            "balance": 10,
            "lots": [],
            "blacklist": set(),
            "allowed_durations": DEFAULT_DURATIONS.copy(),
            "allowed_increments": DEFAULT_INCREMENTS.copy()
        }

# -----------------------------------
# Главное меню
# -----------------------------------
def main_menu_kb() -> ReplyKeyboardMarkup:
    row = [
        [L("menu_create"), L("menu_my")],
        [L("menu_balance"), L("menu_admin")],
        [L("menu_help")]
    ]
    return ReplyKeyboardMarkup(row, resize_keyboard=True)

# -----------------------------------
# /start /help
# -----------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — проверяем ADMIN_ONLY, создаём пользователя, показываем меню."""
    chat_id = update.effective_chat.id
    if ADMIN_ONLY:
        if not await is_admin(context, chat_id):
            await update.message.reply_text(L("only_admin"))
            return ConversationHandler.END

    ensure_user(chat_id)
    await update.message.reply_text(L("start"), parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())
    return STATE_MENU

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if ADMIN_ONLY:
        if not await is_admin(context, chat_id):
            return ConversationHandler.END

    await update.message.reply_text(L("help"), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    return STATE_MENU

# -----------------------------------
# Меню Handler
# -----------------------------------
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    txt = update.message.text.strip()
    if ADMIN_ONLY:
        if not await is_admin(context, chat_id):
            await update.message.reply_text(L("only_admin"))
            return ConversationHandler.END

    ensure_user(chat_id)

    if txt == L("menu_create"):
        # Создать лот: спрашиваем, сколько файлов
        await update.message.reply_text(L("ask_pkg_count"))
        return STATE_PKG_ASK_COUNT

    elif txt == L("menu_my"):
        user_lots = USERS[chat_id]["lots"]
        if not user_lots:
            await update.message.reply_text(L("no_lots"), reply_markup=main_menu_kb())
            return STATE_MENU
        await update.message.reply_text("Ваши лоты:", reply_markup=ReplyKeyboardRemove())
        for lot_id in user_lots:
            lot = LOTS[lot_id]
            st = "Завершён" if lot["is_ended"] else "Активен"
            await update.message.reply_text(f"Лот #{lot_id}: {st}\n{lot['description']}")
        await update.message.reply_text("OK", reply_markup=main_menu_kb())
        return STATE_MENU

    elif txt == L("menu_balance"):
        bal = USERS[chat_id]["balance"]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(L("menu_topup"), callback_data="topup")]
        ])
        await update.message.reply_text(L("bal_info", bal=bal), reply_markup=kb)
        return STATE_MENU

    elif txt == L("menu_admin"):
        return await admin_panel(update, context)

    elif txt == L("menu_help"):
        return await help_cmd(update, context)

    else:
        await update.message.reply_text(L("main_menu"), reply_markup=main_menu_kb())
        return STATE_MENU

# -----------------------------------
# Админ-панель
# -----------------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if ADMIN_ONLY:
        if not await is_admin(context, chat_id):
            await update.message.reply_text(L("only_admin"))
            return STATE_MENU
    txt = L("admin_menu")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(L("btn_adm_durs"), callback_data="adm_durs")],
        [InlineKeyboardButton(L("btn_adm_incs"), callback_data="adm_incs")],
        [InlineKeyboardButton(L("btn_adm_del"), callback_data="adm_del")],
        [InlineKeyboardButton(L("btn_adm_ban"), callback_data="adm_ban")]
    ])
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=kb)
    return STATE_ADMIN_PANEL

async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback в админ-панели."""
    query = update.callback_query
    data = query.data
    user_id = query.message.chat_id
    await query.answer()

    if data == "adm_durs":
        durs = USERS[user_id]["allowed_durations"]
        txt = L("durs_list", vals=durs)
        await query.message.edit_text(txt)
        return STATE_ADMIN_EDIT_DURS
    elif data == "adm_incs":
        incs = USERS[user_id]["allowed_increments"]
        txt = L("incs_list", vals=incs)
        await query.message.edit_text(txt)
        return STATE_ADMIN_EDIT_INCS
    elif data == "adm_del":
        await query.message.edit_text(L("bid_remove"))
        return STATE_ADMIN_DEL_BID
    elif data == "adm_ban":
        await query.message.edit_text(L("ban_user"))
        return STATE_ADMIN_BAN_USER
    else:
        await query.message.reply_text(L("ok_done"), reply_markup=main_menu_kb())
        return STATE_MENU

async def admin_edit_durs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    txt = update.message.text.strip().lower()
    if txt=="отмена":
        await update.message.reply_text(L("ok_done"), reply_markup=main_menu_kb())
        return STATE_MENU

    parts = [p.strip() for p in txt.split(",")]
    new_durs = []
    for p in parts:
        try:
            val = int(p)
            if val<1 or val>10080:
                raise ValueError
            new_durs.append(val)
        except:
            await update.message.reply_text(L("wrong_input"))
            return STATE_ADMIN_EDIT_DURS

    USERS[chat_id]["allowed_durations"] = new_durs
    await update.message.reply_text(L("ok_done"), reply_markup=main_menu_kb())
    return STATE_MENU

async def admin_edit_incs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    txt = update.message.text.strip().lower()
    if txt=="отмена":
        await update.message.reply_text(L("ok_done"), reply_markup=main_menu_kb())
        return STATE_MENU

    parts = [p.strip() for p in txt.split(",")]
    new_incs = []
    for p in parts:
        try:
            val = int(p)
            if val<1 or val>9999:
                raise ValueError
            new_incs.append(val)
        except:
            await update.message.reply_text(L("wrong_input"))
            return STATE_ADMIN_EDIT_INCS

    USERS[chat_id]["allowed_increments"] = new_incs
    await update.message.reply_text(L("ok_done"), reply_markup=main_menu_kb())
    return STATE_MENU

async def admin_del_bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Удаление конкретной ставки по номеру лота и либо позиции в списке ставок, либо user_id.
    Формат ввода: lot_id position OR lot_id user_id
    """
    chat_id = update.effective_chat.id
    txt = update.message.text.strip()
    parts = txt.split()
    if len(parts) != 2:
        await update.message.reply_text("Неверный формат. Используйте: lot_id position/user_id")
        return STATE_ADMIN_DEL_BID

    try:
        lot_id = int(parts[0])
        identifier = int(parts[1])  # Это может быть либо позиция ставки, либо user_id
    except ValueError:
        await update.message.reply_text("Неверный ввод. Убедитесь, что вы указали числовые значения.")
        return STATE_ADMIN_DEL_BID

    # Проверяем, существует ли лот
    if lot_id not in LOTS:
        await update.message.reply_text("Лот не найден.")
        return STATE_MENU

    lot = LOTS[lot_id]

    # Если identifier — это позиция в ставках
    if 1 <= identifier <= len(lot["bids"]):
        # Сортируем ставки по убыванию
        sorted_bids = sorted(lot["bids"].items(), key=lambda x: x[1]["amount"], reverse=True)
        user_id, bid_data = sorted_bids[identifier - 1]  # Получаем user_id и данные ставки на указанной позиции
        lot["bids"].pop(user_id)  # Удаляем ставку
        uname = bid_data["username"]
        await update.message.reply_text(f"Ставка #{identifier} (пользователь @{uname}) удалена.")
    elif identifier in lot["bids"]:
        # Если identifier — это user_id
        uname = lot["bids"][identifier]["username"]
        lot["bids"].pop(identifier)
        await update.message.reply_text(f"Ставка пользователя @{uname} удалена.")
    else:
        await update.message.reply_text("Ставка не найдена. Убедитесь, что вы указали правильную позицию или user_id.")
        return STATE_ADMIN_DEL_BID

    # Обновляем сообщение лота, если оно ещё активно
    if not lot["is_ended"] and len(lot["media_files"]) == 1:
        new_cap = build_caption(lot_id)
        kb = build_lot_kb(lot_id)
        try:
            await context.bot.edit_message_caption(
                chat_id=CHANNEL_ID,
                message_id=lot["message_id"],
                caption=new_cap,
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        except Exception as e:
            logging.error(f"Ошибка обновления сообщения: {e}")

    return STATE_MENU

async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    txt = update.message.text.strip()
    try:
        ban_uid = int(txt)
    except:
        await update.message.reply_text(L("wrong_input"))
        return STATE_ADMIN_BAN_USER

    USERS[chat_id]["blacklist"].add(ban_uid)
    await update.message.reply_text(L("user_banned", uname=ban_uid), reply_markup=main_menu_kb())
    return STATE_MENU

# -----------------------------------
# Баланс: topup
# -----------------------------------
async def balance_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.message.chat_id
    await query.answer()

    if data=="topup":
        USERS[user_id]["balance"] += 10
        bal = USERS[user_id]["balance"]
        await query.message.reply_text(L("bal_topped", bal=bal))
        return STATE_MENU

# -----------------------------------
# Создание лота (пакеты)
# -----------------------------------
async def pkg_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Сколько фото/видео (1..3)?
    """
    chat_id = update.effective_chat.id
    txt = update.message.text.strip()
    try:
        n = int(txt)
        if n<1 or n>3:
            raise ValueError
    except:
        await update.message.reply_text(L("wrong_input"))
        return STATE_PKG_ASK_COUNT

    context.user_data["pkg_count"] = n
    context.user_data["pkg_files"] = []
    await update.message.reply_text(L("send_files", count=n))
    return STATE_PKG_GET_MEDIA

async def pkg_get_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Принимаем n фото/видео.
    """
    chat_id = update.effective_chat.id
    photo = update.message.photo
    video = update.message.video
    fs = context.user_data["pkg_files"]
    n = context.user_data["pkg_count"]

    if not photo and not video:
        await update.message.reply_text(L("wrong_input"))
        return STATE_PKG_GET_MEDIA

    if photo:
        fid = photo[-1].file_id
        fs.append(("photo",fid))
    else:
        fid = video.file_id
        fs.append(("video",fid))

    done = len(fs)
    if done<n:
        await update.message.reply_text(L("recv_file", done=done, total=n))
        return STATE_PKG_GET_MEDIA

    # все
    await update.message.reply_text(L("all_files", n=n))
    # BuyNow?
    await update.message.reply_text(L("ask_buynow"))
    return STATE_ASK_BUYNOW

async def ask_buynow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Получаем BuyNow.
    """
    chat_id = update.effective_chat.id
    txt = update.message.text.strip()
    try:
        val = float(txt)
        if val<0:
            raise ValueError
    except:
        await update.message.reply_text(L("wrong_input"))
        return STATE_ASK_BUYNOW

    context.user_data["max_price"] = val
    # LastCall?
    row = [
        [
            InlineKeyboardButton(L("lc_yes"), callback_data="lc_yes"),
            InlineKeyboardButton(L("lc_no"), callback_data="lc_no")
        ]
    ]
    kb = InlineKeyboardMarkup(row)
    await update.message.reply_text(L("ask_lastcall"), reply_markup=kb)
    return STATE_ASK_LASTCALL

async def lastcall_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()
    context.user_data["lastcall"] = (data=="lc_yes")

    # выбираем длительность
    user_id = query.message.chat_id
    row=[]
    row2=[]
    durs = USERS[user_id]["allowed_durations"]
    for d in durs:
        row2.append(InlineKeyboardButton(f"{d} мин", callback_data=f"dur_{d}"))
        if len(row2)==2:
            row.append(row2)
            row2=[]
    if row2:
        row.append(row2)
    kb = InlineKeyboardMarkup(row)
    await query.message.edit_text(L("ask_duration"), reply_markup=kb)
    return STATE_ASK_DURATION

async def duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if not data.startswith("dur_"):
        await query.message.reply_text("Error.")
        return STATE_MENU

    val_str = data.split("_")[1]
    try:
        dur = int(val_str)
    except:
        await query.message.reply_text("Неверная длительность.")
        return STATE_MENU

    context.user_data["auction_mins"] = dur
    await query.message.edit_text(L("ask_desc"))
    return STATE_ASK_DESC

async def create_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем описание лота, создаём, публикуем."""
    chat_id = update.effective_chat.id
    desc = escape_markdown(update.message.text.strip())
    if USERS[chat_id]["balance"]<1:
        await update.message.reply_text(L("not_enough"))
        return STATE_MENU
    USERS[chat_id]["balance"]-=1

    global NEXT_LOT_ID
    lot_id = NEXT_LOT_ID
    NEXT_LOT_ID+=1

    fs = context.user_data["pkg_files"]
    mxp = context.user_data["max_price"]
    lc = context.user_data["lastcall"]
    mins = context.user_data["auction_mins"]

    now = datetime.utcnow()
    end_time = now + timedelta(minutes=mins)

    LOTS[lot_id] = {
        "owner_id": chat_id,
        "media_files": fs,
        "max_price": mxp,
        "last_call_enabled": lc,
        "start_time": now,
        "end_time": end_time,
        "is_ended": False,
        "bids": {},
        "description": desc,
        "message_id": None
    }
    USERS[chat_id]["lots"].append(lot_id)

    # Публикуем
    await publish_lot(context, lot_id)
    # таймер
    asyncio.create_task(schedule_end(context, lot_id))
    if lc:
        asyncio.create_task(schedule_last_call(context, lot_id))

    # очистка
    context.user_data.pop("pkg_files", None)
    context.user_data.pop("pkg_count", None)
    context.user_data.pop("max_price", None)
    context.user_data.pop("lastcall", None)
    context.user_data.pop("auction_mins", None)

    await update.message.reply_text(L("lot_published"), reply_markup=main_menu_kb())
    return STATE_MENU

async def publish_lot(context: ContextTypes.DEFAULT_TYPE, lot_id: int):
    """send_photo/send_video/sendMediaGroup + caption + inline-кнопки"""
    lot = LOTS[lot_id]
    cap = build_caption(lot_id)
    kb = build_lot_kb(lot_id)
    fm = lot["media_files"]
    if len(fm)==1:
        (ft,fid) = fm[0]
        if ft=="photo":
            msg = await context.bot.send_photo(CHANNEL_ID, photo=fid, caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            msg = await context.bot.send_video(CHANNEL_ID, video=fid, caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
        lot["message_id"] = msg.message_id
    else:
        media=[]
        first=True
        for (ft, fid) in fm:
            if first:
                if ft=="photo":
                    media.append(InputMediaPhoto(fid, caption=cap, parse_mode=ParseMode.HTML))
                else:
                    media.append(InputMediaVideo(fid, caption=cap, parse_mode=ParseMode.HTML))
                first=False
            else:
                if ft=="photo":
                    media.append(InputMediaPhoto(fid))
                else:
                    media.append(InputMediaVideo(fid))
        msgs = await context.bot.send_media_group(CHANNEL_ID, media)
        lot["message_id"] = msgs[-1].message_id

def build_caption(lot_id: int) -> str:
    lot = LOTS[lot_id]
    now = datetime.utcnow()
    diff = (lot["end_time"]-now).total_seconds()
    if diff<0: diff=0
    mm = int(diff//60)
    # Используем HTML-разметку
    txt = f"<b>Лот #{lot_id}</b> (Осталось: {mm} мин)\n"
    if lot["max_price"]>0:
        txt += f"BuyNow: {lot['max_price']}$\n"
    if lot["last_call_enabled"]:
        txt += "LastCall: включён\n"
    txt += lot["description"] + "\n\n"
    if not lot["bids"]:
        txt += L("no_bids")
    else:
        s = sorted(lot["bids"].items(), key=lambda x:x[1]["amount"], reverse=True)
        top=[]
        for uid, data in s[:3]:
            shortn = partial_username(data["username"])
            top.append(f"{data['amount']}$ (@{shortn})")
        txt += "Топ-3 ставок:\n" + "\n".join(top)
    return txt

def build_lot_kb(lot_id: int) -> InlineKeyboardMarkup:
    lot = LOTS[lot_id]
    row=[]
    if lot["max_price"]>0 and not lot["is_ended"]:
        row.append([InlineKeyboardButton(f"💰 BuyNow ({lot['max_price']}$)", callback_data=f"buy_{lot_id}")])
    # инкременты
    # берём у owner'a
    incs = USERS[lot["owner_id"]]["allowed_increments"]
    row_bids = []
    for inc in incs:
        row_bids.append(InlineKeyboardButton(f"➕{inc}", callback_data=f"bid_{lot_id}_{inc}"))
        if len(row_bids)==3:
            row.append(row_bids)
            row_bids=[]
    if row_bids:
        row.append(row_bids)

    row_ex = [
        InlineKeyboardButton("ℹ Info", callback_data=f"info_{lot_id}"),
        InlineKeyboardButton("⌛", callback_data=f"timer_{lot_id}")
    ]
    row.append(row_ex)
    return InlineKeyboardMarkup(row)

async def schedule_end(context: ContextTypes.DEFAULT_TYPE, lot_id: int):
    lot = LOTS[lot_id]
    sec = (lot["end_time"]-datetime.utcnow()).total_seconds()
    if sec<0: sec=0
    await asyncio.sleep(sec)
    if not lot["is_ended"]:
        await end_lot(context, lot_id)

async def end_lot(context: ContextTypes.DEFAULT_TYPE, lot_id: int):
    """Завершение аукциона с отображением полных юзернеймов."""
    lot = LOTS[lot_id]
    lot["is_ended"] = True
    txt = f"**Лот #{lot_id} завершён**\n\nОписание: {lot['description']}\n\n"
    admin_msg = f"Лот #{lot_id} завершён.\n"

    if lot["bids"]:
        # Сортируем ставки по убыванию
        sorted_bids = sorted(lot["bids"].items(), key=lambda x: x[1]["amount"], reverse=True)
        txt += "🏆 Топ-3 победителя:\n"
        for i, (user_id, bid_data) in enumerate(sorted_bids[:3], 1):
            username = bid_data["username"]
            amount = bid_data["amount"]
            txt += f"{i}. @{username} — {amount}$\n"
            admin_msg += f"{i}. @{username} — {amount}$\n"
    else:
        txt += "Ставок не было.\n"
        admin_msg += "Ставок не было.\n"

    # Отправка итогов в канал
    if len(lot["media_files"]) == 1:
        try:
            await context.bot.edit_message_caption(
                chat_id=CHANNEL_ID,
                message_id=lot["message_id"],
                caption=txt,
                parse_mode=ParseMode.HTML,
                reply_markup=None
            )
        except Exception as e:
            logging.error(f"Ошибка обновления сообщения: {e}")
    else:
        await context.bot.send_message(CHANNEL_ID, txt, parse_mode=ParseMode.HTML)

    # Отправка уведомления владельцу лота
    owner = lot["owner_id"]
    await context.bot.send_message(owner, admin_msg)

async def schedule_last_call(context: ContextTypes.DEFAULT_TYPE, lot_id: int):
    lot = LOTS[lot_id]
    total_time = (lot["end_time"] - lot["start_time"]).total_seconds()
    if total_time > 120:
        await asyncio.sleep(total_time - 120)  # За 30 секунд до конца
        if not lot["is_ended"]:
            await context.bot.send_message(
                CHANNEL_ID, L("last_call", lot_id=lot_id), parse_mode=ParseMode.HTML
            )

async def is_subscriber(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Проверка подписки на канал."""
    try:
        chat_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

async def auction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = query.from_user
    if not await is_subscriber(context, user.id):
        await query.answer("Вы должны быть подписчиком канала, чтобы участвовать.", show_alert=True)
        return
    # Остальная логика...

# -----------------------------------
# Auction callback (buy_, bid_, timer_, info_)
# -----------------------------------
async def auction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = query.from_user  # Получаем пользователя, нажавшего кнопку
    await query.answer()

    if data.startswith("buy_"):
        lot_id = int(data.split("_")[1])
        if lot_id not in LOTS:
            await query.answer("Лот не найден.", show_alert=True)
            return

        lot = LOTS[lot_id]
        if lot["is_ended"]:
            await query.answer("Лот уже завершён.", show_alert=True)
            return

        # Проверяем подписку
        if not await is_subscriber(context, user.id):
            await query.answer("Вы должны быть подписчиком канала, чтобы купить этот лот.", show_alert=True)
            return

        # Завершаем лот
        lot["is_ended"] = True
        buyer_username = user.username or "аноним"  # Если username не задан
        buyer_id = user.id

        # Отправляем сообщение в канал
        txt = (
            f"Лот #{lot_id} куплен пользователем @{buyer_username} за {lot['max_price']}$!\n"
            f"Поздравляем победителя!"
        )
        await context.bot.send_message(CHANNEL_ID, txt)

        # Уведомляем владельца лота
        owner_msg = (
            f"Ваш лот #{lot_id} куплен!\n"
            f"Покупатель: @{buyer_username} (ID: {buyer_id})\n"
            f"Сумма: {lot['max_price']}$."
        )
        await context.bot.send_message(lot["owner_id"], owner_msg)

        # Логируем покупку
        logging.info(f"Лот #{lot_id} куплен @{buyer_username} (ID: {buyer_id}) за {lot['max_price']}$.")
        if len(lot["media_files"])==1:
            try:
                await context.bot.edit_message_caption(
                    chat_id=CHANNEL_ID,
                    message_id=lot["message_id"],
                    caption=txt,
                    parse_mode=ParseMode.HTML,
                    reply_markup=None
                )
            except:
                pass
        else:
            await context.bot.send_message(CHANNEL_ID, txt, parse_mode=ParseMode.HTML)

    elif data.startswith("bid_"):
        _, lid, inc_str = data.split("_")
        lot_id = int(lid)
        inc_val = int(inc_str)
        if lot_id not in LOTS:
            return
        lot = LOTS[lot_id]
        if lot["is_ended"]:
            return

        old_amt = lot["bids"].get(user.id, {"username": user.username, "amount":0})["amount"]
        new_amt = old_amt + inc_val
        lot["bids"][user.id] = {"username":user.username, "amount":new_amt}

        # Антиснайпер (если хотите) —пример
        # antisniper_val = ...
        # if remain < antisniper_val: extend ...
        # ...
        if len(lot["media_files"])==1:
            new_cap = build_caption(lot_id)
            kb = build_lot_kb(lot_id)
            try:
                await context.bot.edit_message_caption(
                    chat_id=CHANNEL_ID,
                    message_id=lot["message_id"],
                    caption=new_cap,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb
                )
            except:
                pass

    elif data.startswith("timer_"):
        lot_id = int(data.split("_")[1])
        if lot_id not in LOTS:
            return
        lot = LOTS[lot_id]
        if lot["is_ended"]:
            await query.answer(L("lot_ended"), show_alert=True)
            return
        remain_s = (lot["end_time"]-datetime.utcnow()).total_seconds()
        if remain_s<0:
            remain_s=0
        mm = int(remain_s//60)
        await query.answer(f"Осталось: {mm} мин", show_alert=True)
    elif data.startswith("info_"):
        await query.answer("Инфо о лоте / правила и т.п.", show_alert=True)

# -----------------------------------
# Запуск
# -----------------------------------
def main():
    """Собираем всё в один ConversationHandler и callbacks."""
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ConvHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_cmd)],
        states={
            STATE_MENU: [
                MessageHandler(filters.Regex("^(🎁 Создать лот|📋 Мои лоты|💰 Баланс|⚙️ Admin|❓ Помощь)$"), menu_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler),
                CommandHandler("help", help_cmd),
            ],
            STATE_ADMIN_PANEL: [
                CallbackQueryHandler(admin_cb, pattern=r"^adm_")
            ],
            STATE_ADMIN_EDIT_DURS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_durs)
            ],
            STATE_ADMIN_EDIT_INCS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_incs)
            ],
            STATE_ADMIN_DEL_BID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_del_bid)
            ],
            STATE_ADMIN_BAN_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ban_user)
            ],

            STATE_PKG_ASK_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, pkg_count)
            ],
            STATE_PKG_GET_MEDIA: [
                MessageHandler((filters.PHOTO|filters.VIDEO), pkg_get_media)
            ],
            STATE_ASK_BUYNOW: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_buynow)
            ],
            STATE_ASK_LASTCALL: [
                CallbackQueryHandler(lastcall_callback, pattern=r"^(lc_yes|lc_no)$")
            ],
            STATE_ASK_DURATION: [
                CallbackQueryHandler(duration_callback, pattern=r"^dur_")
            ],
            STATE_ASK_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_desc)
            ],
        },
        fallbacks=[
            CommandHandler("start", start_cmd),
            CommandHandler("help", help_cmd)
        ]
    )

    app.add_handler(conv_handler)
    # баланс callback
    app.add_handler(CallbackQueryHandler(balance_cb, pattern=r"^topup$"))
    # аукцион callback
    app.add_handler(CallbackQueryHandler(auction_callback, pattern=r"^(buy_|bid_|timer_|info_)"))

    logging.info("Super Auction Bot is running with all features, ~1000 lines!")
    app.run_polling()

if __name__=="__main__":
    main()