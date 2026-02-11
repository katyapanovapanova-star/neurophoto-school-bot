import os
from datetime import datetime
from typing import Dict, Any, Optional

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

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))  # твой личный Telegram ID

# Шаги
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

def uid(update: Update) -> int:
    return update.effective_user.id

def chat_id(update: Update) -> int:
    return update.effective_chat.id

def ensure_storage(app: Application) -> None:
    app.bot_data.setdefault("users", {})        # user_id -> state
    app.bot_data.setdefault("next_request_id", 1)
    app.bot_data.setdefault("pending_rework", None)  # {"student_id":..., "req_id":..., "admin_msg_chat_id":...}

def init_user(app: Application, user_id: int) -> None:
    ensure_storage(app)
    users = app.bot_data["users"]
    if user_id not in users:
        users[user_id] = {"step": STEP_NAME, "data": {}, "files": {}}

def reset_user(app: Application, user_id: int) -> None:
    app.bot_data["users"][user_id] = {"step": STEP_NAME, "data": {}, "files": {}}

def get_user(app: Application, user_id: int) -> Dict[str, Any]:
    return app.bot_data["users"][user_id]

def main_menu() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("🏆 Сдать итоговую работу", callback_data="menu_submit")],
        [InlineKeyboardButton("📋 Требования к работе", callback_data="menu_requirements")],
        [InlineKeyboardButton("💬 Связаться со мной", callback_data="menu_help")],
    ]
    return InlineKeyboardMarkup(kb)

def next_from_source_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Дальше (к фотосету)", callback_data="next_from_source")]
    ])

def admin_kb(student_id: int, req_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Принято", callback_data=f"admin_accept:{student_id}:{req_id}"),
            InlineKeyboardButton("🔁 Доработка", callback_data=f"admin_rework:{student_id}:{req_id}"),
            InlineKeyboardButton("🏆 Сертификат", callback_data=f"admin_cert:{student_id}:{req_id}"),
        ]
    ])

def file_id_from_update(update: Update) -> Optional[str]:
    msg = update.message
    if msg is None:
        return None
    if msg.document:
        return msg.document.file_id
    if msg.photo:
        return msg.photo[-1].file_id
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_storage(context.application)
    await update.message.reply_text(
        "Привет! Это бот для сдачи итоговой работы.\n\nВыберите действие:",
        reply_markup=main_menu()
    )

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"Ваш User ID: {update.effective_user.id}\n"
        f"Chat ID текущего чата: {update.effective_chat.id}"
    )

async def chatid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Chat ID: {update.effective_chat.id}")

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_storage(context.application)
    query = update.callback_query
    await query.answer()

    user_id = uid(update)
    init_user(context.application, user_id)

    if query.data == "menu_submit":
        reset_user(context.application, user_id)
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
            "— Что было труднее всего (текст)\n"
            "— Отзыв о курсе (текст)\n\n"
            "Нажмите «Сдать итоговую работу» и сдавайте по шагам."
        )
        return

    if query.data == "menu_help":
        await query.message.reply_text(
            "💬 По любым вопросам можно написать мне в личные сообщения.\n"
            "Если что-то не получается — просто напишите, разберём."
        )
        return

