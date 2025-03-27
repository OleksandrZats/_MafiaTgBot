import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest
import os

# === CONFIGURATION ===
TOKEN = os.getenv("BOT_TOKEN")
HOST_USERNAME = os.getenv("HOST_USERNAME")


DEFAULT_ROLES = {
    "Мафія": 1,
    "Дон": 1,
    "Лікар": 1,
    "Комісар": 1
}

# === GLOBAL STATE ===
players = {}  # user_id -> {name, username}
roles_assigned = {}  # user_id -> role
player_number_map = {}  # user_id -> number
host_id = None

game_started = False

# === LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === /join ===
async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_started, host_id
    user = update.effective_user

    if game_started:
        await update.message.reply_text("Гру вже розпочато. Зачекайте на її завершення.")
        return

    if user.username == HOST_USERNAME.strip('@'):
        if host_id is None:
            host_id = user.id
        await update.message.reply_text(
            f"Ви ведучий. Ось список гравців:\n" + format_player_list()
        )
        await update.message.reply_text("Щоб розпочати гру, натисніть /startgame")
    else:
        if user.id not in players:
            await update.message.reply_text("Ви увійшли як гравець. Введіть своє ім'я.")
            players[user.id] = {"name": None, "username": user.username}
        else:
            await update.message.reply_text("Ви вже приєднані. Введіть своє ім'я.")

# === Handle name input ===
async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global host_id
    user = update.effective_user

    if user.id in players and players[user.id]['name'] is None:
        players[user.id]['name'] = update.message.text
        await update.message.reply_text("Ім'я збережено! Очікуйте на початок гри.")

        if host_id:
            msg = f"\U0001F464 Гравець з ім'ям *{players[user.id]['name']}* @{players[user.id]['username']} приєднався"
            await context.bot.send_message(chat_id=host_id, text=msg, parse_mode="Markdown")
    elif user.id in players:
        await update.message.reply_text("Ім'я вже встановлено.")
    else:
        await update.message.reply_text("Спочатку натисніть /join")

# === /startgame ===
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global game_started, roles_assigned, player_number_map
    user = update.effective_user

    if user.id != host_id:
        await update.message.reply_text("Лише ведучий може розпочати гру.")
        return

    if game_started:
        await update.message.reply_text("Гра вже запущена.")
        return

    if len(players) < 2:
        await update.message.reply_text("Недостатньо гравців для початку гри.")
        return

    game_started = True
    roles_assigned = assign_roles()
    player_list = list(players.items())
    random.shuffle(player_list)

    player_number_map.clear()
    for number, (user_id, info) in enumerate(player_list, start=1):
        player_number_map[user_id] = number
        role = roles_assigned[user_id]
        text = f"Гравець №{number} - {info['name']} @{info['username']} - {role}"
        keyboard = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton("Надіслати роль", callback_data=f"send_role:{user_id}")
        )
        await update.message.reply_text(text, reply_markup=keyboard)

    await update.message.reply_text("\u2705 Усі ролі роздані. Щоб надіслати номери, натисніть /sendnumbers")

# === Send Role Callback ===
async def send_role_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("send_role:"):
        user_id = int(data.split(":")[1])
        role = roles_assigned.get(user_id, "Мирний мешканець")

        try:
            await context.bot.send_message(chat_id=user_id, text=f"Ваша роль: {role}")
            original_text = query.message.text
            new_text = original_text + "\n\u2705 Роль надіслана гравцю."
            await query.edit_message_text(new_text)
        except Exception as e:
            await query.edit_message_text(f"Не вдалося надіслати роль: {e}")

# === /sendnumbers ===
async def send_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != host_id:
        await update.message.reply_text("Лише ведучий може використовувати цю команду.")
        return

    if not player_number_map:
        await update.message.reply_text("Номери ще не сформовані. Спочатку запустіть гру через /startgame.")
        return

    for uid, number in player_number_map.items():
        try:
            await context.bot.send_message(chat_id=uid, text=f"Ваш номер у цій грі: {number}")
        except Exception as e:
            await update.message.reply_text(f"Не вдалося надіслати номер гравцю {uid}: {e}")

    await update.message.reply_text("\U0001F4E9 Усі номери надіслані гравцям.")

# === /stopgame ===
async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global players, roles_assigned, game_started, player_number_map, host_id

    user = update.effective_user
    if user.id != host_id:
        await update.message.reply_text("Лише ведучий може завершити гру.")
        return

    for user_id in players:
        try:
            await context.bot.send_message(chat_id=user_id, text="Гру завершено. Щоб приєднатися знову, натисніть /join")
        except Exception:
            pass

    players.clear()
    roles_assigned.clear()
    player_number_map.clear()
    game_started = False
    host_id = None

    await update.message.reply_text("Гру завершено. Усі дані очищено.")

# === Helpers ===
def assign_roles():
    role_counts = DEFAULT_ROLES.copy()
    user_ids = list(players.keys())
    random.shuffle(user_ids)

    assigned = {}
    for role, count in role_counts.items():
        for _ in range(count):
            if user_ids:
                uid = user_ids.pop()
                assigned[uid] = role

    for uid in user_ids:
        assigned[uid] = "Мирний мешканець"

    return assigned

def format_player_list():
    if not players:
        return "Гравців поки що немає."
    return "\n".join(f"- {info['name'] or 'Ім\'я не вказано'} @{info['username']}" for info in players.values())

# === Main ===
def main():
    request = HTTPXRequest(connect_timeout=10.0, read_timeout=20.0)
    app = Application.builder().token(TOKEN).request(request).build()

    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("startgame", start_game))
    app.add_handler(CommandHandler("stopgame", stop_game))
    app.add_handler(CommandHandler("sendnumbers", send_numbers))
    app.add_handler(CallbackQueryHandler(send_role_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name))

    print("Бот запущено...")
    app.run_polling()

if __name__ == "__main__":
    main()
