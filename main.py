import os
import json
import time
from datetime import datetime
from typing import Dict, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
async def chatid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Chat ID: {update.effective_chat.id}")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

# Простая нумерация заявок (в памяти процесса)
NEXT_ID = 1

# Состояния шагов
STEP_NAME = 1
STEP_USERNAME = 2
STEP_PROMPT = 3
STEP_SOURCE_PHOTOS = 4
STEP_SET3 = 5
STEP_CARICATURE = 6
STEP_STICKERS = 7
STEP_HARDEST = 8
STEP_REVIEW = 9

def now_str() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M")

def user_key(update: Update) -> str:
    return str(update.effective_user.id)

def init_user_state(ctx: ContextTypes.DEFAULT_TYPE, uid: str) -> None:
    ctx.application.bot_data.setdefault("users", {})
    users = ctx.application.bot_data["users"]
    users.setdefault(uid, {"step": STEP_NAME, "data": {}, "files": {}})

def set_step(ctx: ContextTypes.DEFAULT_TYPE, uid: str, step: int) -> None:
    ctx.application.bot_data["users"][uid]["step"] = step

def get_state(ctx: ContextTypes.DEFAULT_TYPE, uid: str) -> Dict[str, Any]:
    return ctx.application.bot_data["users"][uid]

def main_menu() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("🏆 Сдать итоговую работу", callback_data="menu_submit")],
        [InlineKeyboardButton("📋 Требования к работе", callback_data="menu_requirements")],
        [InlineKeyboardButton("💬 Связаться со мной", callback_data="menu_help")],
    ]
    return InlineKeyboardMarkup(kb)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Это бот для сдачи итоговой работы.\n\nВыберите действие:",
        reply_markup=main_menu()
    )

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    uid = user_key(update)
    init_user_state(context, uid)

    if query.data == "menu_submit":
        # старт сдачи
        context.application.bot_data["users"][uid] = {"step": STEP_NAME, "data": {}, "files": {}}
        await query.message.reply_text("Шаг 1/9. Напишите имя и фамилию (как к вам обращаться).")
        return

    if query.data == "menu_requirements":
        await query.message.reply_text(
            "📋 Требования к итоговой:\n"
            "— Итоговый промт (текст)\n"
            "— Исходные фото (1–3)\n"
            "— Нейрофотосет (3 фото)\n"
            "— Нейрошарж (1 фото)\n"
            "— Стикеры (5 фото или 1 ZIP)\n"
            "— Трудности (текст)\n"
            "— Отзыв (текст)\n\n"
            "Сдача происходит по шагам через кнопку «Сдать итоговую работу»."
        )
        return

    if query.data == "menu_help":
        await query.message.reply_text(
            "💬 По любым вопросам можно написать мне в личные сообщения.\n"
            "Если что-то не получается — просто напишите, разберём."
        )
        return

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = user_key(update)
    init_user_state(context, uid)
    st = get_state(context, uid)
    step = st["step"]
    text = (update.message.text or "").strip()

    if step == STEP_NAME:
        st["data"]["name"] = text
        set_step(context, uid, STEP_USERNAME)
        await update.message.reply_text("Шаг 2/9. Напишите ваш Telegram @ник (например: @name).")
        return

    if step == STEP_USERNAME:
        st["data"]["username"] = text
        set_step(context, uid, STEP_PROMPT)
        await update.message.reply_text("Шаг 3/9. Отправьте итоговый промт одним сообщением.")
        return

    if step == STEP_PROMPT:
        st["data"]["prompt"] = text
        set_step(context, uid, STEP_SOURCE_PHOTOS)
        await update.message.reply_text("Шаг 4/9. Прикрепите исходные фото (1–3 фото).")
        return

    if step == STEP_HARDEST:
        st["data"]["hardest"] = text
        set_step(context, uid, STEP_REVIEW)
        await update.message.reply_text("Шаг 9/9. Напишите отзыв о курсе (можно коротко).")
        return

    if step == STEP_REVIEW:
        st["data"]["review"] = text
        await finalize_submission(update, context)
        return

    # Если текст пришёл не в тот шаг
    await update.message.reply_text("Сейчас ожидаю файлы по шагу. Пожалуйста, следуйте подсказкам бота.")