async def next_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_storage(context.application)
    query = update.callback_query
    await query.answer()
    user_id = uid(update)
    init_user(context.application, user_id)
    st = get_user(context.application, user_id)

    if query.data == "next_from_source":
        st["step"] = STEP_SET3
        await query.message.reply_text("Шаг 5/9. Прикрепите 3 фото нейрофотосета (ровно 3 файла).")
        return

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_storage(context.application)
    user_id = uid(update)
    init_user(context.application, user_id)
    st = get_user(context.application, user_id)

    text = (update.message.text or "").strip()
    step = st["step"]

    if step == STEP_NAME:
        st["data"]["name"] = text
        st["step"] = STEP_USERNAME
        await update.message.reply_text("Шаг 2/9. Напишите ваш Telegram @ник (например: @name).")
        return

    if step == STEP_USERNAME:
        st["data"]["username"] = text
        st["step"] = STEP_PROMPT
        await update.message.reply_text("Шаг 3/9. Отправьте итоговый промт одним сообщением.")
        return

    if step == STEP_PROMPT:
        st["data"]["prompt"] = text
        st["step"] = STEP_SOURCE_PHOTOS
        await update.message.reply_text("Шаг 4/9. Прикрепите исходные фото (1–3 фото).")
        return

    if step == STEP_HARDEST:
        st["data"]["hardest"] = text
        st["step"] = STEP_REVIEW
        await update.message.reply_text("Шаг 9/9. Напишите отзыв о курсе (можно коротко).")
        return

    if step == STEP_REVIEW:
        st["data"]["review"] = text
        await finalize_submission(update, context)
        return

    # если текст пришёл когда ждём файлы
    await update.message.reply_text("Сейчас ожидаю файлы по шагу. Пожалуйста, следуйте подсказкам бота.")

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_storage(context.application)
    user_id = uid(update)
    init_user(context.application, user_id)
    st = get_user(context.application, user_id)

    step = st["step"]
    fid = file_id_from_update(update)
    if not fid:
        await update.message.reply_text("Не вижу файл. Отправьте фото или документ (ZIP).")
        return

    files = st["files"]

    if step == STEP_SOURCE_PHOTOS:
        files.setdefault("source", [])
        files["source"].append(fid)
        await update.message.reply_text(
            f"Исходник принят ✅ Сейчас: {len(files['source'])}/3.\n"
            "Можете отправить ещё фото или нажмите «Дальше».",
            reply_markup=next_from_source_kb()
        )
        return

    if step == STEP_SET3:
        files.setdefault("set3", [])
        files["set3"].append(fid)
        n = len(files["set3"])
        if n < 3:
            await update.message.reply_text(f"Фото {n}/3 принято ✅ Отправьте ещё.")
            return
        if n == 3:
            st["step"] = STEP_CARICATURE
            await update.message.reply_text("Шаг 6/9. Прикрепите 1 нейрошарж (1 фото).")
            return
        # если прислали больше 3 — игнорим лишнее
        await update.message.reply_text("Уже получено 3/3 фото. Переходим дальше.")
        return

    if step == STEP_CARICATURE:
        files["caricature"] = fid
        st["step"] = STEP_STICKERS
        await update.message.reply_text("Шаг 7/9. Прикрепите 5 стикеров (5 фото) или 1 ZIP архив.")
        return

    if step == STEP_STICKERS:
        # если zip — принимаем как один файл и идём дальше
        if update.message.document and (update.message.document.file_name or "").lower().endswith(".zip"):
            files.setdefault("stickers_zip", [])
            files["stickers_zip"].append(fid)
            st["step"] = STEP_HARDEST
            await update.message.reply_text("ZIP принят ✅\nШаг 8/9. Коротко: что было труднее всего?")
            return

        files.setdefault("stickers", [])
        files["stickers"].append(fid)
        n = len(files["stickers"])
        if n < 5:
            await update.message.reply_text(f"Стикер {n}/5 принят ✅ Отправьте ещё.")
            return
        if n == 5:
            st["step"] = STEP_HARDEST
            await update.message.reply_text("Стикеры приняты ✅\nШаг 8/9. Коротко: что было труднее всего?")
            return
        await update.message.reply_text("Уже получено 5/5 стикеров. Переходим дальше.")
        return

    await update.message.reply_text("Сейчас ожидаю другой шаг. Нажмите /start и начните сдачу заново, если запутались.")

