from groq import Groq
import json
from config import GROQ_API_KEY
from services.places_service import find_restaurants, parse_radius, DEFAULT_RADIUS

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
def get_session(chat_id: int) -> dict:
    if chat_id not in chat_sessions:
        chat_sessions[chat_id] = {
            "history": [{"role": "system", "content": SYSTEM_PROMPT}],
            "last_keyword": None,
            "last_radius": DEFAULT_RADIUS,
            "seen_places": set(),
            "next_page_token": None   # track pagination
        }
    # backfill old sessions
    for key, default in [("seen_places", set()), ("next_page_token", None)]:
        if key not in chat_sessions[chat_id]:
            chat_sessions[chat_id][key] = default
    return chat_sessions[chat_id]


def get_trimmed_history(chat_id: int):
    session = get_session(chat_id)
    history = session["history"]

    if len(history) <= 11:
        return history

    system = history[0]

    last_search_idx = None
    for i in range(len(history) - 1, 0, -1):
        content = history[i].get("content") or ""  # handle None content
        if history[i]["role"] == "assistant" and "🏪" in content:
            last_search_idx = i
            break

    recent = history[-8:]

    if last_search_idx is not None and history[last_search_idx] not in recent:
        return [system, history[last_search_idx]] + recent

    return [system] + recent


def clear_chat(chat_id: int):
    chat_sessions.pop(chat_id, None)


def classify_intent(text: str, has_previous_results: bool) -> dict:
    context = "The user has seen restaurant results already." if has_previous_results else "No results have been shown yet."

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": f"""Classify this message and extract info. {context}

Message: "{text}"

Reply ONLY with valid JSON, no explanation:
{{
  "intent": "search" | "new_search" | "followup" | "chat",
  "keyword": "the food/drink/place type or null",
  "notes": "brief reason"
}}

Intent rules:
- "search": user wants to find food/drink/place (first time or no previous results)
- "new_search": user wants to see DIFFERENT or MORE places (e.g. "show other places", "find me something else", "any other options", "show more", "different restaurants")
- "followup": user asks about the CURRENT results (cheapest, closest, best, tell me more about #1)
- "chat": greeting, thanks, unrelated question

Keyword rules:
- Only return a keyword if the user EXPLICITLY names a food/drink in THIS message
- If user says 'show more', 'find another', 'other options', 'different place' → return null (reuse previous)
- If user says 'actually I want pizza' → return 'pizza' (new food)
- Do NOT infer food from context
- For drinks (coffee, boba, tea, juice, latte) → return the drink type e.g. "coffee", "boba tea"
- For food → return the food type e.g. "ramen", "pizza", "soup"
- For places → return place type e.g. "coffee shop", "restaurant"
- If intent is followup or chat → return null


"""
        }],
        temperature=0,
        max_tokens=100
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw)
    except Exception:
        return {"intent": "chat", "keyword": None}


# ─── Agent ────────────────────────────────────────────────────────────────────
def chat_with_agent(chat_id: int, message: str, lat: float = None, lng: float = None) -> str:
    try:
        session = get_session(chat_id)
        history = session["history"]
        has_results = session["last_keyword"] is not None

        # Radius: trust message first, fall back to last used
        parsed_radius = parse_radius(message)
        if parsed_radius != DEFAULT_RADIUS:
            radius = parsed_radius
        else:
            radius = session["last_radius"]

        # Classify intent
        intent_data = classify_intent(message, has_results)
        intent = intent_data.get("intent", "chat")
        keyword = intent_data.get("keyword")

        if intent in ("search", "new_search"):
            if not lat or not lng:
                history.append({"role": "user", "content": message})
                reply = "Please share your location first so I can find nearby restaurants! 📍"
                history.append({"role": "assistant", "content": reply})
                return reply

            # Only update keyword if user explicitly named a new food
            if keyword:
                if keyword != session.get("last_keyword"):
                    # Truly new food — reset everything
                    session["seen_places"] = set()
                    session["next_page_token"] = None
                session["last_keyword"] = keyword
            elif session["last_keyword"]:
                keyword = session["last_keyword"]
            else:
                history.append({"role": "user", "content": message})
                reply = "What are you craving? 😋 Tell me the food or drink you want!"
                history.append({"role": "assistant", "content": reply})
                return reply

            # Use next_page_token for new_search to get different results
            page_token = session["next_page_token"] if intent == "new_search" else None

            restaurants, next_token = find_restaurants(lat, lng, keyword, radius=radius, page_token=page_token)

            # Save token for next "show more" request
            session["next_page_token"] = next_token

            # Filter out already seen places
            fresh = [r for r in restaurants if r["name"] not in session["seen_places"]]

            # If nothing fresh and no more pages, tell user
            if not fresh and not next_token:
                reply = f"I've shown you all available {keyword} spots nearby! Try a different food or bigger radius 😅"
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": reply})
                return reply

            # If nothing fresh but there's another page, fetch it
            if not fresh and next_token:
                restaurants, next_token = find_restaurants(lat, lng, keyword, radius=radius, page_token=next_token)
                session["next_page_token"] = next_token
                fresh = [r for r in restaurants if r["name"] not in session["seen_places"]]

            for r in fresh:
                session["seen_places"].add(r["name"])

            session["last_keyword"] = keyword
            session["last_radius"] = radius

            if not fresh:
                reply = f"No more new {keyword} spots to show! Try a different food 😅"
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": reply})
                return reply

            label = "More" if intent == "new_search" else keyword.title()
            lines = [f"🍽️ {label} spots near you:\n"]
            for i, r in enumerate(fresh, 1):
                lines.append(
                    f"{i}. 🏪 {r['name']}\n"
                    f"   📍 {r['address']}\n"
                    f"   ⭐ {r['rating']}  💰 {r['price_level']}  📏 {r['distance']}\n"
                    f"   🔗 {r['maps_link']}\n"
                )

            reply = "\n".join(lines)
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": reply})
            return reply
    

        # ── Follow-up or chat: let LLM answer from history ──
        if lat and lng:
            history.append({"role": "user", "content": f"{message}\n[User location: {lat}, {lng}]"})
        else:
            history.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model=MODEL,
            messages=get_trimmed_history(chat_id),
            temperature=0.3,
            max_tokens=512
        )

        reply = response.choices[0].message.content
        history.append({"role": "assistant", "content": reply})
        return reply

    except Exception as e:
        print(f"ERROR: {e}")
        return "⚠️ Sorry, having trouble right now. Please try again!"