def _get_file_id_from_message(update: Update) -> str | None:
    msg = update.message
    if msg.document:
        return msg.document.file_id
    if msg.photo:
        return msg.photo[-1].file_id
    return None

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = user_key(update)
    init_user_state(context, uid)
    st = get_state(context, uid)
    step = st["step"]
    file_id = _get_file_id_from_message(update)

    if not file_id:
        await update.message.reply_text("Не вижу файл. Отправьте фото или документ (ZIP).")
        return

    files = st["files"]

    if step == STEP_SOURCE_PHOTOS:
        files.setdefault("source", [])
        files["source"].append(file_id)
        if len(files["source"]) >= 1:
            # даём возможность отправить до 3, потом перейти кнопкой
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Дальше (к фотосету)", callback_data="next_from_source")]
            ])
            await update.message.reply_text(
                f"Исходник принят ✅ Сейчас у вас: {len(files['source'])}/3.\n"
                "Можете отправить ещё фото или нажмите «Дальше».",
                reply_markup=kb
            )
        return

    if step == STEP_SET3:
        files.setdefault("set3", [])
        files["set3"].append(file_id)
        if len(files["set3"]) < 3:
            await update.message.reply_text(f"Фото {len(files['set3'])}/3 принято ✅ Отправьте ещё.")
            return
        if len(files["set3"]) == 3:
            set_step(context, uid, STEP_CARICATURE)
            await update.message.reply_text("Шаг 6/9. Прикрепите 1 нейрошарж (1 фото).")
            return

    if step == STEP_CARICATURE:
        files["caricature"] = file_id
        set_step(context, uid, STEP_STICKERS)
        await update.message.reply_text("Шаг 7/9. Прикрепите 5 стикеров (5 фото) или 1 ZIP архив.")
        return

    if step == STEP_STICKERS:
        files.setdefault("stickers", [])
        files["stickers"].append(file_id)

        # Если это zip — сразу принимаем как 1 файл и идём дальше
        if update.message.document and (update.message.document.file_name or "").lower().endswith(".zip"):
            set_step(context, uid, STEP_HARDEST)
            await update.message.reply_text("ZIP принят ✅\nШаг 8/9. Коротко: что было труднее всего?")
            return

        # Иначе ждём 5 фото
        if len(files["stickers"]) < 5:
            await update.message.reply_text(f"Стикер {len(files['stickers'])}/5 принят ✅ Отправьте ещё.")
            return

        if len(files["stickers"]) == 5:
            set_step(context, uid, STEP_HARDEST)
            await update.message.reply_text("Стикеры приняты ✅\nШаг 8/9. Коротко: что было труднее всего?")
            return

    await update.message.reply_text("Сейчас ожидаю другой шаг. Нажмите /start и выберите «Сдать итоговую работу» заново, если запутались.")

async def next_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    uid = user_key(update)
    init_user_state(context, uid)
    st = get_state(context, uid)

    if query.data == "next_from_source":
        set_step(context, uid, STEP_SET3)
        await query.message.reply_text("Шаг 5/9. Прикрепите 3 фото нейрофотосета (ровно 3 файла).")
        return

