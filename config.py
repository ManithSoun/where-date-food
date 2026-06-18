import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MODEL_PATH = "best_model_b3.keras"
CLASS_LABELS_PATH = "class_labels.json"
IMG_SIZE = 300
SEARCH_RADIUS = 2000
MAX_RESULTS = 5