async def finalize_submission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    user_id = uid(update)
    st = get_user(app, user_id)

    req_id = app.bot_data["next_request_id"]
    app.bot_data["next_request_id"] += 1

    data = st["data"]
    files = st["files"]

    header = (
        f"🧾 <b>Заявка #{req_id}</b>\n"
        f"🕒 {now_str()}\n\n"
        f"<b>Имя:</b> {data.get('name','')}\n"
        f"<b>@ник:</b> {data.get('username','')}\n\n"
        f"<b>Итоговый промт:</b>\n{data.get('prompt','')}\n\n"
        f"<b>Труднее всего:</b>\n{data.get('hardest','')}\n\n"
        f"<b>Отзыв:</b>\n{data.get('review','')}\n"
    )

    # Отправка в админ-чат
    if ADMIN_CHAT_ID != 0 and ADMIN_CHAT_ID != 123:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=header,
            parse_mode=ParseMode.HTML,
            reply_markup=admin_kb(user_id, req_id)
        )

        async def send_doc(fid: str):
            # отправляем как документ, чтобы не терять качество
            await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=fid)

        for fid in files.get("source", []):
            await send_doc(fid)
        for fid in files.get("set3", []):
            await send_doc(fid)
        if files.get("caricature"):
            await send_doc(files["caricature"])
        for fid in files.get("stickers", []):
            await send_doc(fid)
        for fid in files.get("stickers_zip", []):
            await send_doc(fid)
    else:
        # если админ чат ещё не настроен
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ Админ-чат ещё не настроен (ADMIN_CHAT_ID).\n"
                 "Работа принята ботом, но пока не отправлена на проверку."
        )

    await update.message.reply_text(
        f"Готово ✅\n"
        f"Ваша работа отправлена на проверку.\n"
        f"Номер заявки: #{req_id}\n"
        f"Статус: На проверке."
    )

    reset_user(app, user_id)

def is_admin(update: Update) -> bool:
    # управлять кнопками может только ты (по ADMIN_USER_ID)
    return ADMIN_USER_ID != 0 and uid(update) == ADMIN_USER_ID

async def admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_storage(context.application)
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        await query.message.reply_text("⛔️ Нет доступа.")
        return

    data = query.data or ""
    if data.startswith("admin_accept:"):
        _, student_id, req_id = data.split(":")
        await context.bot.send_message(
            chat_id=int(student_id),
            text=f"Работа #{req_id} принята ✅\n"
                 "Для сертификата пришлите, пожалуйста, ФИО (как написать в сертификате)."
        )
        await query.message.reply_text(f"✅ Отправлено ученику: работа #{req_id} принята.")
        return

    if data.startswith("admin_cert:"):
        _, student_id, req_id = data.split(":")
        await context.bot.send_message(
            chat_id=int(student_id),
            text=f"Поздравляю! Работа #{req_id} закрыта 🏆\nСертификат готов ✅"
        )
        await query.message.reply_text(f"🏆 Отправлено ученику: сертификат по работе #{req_id}.")
        return

    if data.startswith("admin_rework:"):
        _, student_id, req_id = data.split(":")
        context.application.bot_data["pending_rework"] = {
            "student_id": int(student_id),
            "req_id": req_id,
            "admin_msg_chat_id": chat_id(update),
        }
        await query.message.reply_text("✍️ Напишите одним сообщением, что нужно доработать. Я отправлю это ученику.")
        return

async def admin_rework_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending = context.application.bot_data.get("pending_rework")
    if not pending:
        return

    # Только из того же чата, где нажали кнопку (админ-чат)
    if chat_id(update) != pending["admin_msg_chat_id"]:
        return

    if not is_admin(update):
        return

    text = (update.message.text or "").strip()
    student_id = pending["student_id"]
    req_id = pending["req_id"]

    await context.bot.send_message(
        chat_id=student_id,
        text=f"По работе #{req_id} нужна доработка 🔁\n\n{text}"
    )
    await update.message.reply_text("🔁 Комментарий отправлен ученику.")
    context.application.bot_data["pending_rework"] = None

def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = Application.builder().token(BOT_TOKEN).build()
    ensure_storage(app)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
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
