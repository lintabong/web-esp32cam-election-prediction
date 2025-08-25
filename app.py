import os
import cv2
import numpy as np
import pyrebase
import threading
import time
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from dotenv import load_dotenv
import requests
from werkzeug.security import check_password_hash, generate_password_hash
from google.cloud import firestore

load_dotenv()

CANDIDATE_MAP = {
    "v5nuu1ilJ8cKFt711QIF": "siA",
    "y0FozxfzZJSofyoHAx8p": "siB",
}

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

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

# Initialize Firebase
firebase = pyrebase.initialize_app(firebase_config)
firebase_db = firebase.database()
firestore_db = firestore.Client()
storage = firebase.storage()


class VoteCounter:
    def __init__(self):
        self.listening = False
        self.listener_thread = None
        
    def detect_votes_opencv(self, image_path):
        """Analisa gambar surat suara menggunakan OpenCV"""
        try:
            # Download image dari Firebase Storage
            response = requests.get(image_path)
            image_array = np.frombuffer(response.content, np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            
            if image is None:
                return {"error": "Cannot read image"}
            
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Apply threshold untuk deteksi coblos
            _, thresh = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)
            
            # Contoh sederhana deteksi area coblosan (asumsi ada 2 area)
            height, width = thresh.shape
            
            # Bagi image menjadi 2 bagian (kiri untuk siA, kanan untuk siB)
            left_half = thresh[:, :width//2]
            right_half = thresh[:, width//2:]
            
            # Hitung pixel hitam (coblosan) di masing-masing area
            left_black_pixels = np.sum(left_half == 0)
            right_black_pixels = np.sum(right_half == 0)
            
            # Tentukan threshold minimum untuk dianggap tercoblos
            threshold_pixels = 1000  # Sesuaikan dengan kebutuhan
            
            result = {
                "siA": 1 if left_black_pixels > threshold_pixels else 0,
                "siB": 1 if right_black_pixels > threshold_pixels else 0,
                "total_votes": 0,
                "status": "processed",
                "left_pixels": int(left_black_pixels),
                "right_pixels": int(right_black_pixels)
            }
            
            result["total_votes"] = result["siA"] + result["siB"]
            
            return result
            
        except Exception as e:
            return {"error": str(e)}
    
    def process_new_ballot(self, data):
        """Process ballot baru yang masuk"""
        try:
            ballot_id = data.get('ballot_id')
            image_path = data.get('image_path')
            
            if not ballot_id or not image_path:
                print("Missing ballot_id or image_path")
                return
                
            print(f"Processing ballot: {ballot_id}")
            
            # Analisa gambar
            result = self.detect_votes_opencv(image_path)
            
            # Update hasil ke database
            update_data = {
                'processed': True,
                'processed_at': time.time(),
                'result': result
            }
            
            firebase_db.child("ballots").child(ballot_id).update(update_data)
            print(f"Ballot {ballot_id} processed successfully")
            
        except Exception as e:
            print(f"Error processing ballot: {str(e)}")
    
    def stream_handler(self, message):
        """Handler untuk Firebase listener"""
        if message["event"] == "put":
            data = message["data"]
            if data and isinstance(data, dict):
                for ballot_id, ballot_data in data.items():
                    if isinstance(ballot_data, dict) and not ballot_data.get('processed', False):
                        self.process_new_ballot({
                            'ballot_id': ballot_id,
                            'image_path': ballot_data.get('image_path')
                        })
    
    def start_listening(self):
        """Mulai mendengarkan perubahan di Firebase"""
        if not self.listening:
            self.listening = True
            print("Starting Firebase listener...")
            try:
                firebase_db.child("ballots").stream(self.stream_handler)
            except Exception as e:
                print(f"Error in Firebase listener: {str(e)}")
                self.listening = False

vote_counter = VoteCounter()

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        users_ref = firestore_db.collection('users')
        query = users_ref.where('username', '==', username).limit(1).get()

        if not query:
            flash('Username atau password salah!', 'error')
            return render_template('login.html')

        user_doc = query[0]
        user_data = user_doc.to_dict()
        user_id = user_doc.id
        print(user_id)

        if password == user_data.get("password"):
            session['user'] = username
            session['user_type'] = user_data.get("role", "user")
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah!', 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    return render_template('dashboard.html', current_page='dashboard')

@app.route('/statistik')
def statistik():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    try:
        ballots_data = firebase_db.child("ballots").get()
        ballots = ballots_data.val() if ballots_data.val() else {}
        
        stats = {
            'total_ballots': len(ballots),
            'processed_ballots': 0,
            'siA_votes': 0,
            'siB_votes': 0,
            'total_valid_votes': 0
        }
        
        for ballot_id, ballot in ballots.items():
            if ballot.get('processed', False):
                stats['processed_ballots'] += 1
                result = ballot.get('result', {})
                if not result.get('error'):
                    stats['siA_votes'] += result.get('siA', 0)
                    stats['siB_votes'] += result.get('siB', 0)
        
        stats['total_valid_votes'] = stats['siA_votes'] + stats['siB_votes']
        
        return render_template('statistik.html', stats=stats, current_page='statistik')
        
    except Exception as e:
        flash(f'Error mengambil statistik: {str(e)}', 'error')
        return render_template('statistik.html', stats={}, current_page='statistik')

@app.route('/surat-suara')
def surat_suara():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        ballots_ref = firestore_db.collection("ballots").stream()
        
        ballot_list = []
        for doc in ballots_ref:
            ballot_data = doc.to_dict()
            ballot_data['id'] = doc.id

            ballot_data.setdefault('image_path', None)
            ballot_data.setdefault('processed', False)
            ballot_data.setdefault('created_at', None)

            result_dict = {}
            for r in ballot_data.get("result", []):
                candidate_name = CANDIDATE_MAP.get(r["candidate_id"], r["candidate_id"])
                result_dict[candidate_name] = r["value"]
            ballot_data["result_dict"] = result_dict
            ballot_list.append(ballot_data)

        ballot_list.sort(
            key=lambda x: x.get('created_at') or 0,
            reverse=True
        )
        
        return render_template(
            'surat_suara.html',
            ballots=ballot_list,
            current_page='surat_suara'
        )
        
    except Exception as e:
        flash(f'Error mengambil data surat suara: {str(e)}', 'error')
        return render_template(
            'surat_suara.html',
            ballots=[],
            current_page='surat_suara'
        )

@app.route('/surat-suara/<ballot_id>')
def detail_surat_suara(ballot_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    try:
        doc_ref = firestore_db.collection("ballots").document(ballot_id)
        doc = doc_ref.get()

        if not doc.exists:
            flash('Surat suara tidak ditemukan!', 'error')
            return redirect(url_for('surat_suara'))

        ballot = doc.to_dict()
        ballot['id'] = doc.id

        ballot.setdefault('image_path', None)
        ballot.setdefault('processed', False)
        ballot.setdefault('created_at', None)
        ballot.setdefault('result', [])

        return render_template(
            'detail_surat_suara.html',
            ballot=ballot,
            current_page='surat_suara'
        )
        
    except Exception as e:
        flash(f'Error mengambil detail surat suara: {str(e)}', 'error')
        return redirect(url_for('surat_suara'))


@app.route('/api/stats')
def api_stats():
    """API endpoint untuk mendapatkan statistik real-time"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        ballots_data = firebase_db.child("ballots").get()
        ballots = ballots_data.val() if ballots_data.val() else {}
        
        stats = {
            'total_ballots': len(ballots),
            'processed_ballots': 0,
            'siA_votes': 0,
            'siB_votes': 0,
            'total_valid_votes': 0
        }
        
        for ballot_id, ballot in ballots.items():
            if ballot.get('processed', False):
                stats['processed_ballots'] += 1
                result = ballot.get('result', {})
                if not result.get('error'):
                    stats['siA_votes'] += result.get('siA', 0)
                    stats['siB_votes'] += result.get('siB', 0)
        
        stats['total_valid_votes'] = stats['siA_votes'] + stats['siB_votes']
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def start_firebase_listener():
    """Start Firebase listener in background thread"""
    vote_counter.start_listening()

if __name__ == '__main__':
    listener_thread = threading.Thread(target=start_firebase_listener, daemon=True)
    listener_thread.start()
    
    app.run(
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        host='0.0.0.0',
        port=5000
    )
