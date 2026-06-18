import json
import numpy as np
import tensorflow as tf
from tensorflow.keras.applications.efficientnet import preprocess_input
from PIL import Image
from io import BytesIO
from config import MODEL_PATH, CLASS_LABELS_PATH, IMG_SIZE

print("Loading food classifier...")
model = tf.keras.models.load_model(MODEL_PATH)

with open(CLASS_LABELS_PATH, "r") as f:
    class_labels = json.load(f)

print(f"Model ready! {len(class_labels)} categories.")

def classify_food(image_bytes: bytes) -> tuple[str, float]:
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img = img.resize((IMG_SIZE, IMG_SIZE))
    img_array = np.array(img, dtype=np.float32)
    
    # Use same preprocessing as training
    img_array = preprocess_input(img_array)
    img_array = np.expand_dims(img_array, axis=0)

    predictions = model.predict(img_array, verbose=0)
    
    top_5_idx = np.argsort(predictions[0])[-5:][::-1]
    for idx in top_5_idx:
        print(f"{class_labels[str(idx)]}: {predictions[0][idx]:.2%}")

    top_idx = np.argmax(predictions[0])
    confidence = float(predictions[0][top_idx])
    food_name = class_labels[str(top_idx)].replace("_", " ")
    return food_name, confidence