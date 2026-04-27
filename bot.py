import logging
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# ─── Конфиг ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8720860098:AAHt3mmcnujCASnREzkfCSiRVtMtq9PQ2-g")
SUPPORT_GROUP_ID = int(os.getenv("SUPPORT_GROUP_ID", "-1003954019230"))
TICKETS_FILE = "tickets.json"

# ─── Логирование ──────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Состояния диалога ────────────────────────────────────────────────────────
CHOOSE_CATEGORY, ENTER_NICKNAME, ENTER_DESCRIPTION = range(3)

# ─── Категории тикетов ────────────────────────────────────────────────────────
CATEGORIES = {
    "bug":        ("🐛 Баг сервера",          "🐛"),
    "complaint":  ("😡 Жалоба на игрока",     "😡"),
    "appeal":     ("⚖️ Апелляция наказания",  "⚖️"),
    "account":    ("🔑 Проблема с аккаунтом", "🔑"),
    "boosty":     ("💳 Вопрос по Boosty",     "💳"),
    "other":      ("❓ Другое",               "❓"),
}

# ─── Хранилище тикетов ────────────────────────────────────────────────────────
def load_tickets() -> dict:
    if os.path.exists(TICKETS_FILE):
        with open(TICKETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"counter": 0, "tickets": {}}

def save_tickets(data: dict):
    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def next_ticket_id() -> str:
    data = load_tickets()
    data["counter"] += 1
    save_tickets(data)
    return f"{data['counter']:04d}"

def store_ticket(ticket_id: str, ticket: dict):
    data = load_tickets()
    data["tickets"][ticket_id] = ticket
    save_tickets(data)

def get_ticket(ticket_id: str) -> dict | None:
    data = load_tickets()
    return data["tickets"].get(ticket_id)

def find_ticket_by_thread(thread_id: int) -> tuple[str, dict] | tuple[None, None]:
    data = load_tickets()
    for tid, ticket in data["tickets"].items():
        if ticket.get("thread_id") == thread_id:
            return tid, ticket
    return None, None

def update_ticket(ticket_id: str, updates: dict):
    data = load_tickets()
    if ticket_id in data["tickets"]:
        data["tickets"][ticket_id].update(updates)
        save_tickets(data)

# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Добро пожаловать в поддержку *VanillaBox*!\n\n"
        "Здесь вы можете создать тикет и получить помощь от администрации.\n\n"
        "📋 `/ticket` — создать новый тикет\n"
        "📂 `/mystatus` — статус ваших тикетов",
        parse_mode="Markdown"
    )