async def finalize_submission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global NEXT_ID
    uid = user_key(update)
    st = get_state(context, uid)

    req_id = NEXT_ID
    NEXT_ID += 1

    data = st["data"]
    files = st["files"]

    # Сообщение в админ-чат
    header = (
        f"🧾 <b>Заявка #{req_id}</b>\n"
        f"🕒 {now_str()}\n\n"
        f"<b>Имя:</b> {data.get('name','')}\n"
        f"<b>@ник:</b> {data.get('username','')}\n\n"
        f"<b>Итоговый промт:</b>\n{data.get('prompt','')}\n\n"
        f"<b>Труднее всего:</b>\n{data.get('hardest','')}\n\n"
        f"<b>Отзыв:</b>\n{data.get('review','')}\n"
    )

    # Кнопки админа (управление)
    admin_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Принято", callback_data=f"admin_accept:{uid}:{req_id}"),
            InlineKeyboardButton("🔁 Доработка", callback_data=f"admin_rework:{uid}:{req_id}"),
            InlineKeyboardButton("🏆 Сертификат", callback_data=f"admin_cert:{uid}:{req_id}"),
        ]
    ])

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=header,
        reply_markup=admin_kb,
        parse_mode=ParseMode.HTML
    )

    # Отправка файлов в админ-чат
    async def send_file(fid: str):
        # fid может быть photo или document — отправляем как документ, чтобы сохранить качество
        await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=fid)

    for fid in files.get("source", []):
        await send_file(fid)
    for fid in files.get("set3", []):
        await send_file(fid)
    if files.get("caricature"):
        await send_file(files["caricature"])
    for fid in files.get("stickers", []):
        await send_file(fid)

    # Ответ ученику
    await update.message.reply_text(
        f"Готово ✅\n"
        f"Ваша работа отправлена на проверку.\n"
        f"Номер заявки: #{req_id}\n"
        f"Статус: На проверке."
    )

    # Сброс состояния
    context.application.bot_data["users"][uid] = {"step": STEP_NAME, "data": {}, "files": {}}

# Админские кнопки
async def admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("admin_accept:"):
        _, uid, req_id = data.split(":")
        await context.bot.send_message(chat_id=int(uid),
                                       text=f"Работа #{req_id} принята ✅\n"
                                            f"Для сертификата пришлите, пожалуйста, ФИО (как написать в сертификате).")
        await query.message.reply_text(f"✅ Отправлено ученику: работа #{req_id} принята.")
        return

    if data.startswith("admin_cert:"):
        _, uid, req_id = data.split(":")
        await context.bot.send_message(chat_id=int(uid),
                                       text=f"Поздравляю! Работа #{req_id} закрыта 🏆\n"
                                            f"Сертификат готов ✅")
        await query.message.reply_text(f"🏆 Отправлено ученику: сертификат по работе #{req_id}.")
        return

    if data.startswith("admin_rework:"):
        _, uid, req_id = data.split(":")
        # попросим админа написать текст следующим сообщением в админ-чате
        context.application.bot_data["pending_rework"] = {"uid": int(uid), "req_id": req_id, "admin_chat": query.message.chat_id}
        await query.message.reply_text("✍️ Напишите одним сообщением, что нужно доработать. Я отправлю это ученику.")
        return

async def admin_rework_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending = context.application.bot_data.get("pending_rework")
    if not pending:
        return

    # только из админ-чата
    if update.message.chat_id != pending["admin_chat"]:
        return

    text = (update.message.text or "").strip()
    uid = pending["uid"]
    req_id = pending["req_id"]

    await context.bot.send_message(chat_id=uid, text=f"По работе #{req_id} нужна доработка 🔁\n\n{text}")
    await update.message.reply_text("🔁 Комментарий отправлен ученику.")
    context.application.bot_data["pending_rework"] = None

def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if not ADMIN_CHAT_ID:
        raise RuntimeError("ADMIN_CHAT_ID is not set")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chatid", chatid_cmd))
    async def chatid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Chat ID: {update.effective_chat.id}")
app.add_handler(CommandHandler("chatid", chatid_cmd))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(next_buttons, pattern="^next_"))
    app.add_handler(CallbackQueryHandler(admin_actions, pattern="^admin_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, file_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_rework_text))
    return app

if __name__ == "__main__":
    app = build_app()
    app.run_polling(close_loop=False)
