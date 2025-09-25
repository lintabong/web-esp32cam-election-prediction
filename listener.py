
import os
import cv2
import shutil
import pyrebase
from datetime import datetime
from dotenv import load_dotenv
from google.genai import types
from google import genai
from google.cloud import firestore

load_dotenv()

# --- Firebase Config ---
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('PATH_TO_FIRESTORE')

firebase_config = {
    'apiKey': os.getenv('FIREBASE_API_KEY'),
    'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN'),
    'databaseURL': os.getenv('FIREBASE_DATABASE_URL'),
    'projectId': os.getenv('FIREBASE_PROJECT_ID'),
    'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET'),
    'messagingSenderId': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
    'appId': os.getenv('FIREBASE_APP_ID')
}

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
folder = os.getenv('FIREBASE_STORAGE_FOLDER')
base_url = os.getenv('FIREBASE_STORAGE_BASE_URL')

# --- Initialize ---
firebase = pyrebase.initialize_app(firebase_config)
firebase_db = firebase.database()
firestore_db = firestore.Client()
storage = firebase.storage()

# --- 

def analyze_ballot(local_path):
    img = cv2.imread(local_path)
    if img is None:
        print("❌ Could not read image:", local_path)
        return

    CANDIDATE_ROIS = [
        {"name": "C01", "coords": (90, 70, 80, 150)},
        {"name": "C02", "coords": (190, 70, 80, 150)},
    ]

    results = []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    for cand in CANDIDATE_ROIS:
        x, y, w, h = cand["coords"]
        roi = gray[y:y+h, x:x+w]

        # Threshold (Otsu)
        _, roi_thresh = cv2.threshold(roi, 0, 255,
                                      cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Fill ratio
        ratio = cv2.countNonZero(roi_thresh) / float(w * h)
        results.append([cand["name"], ratio, (x, y, w, h)])

    os.environ['GEMINI_API_KEY'] = GEMINI_API_KEY

    client = genai.Client()

    with open(local_path, 'rb') as f:
        image_bytes = f.read()

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            types.Part.from_bytes(
            data=image_bytes,
            mime_type='image/jpeg',),
            'Who is choosen? 01 or 02? answer with 1/2'
        ]
    )

    if int(response.text) == 1:
        results[0][1] = 0.6
    else:
        results[1][1] = 0.6

    if results[0][1] > results[1][1]:
        winner = "1"
        winner_box = results[0][2]
        loser_box = results[1][2]
        
        results = [
            {"candidate_id": "v5nuu1ilJ8cKFt711QIF", "value": 1},
            {"candidate_id": "y0FozxfzZJSofyoHAx8p", "value": 0}
        ]
    else:
        winner = "2"
        winner_box = results[1][2]
        loser_box = results[0][2]
        
        results = [
            {"candidate_id": "v5nuu1ilJ8cKFt711QIF", "value": 0},
            {"candidate_id": "y0FozxfzZJSofyoHAx8p", "value": 1}
        ]

    print("Results:", winner)

    doc_ref = firestore_db.collection("ballots").document()

    doc_ref.set({
        "created_at": datetime.utcnow(),   # timestamp
        "image_path": str(local_path).replace('downloads\\', ''),            # string
        "is_valid": True,                  # boolean
        "processed": True,                 # boolean
        "result": results                  # array of maps
    })

    print(f"✅ {local_path} successfully uploaded")

# --- Callback when data changes ---
first_event = True
def stream_handler(message):
    global first_event
    if first_event:
        first_event = False
        return

    data = message["data"]
    if isinstance(data, dict):
        first_key = next(iter(data))
        filename = data[first_key] 
        print(filename)

        remote_path = f"{folder}/{filename}"
        download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_dir, exist_ok=True)

        storage.child(remote_path).download(os.path.join(download_dir, filename), filename)

        shutil.copy(f'{filename}', os.path.join("downloads", filename))

        analyze_ballot(os.path.join("downloads", filename))

        os.remove(filename)

    else:
        print(data)


# --- Start listening ---
print(f'Listener starting')
my_stream = firebase_db.child('listener_esp32cam').stream(stream_handler)

# keep it alive (Ctrl+C to stop)
try:
    while True:
        pass
except KeyboardInterrupt:
    my_stream.close()
