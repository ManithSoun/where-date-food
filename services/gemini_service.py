from groq import Groq
import json
from config import GROQ_API_KEY
from services.places_service import find_restaurants

client = Groq(api_key=GROQ_API_KEY)

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_restaurant",
            "description": "Find a list of nearby restaurants based on food preference and user location. ALWAYS call this when user asks for food or restaurant recommendations. When user refines with price or other filters, combine with the previous food type e.g. if user asked for sushi then says cheap, search for 'cheap sushi'. NEVER make up restaurant names.",
            "parameters": {
                "type": "object",
                "properties": {
                    "preference": {
                        "type": "string",
                        "description": "The user's food preference e.g. 'pizza', 'cheap Khmer food', 'coffee shop to study'"
                    }
                },
                "required": ["preference"]
            }
        }
    }
]

SYSTEM_PROMPT = """You are WhereDatFood, a friendly food recommendation assistant for Phnom Penh, Cambodia.

IMPORTANT RULES:
- When user asks for food or restaurant recommendations, ALWAYS call get_restaurant tool immediately
- NEVER make up restaurant names
- NEVER say you are searching or waiting
- Just call the tool and present the real results

When presenting restaurant results:
- ONE sentence intro max
- Show the list as-is from the tool results
- NO top pick recommendation
- NO closing message
- Keep it clean and scannable

When user asks follow-up questions about results:
- NEVER call get_restaurant again
- Keep answers to 1-2 sentences max
- Be direct, no filler words
- Answer only from previous results
- For price questions ("cheapest", "cheap", "budget"): compare price_level values from results and recommend the cheapest one
- For distance questions ("closest", "nearest"): compare distance values and recommend the closest one  
- For rating questions ("best", "highest rated"): compare rating values and recommend the highest rated
- For info questions ("tell me more about #1", "what's the address"): pull from the results
- Only call get_restaurant again if user asks for a COMPLETELY different food type like "actually I want pizza instead"

Answer directly from the context of previous results.
Be helpful and conversational

General rules:
- Keep responses short and friendly
- Use emojis occasionally but not excessively
- No yapping or unnecessary filler sentences
- Always respond in the same language the user uses"""

chat_sessions = {}

def get_history(chat_id: int):
    if chat_id not in chat_sessions:
        chat_sessions[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return chat_sessions[chat_id]

def get_trimmed_history(chat_id: int):
    history = get_history(chat_id)
    # Keep system prompt + last 10 messages
    if len(history) > 11:
        return [history[0]] + history[-10:]
    return history

def clear_chat(chat_id: int):
    if chat_id in chat_sessions:
        del chat_sessions[chat_id]

# ─── Agent ────────────────────────────────────────────────────────────────────
def chat_with_agent(chat_id: int, message: str, lat: float = None, lng: float = None) -> str:
    try:
        history = get_history(chat_id)

        if lat and lng:
            message = f"{message}\n[User location: {lat}, {lng}]"

        history.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model=MODEL,
            messages=get_trimmed_history(chat_id),
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=1024
        )

        msg = response.choices[0].message

        if msg.tool_calls:
          tc = msg.tool_calls[0]
          preference = json.loads(tc.function.arguments).get("preference", "restaurant")

          if not lat or not lng:
              return "Please share your location first so I can find nearby restaurants! 📍"

          restaurants = find_restaurants(lat, lng, preference)

          if not restaurants:
              return f"Sorry, I couldn't find any {preference} restaurants nearby. Try a different area!"

          lines = [f"🍽️ *{preference.title()}* spots near you:\n"]
          lines = [f"🍽️ {preference.title()} spots near you:\n"]
          
          for r in restaurants:
              lines.append(
                  f"🏪 {r['name']}\n"
                  f"📍 {r['address']}\n"
                  f"⭐ {r['rating']}  💰 {r['price_level']}  📏 {r['distance']}\n"
                  f"🔗 {r['maps_link']}\n"
              )

          reply = "\n".join(lines)
          history.append(msg)
          history.append({"role": "assistant", "content": reply})
          return reply

        reply = msg.content
        history.append({"role": "assistant", "content": reply})
        return reply

    except Exception as e:
        print(f"ERROR: {e}")
        return "⚠️ Sorry, I'm having trouble right now. Please try again in a moment!"