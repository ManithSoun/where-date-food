import threading
import telebot
from config import TELEGRAM_TOKEN
from services.classifier_service import classify_food
from services.gemini_service import chat_with_agent, clear_chat
from services.places_service import parse_radius

bot = telebot.TeleBot(TELEGRAM_TOKEN)

user_location = {}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_loc(chat_id):
    loc = user_location.get(chat_id)
    if loc:
        return loc["lat"], loc["lng"]
    return None, None

def send_typing_loop(chat_id, stop_event):
    while not stop_event.is_set():
        try:
            bot.send_chat_action(chat_id, "typing")
        except Exception:
            pass
        stop_event.wait(4)

def reply_with_typing(chat_id, message, agent_fn):
    stop = threading.Event()
    t = threading.Thread(target=send_typing_loop, args=(chat_id, stop))
    t.start()
    try:
        response = agent_fn()
    finally:
        stop.set()
        t.join()
    bot.reply_to(message, response)


# ─── Handlers ─────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def start(message):
    clear_chat(message.chat.id)
    bot.reply_to(
        message,
        "🍜 *Welcome to WhereDatFood!*\n\n"
        "I'm your AI food assistant for Phnom Penh!\n\n"
        "You can:\n"
        "📝 Type what you're craving\n"
        "📸 Send a food photo\n"
        "📍 Share your location\n"
        "💬 Ask me anything about nearby places!\n\n"
        "Start by sharing your location or telling me what you want to eat 👇",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=["help"])
def help_command(message):
    bot.reply_to(
        message,
        "🤖 *How to use WhereDatFood:*\n\n"
        "1️⃣ Share your location (📎 → Location)\n"
        "2️⃣ Type what you're craving or send a food photo\n"
        "3️⃣ Ask follow-up questions about the results!\n\n"
        "Examples:\n"
        "• 'I want ramen near me'\n"
        "• 'Find pho within 2 km'\n"
        "• 'Which one is cheapest?'\n\n"
        "Use /start to reset the conversation.",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=["reset"])
def reset(message):
    clear_chat(message.chat.id)
    user_location.pop(message.chat.id, None)
    bot.reply_to(message, "🔄 Conversation reset! Start fresh 👇")

@bot.message_handler(content_types=["location"])
def handle_location(message):
    chat_id = message.chat.id
    lat = message.location.latitude
    lng = message.location.longitude
    user_location[chat_id] = {"lat": lat, "lng": lng}

    prompt = "I just shared my location. If I previously mentioned a food I want, please search for it now."
    reply_with_typing(chat_id, message, lambda: chat_with_agent(chat_id, prompt, lat, lng))

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    chat_id = message.chat.id
    lat, lng = get_loc(chat_id)

    bot.send_chat_action(chat_id, "typing")
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    image_bytes = bot.download_file(file_info.file_path)
    food, confidence = classify_food(image_bytes)

    if not lat:
        bot.reply_to(
            message,
            f"🍽️ Looks like *{food}*! (confidence: {confidence:.0%})\n\n"
            "Share your location so I can find nearby spots 📍",
            parse_mode="Markdown"
        )
        return

    if confidence < 0.5:
        bot.reply_to(
            message,
            f"🤔 This looks like it could be *{food}* (confidence: {confidence:.0%})\n\n"
            "If that's wrong, just type what food you actually want!",
            parse_mode="Markdown"
        )
        return

    prompt = f"I'm craving {food} (identified from photo, {confidence:.0%} confidence). Find me nearby restaurants."
    reply_with_typing(chat_id, message, lambda: chat_with_agent(chat_id, prompt, lat, lng))

@bot.message_handler(content_types=["text"])
def handle_text(message):
    if message.text.startswith("/"):
        return

    chat_id = message.chat.id
    lat, lng = get_loc(chat_id)
    text = message.text

    reply_with_typing(chat_id, message, lambda: chat_with_agent(chat_id, text, lat, lng))

# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🤖 WhereDatFood bot is running...")
    bot.infinity_polling()