# ─── /ticket — начало создания ────────────────────────────────────────────────
async def new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"cat_{key}")]
        for key, (label, _) in CATEGORIES.items()
    ]
    await update.message.reply_text(
        "📋 *Создание тикета*\n\nВыберите категорию обращения:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CHOOSE_CATEGORY

async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_key = query.data.replace("cat_", "")
    context.user_data["category"] = cat_key
    await query.edit_message_text(
        f"Категория: *{CATEGORIES[cat_key][0]}*\n\n"
        "Введите ваш *игровой ник* на сервере VanillaBox:",
        parse_mode="Markdown"
    )
    return ENTER_NICKNAME

async def nickname_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nickname"] = update.message.text.strip()
    await update.message.reply_text(
        "📝 Опишите вашу проблему подробно.\n\n"
        "_Можно прикрепить скриншоты — отправьте фото вместе с текстом или следующим сообщением._",
        parse_mode="Markdown"
    )
    return ENTER_DESCRIPTION

async def description_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cat_key = context.user_data["category"]
    cat_label, cat_emoji = CATEGORIES[cat_key]
    nickname = context.user_data["nickname"]
    description = update.message.text or update.message.caption or "(без текста)"
    photo = update.message.photo[-1] if update.message.photo else None

    ticket_id = next_ticket_id()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    # Создаём топик в группе поддержки
    topic_name = f"{cat_emoji} #{ticket_id} | {nickname}"
    try:
        topic = await context.bot.create_forum_topic(
            chat_id=SUPPORT_GROUP_ID,
            name=topic_name
        )
        thread_id = topic.message_thread_id
    except Exception as e:
        logger.error(f"Ошибка создания топика: {e}")
        await update.message.reply_text(
            "❌ Не удалось создать тикет. Попробуйте позже или напишите в чат Telegram: @VanillaBoxMc"
        )
        return ConversationHandler.END

    # Сообщение в топик
    header = (
        f"🎫 *Тикет #{ticket_id}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📁 Категория: {cat_label}\n"
        f"👤 Игрок: `{nickname}`\n"
        f"🆔 Telegram: @{user.username or user.first_name} (`{user.id}`)\n"
        f"🕐 Время: {now}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 *Описание:*\n{description}\n\n"
        f"_Для ответа игроку используйте /reply {ticket_id} <текст>_\n"
        f"_Для закрытия тикета: /close {ticket_id}_"
    )

    if photo:
        await context.bot.send_photo(
            chat_id=SUPPORT_GROUP_ID,
            photo=photo.file_id,
            caption=header,
            message_thread_id=thread_id,
            parse_mode="Markdown"
        )
    else:
        await context.bot.send_message(
            chat_id=SUPPORT_GROUP_ID,
            text=header,
            message_thread_id=thread_id,
            parse_mode="Markdown"
        )

    # Сохраняем тикет
    store_ticket(ticket_id, {
        "user_id": user.id,
        "username": user.username or user.first_name,
        "nickname": nickname,
        "category": cat_key,
        "description": description,
        "thread_id": thread_id,
        "status": "open",
        "created_at": now
    })

    # Подтверждение пользователю с кнопкой закрытия
    keyboard = [[InlineKeyboardButton("🔒 Закрыть тикет", callback_data=f"close_{ticket_id}")]]
    await update.message.reply_text(
        f"✅ *Тикет #{ticket_id} создан!*\n\n"
        f"Категория: {cat_label}\n"
        f"Администрация ответит вам здесь в личке.\n\n"
        f"💬 Вы можете писать сюда дополнительные сообщения — они будут доставлены в поддержку.\n\n"
        f"⏱ Обычное время ответа: до 24 часов.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Создание тикета отменено.")
    return ConversationHandler.END

# ─── Найти открытый тикет игрока ──────────────────────────────────────────────
def find_open_ticket_by_user(user_id: int) -> tuple[str, dict] | tuple[None, None]:
    data = load_tickets()
    for tid, ticket in data["tickets"].items():
        if ticket.get("user_id") == user_id and ticket.get("status") == "open":
            return tid, ticket
    return None, None

# ─── Сообщение игрока в личку бота → пересылаем в топик ──────────────────────
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    if not message:
        return

    ticket_id, ticket = find_open_ticket_by_user(user.id)
    if not ticket:
        await message.reply_text(
            "У вас нет открытых тикетов.\n"
            "Создайте новый: /ticket"
        )
        return

    text = message.text or message.caption or ""
    photo = message.photo[-1] if message.photo else None
    thread_id = ticket["thread_id"]
    username = f"@{user.username}" if user.username else user.first_name

    msg = f"💬 *Игрок {username}:*\n{text}"

    try:
        if photo:
            await context.bot.send_photo(
                chat_id=SUPPORT_GROUP_ID,
                photo=photo.file_id,
                caption=msg,
                message_thread_id=thread_id,
                parse_mode="Markdown"
            )
        else:
            await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                text=msg,
                message_thread_id=thread_id,
                parse_mode="Markdown"
            )
        await message.reply_text("✅ Сообщение отправлено в поддержку.")
    except Exception as e:
        logger.error(f"Ошибка пересылки от игрока: {e}")
        await message.reply_text("❌ Не удалось отправить сообщение. Попробуйте позже.")

# ─── Кнопка закрытия тикета игроком ──────────────────────────────────────────
async def player_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = query.data.replace("close_", "")
    ticket = get_ticket(ticket_id)

    if not ticket or ticket.get("status") == "closed":
        await query.edit_message_text("Тикет уже закрыт.")
        return

    if ticket["user_id"] != query.from_user.id:
        await query.answer("Это не ваш тикет.", show_alert=True)
        return

    update_ticket(ticket_id, {"status": "closed"})

    try:
        await context.bot.send_message(
            chat_id=SUPPORT_GROUP_ID,
            text=f"🔒 Игрок закрыл тикет #{ticket_id}.",
            message_thread_id=ticket["thread_id"]
        )
        await context.bot.close_forum_topic(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=ticket["thread_id"]
        )
    except Exception:
        pass

    await query.edit_message_text(
        f"🔒 *Тикет #{ticket_id} закрыт.*\n\nЕсли проблема не решена — создайте новый: /ticket",
        parse_mode="Markdown"
    )

