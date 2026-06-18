import telebot
from config import TELEGRAM_TOKEN
from services.classifier_service import classify_food
from services.gemini_service import chat_with_agent, clear_chat
import threading

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Store user location
user_location = {}

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
        "• 'I want ramen'\n"
        "• 'Which one is cheapest?'\n"
        "• 'Is there parking nearby?'\n\n"
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

    # Check if there's a pending food request in chat history
    bot.send_chat_action(chat_id, "typing")
    response = chat_with_agent(
        chat_id,
        "I just shared my location. If I previously mentioned a food I want, please search for it now.",
        lat,
        lng
    )
    bot.reply_to(message, response)

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    chat_id = message.chat.id
    bot.reply_to(message, "Analyzing your food photo...")

    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    image_bytes = bot.download_file(file_info.file_path)

    food, confidence = classify_food(image_bytes)

    loc = user_location.get(chat_id)
    lat = loc["lat"] if loc else None
    lng = loc["lng"] if loc else None

    if confidence < 0.5:
        bot.reply_to(message,
            f"🤔 This looks like it could be {food} (confidence: {confidence:.0%})\n\n"
            f"If that's wrong, just type what food you actually want and I'll search for it!"
        )
        user_state[chat_id] = {"food": food}
    else:
        message_to_agent = f"I'm craving {food}. Find me nearby restaurants."
        response = chat_with_agent(chat_id, message_to_agent, lat, lng)
        bot.reply_to(message, response)

    loc = user_location.get(chat_id)
    lat = loc["lat"] if loc else None
    lng = loc["lng"] if loc else None

    message_to_agent = f"I'm craving {food} (identified from photo with {confidence:.0%} confidence). Find me nearby restaurants."
    response = chat_with_agent(chat_id, message_to_agent, lat, lng)

    if not loc:
        response = f"🍽️ Looks like *{food}*! (confidence: {confidence:.0%})\n\nShare your location so I can find nearby spots 📍"

    bot.reply_to(message, response)
    
def send_typing(chat_id):
    try:
        bot.send_chat_action(chat_id, "typing")
    except:
        pass

@bot.message_handler(content_types=["text"])
def handle_text(message):
    if message.text.startswith("/"):
        return

    chat_id = message.chat.id
    loc = user_location.get(chat_id)
    lat = loc["lat"] if loc else None
    lng = loc["lng"] if loc else None

    threading.Thread(target=send_typing, args=(chat_id,)).start()
    response = chat_with_agent(chat_id, message.text, lat, lng)
    bot.reply_to(message, response)

@bot.message_handler(content_types=["text"])
def handle_text(message):
    if message.text.startswith("/"):
        return

    chat_id = message.chat.id
    loc = user_location.get(chat_id)
    lat = loc["lat"] if loc else None
    lng = loc["lng"] if loc else None

    response = chat_with_agent(chat_id, message.text, lat, lng)
    bot.reply_to(message, response)

# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🤖 WhereDatFood bot is running...")
    bot.infinity_polling()