# ─── Ответ администратора через личку бота ────────────────────────────────────
# Когда админ пишет в топик группы — пересылаем пользователю
async def handle_group_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.message_thread_id:
        return
    # Игнорируем сообщения от самого бота
    if message.from_user and message.from_user.is_bot:
        return

    thread_id = message.message_thread_id
    ticket_id, ticket = find_ticket_by_thread(thread_id)
    if not ticket or ticket.get("status") == "closed":
        return

    text = message.text or message.caption or ""
    if not text or text.startswith("/"):
        return

    admin_name = message.from_user.first_name or "Администратор"
    try:
        await context.bot.send_message(
            chat_id=ticket["user_id"],
            text=(
                f"📬 *Ответ по тикету #{ticket_id}*\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👨‍💼 {admin_name}:\n\n"
                f"{text}"
            ),
            parse_mode="Markdown"
        )
        # Ставим галочку в топике
        await message.reply_text("✅ Ответ доставлен игроку.", message_thread_id=thread_id)
    except Exception as e:
        logger.error(f"Ошибка отправки ответа: {e}")
        await message.reply_text(f"❌ Не удалось доставить ответ: {e}", message_thread_id=thread_id)

# ─── /close <ticket_id> ───────────────────────────────────────────────────────
async def close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /close <номер_тикета>")
        return

    ticket_id = context.args[0].zfill(4)
    ticket = get_ticket(ticket_id)
    if not ticket:
        await update.message.reply_text(f"❌ Тикет #{ticket_id} не найден.")
        return

    update_ticket(ticket_id, {"status": "closed"})

    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            chat_id=ticket["user_id"],
            text=(
                f"🔒 *Тикет #{ticket_id} закрыт*\n\n"
                f"Ваше обращение было рассмотрено администрацией.\n"
                f"Если проблема не решена — создайте новый тикет командой /ticket."
            ),
            parse_mode="Markdown"
        )
    except Exception:
        pass

    # Закрываем топик
    try:
        await context.bot.close_forum_topic(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=ticket["thread_id"]
        )
    except Exception:
        pass

    await update.message.reply_text(f"✅ Тикет #{ticket_id} закрыт.")

# ─── /mystatus ────────────────────────────────────────────────────────────────
async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_tickets()
    user_tickets = [
        (tid, t) for tid, t in data["tickets"].items()
        if t["user_id"] == user_id
    ]
    if not user_tickets:
        await update.message.reply_text("У вас нет тикетов. Создайте: /ticket")
        return

    lines = ["📂 *Ваши тикеты:*\n"]
    for tid, t in sorted(user_tickets, reverse=True)[:10]:
        status_icon = "🟢" if t["status"] == "open" else "🔴"
        cat_label = CATEGORIES.get(t["category"], ("❓ Другое",))[0]
        lines.append(f"{status_icon} *#{tid}* — {cat_label}\n   📅 {t['created_at']}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── Запуск ───────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("ticket", new_ticket)],
        states={
            CHOOSE_CATEGORY:   [CallbackQueryHandler(category_chosen, pattern="^cat_")],
            ENTER_NICKNAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, nickname_entered)],
            ENTER_DESCRIPTION: [MessageHandler(
                (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
                description_entered
            )],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("close", close_ticket))
    app.add_handler(CommandHandler("mystatus", my_status))
    app.add_handler(CallbackQueryHandler(player_close_callback, pattern="^close_"))

    # Ответы игроков из лички
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
        handle_user_message
    ))

    # Ответы админов из группы
    app.add_handler(MessageHandler(
        filters.Chat(SUPPORT_GROUP_ID) & filters.TEXT & ~filters.COMMAND,
        handle_group_reply
    ))

    logger.info("🚀 VanillaBox Support Bot запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
