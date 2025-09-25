
import os
import pyrebase
import warnings
import threading
from urllib.parse import quote
from flask import Flask, render_template, request, redirect, url_for, session, flash
from dotenv import load_dotenv
from google.cloud import firestore

from helpers import candidate_utils

warnings.filterwarnings(
    'ignore',
    category=UserWarning,
    message='pkg_resources is deprecated as an API.*'
)

load_dotenv()

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

firebase = pyrebase.initialize_app(firebase_config)
firebase_db = firebase.database()
firestore_db = firestore.Client()
storage = firebase.storage()


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

        if password == user_data.get('password'):
            session['user'] = username
            session['user_type'] = user_data.get('role', 'user')
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
        ballots_docs = firestore_db.collection('ballots').get()
        ballots = [{**doc.to_dict(), 'id': doc.id} for doc in ballots_docs]

        stats = {
            'total_ballots': len(ballots),
            'processed_ballots': 0,
            'A_votes': 0,
            'B_votes': 0,
            'total_valid_votes': 0
        }

        CANDIDATE_MAP = candidate_utils.get_candidate_map(firestore_db)

        for ballot in ballots:
            if ballot.get('processed', False):
                stats['processed_ballots'] += 1
                result_list = ballot.get('result', [])

                for r in result_list:
                    if isinstance(r, dict) and not r.get('error'):
                        candidate_id = r.get('candidate_id')
                        value = int(r.get('value', 0))
                        candidate_name = CANDIDATE_MAP.get(candidate_id)
                        if candidate_name == 'A':
                            stats['A_votes'] += value
                        elif candidate_name == 'B':
                            stats['B_votes'] += value

        stats['total_valid_votes'] = stats['A_votes'] + stats['B_votes']
    
    except Exception as e:
        flash(f'Error mengambil statistik: {str(e)}', 'error')
        
    return render_template(
        'statistik.html', 
        stats=stats, 
        current_page='statistik'
    )

@app.route('/surat-suara')
def surat_suara():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        ballots_ref = firestore_db.collection("ballots").stream()

        CANDIDATE_MAP = candidate_utils.get_candidate_map(firestore_db)

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

        file_path = ballot.get('image_path')
        if file_path:
            bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
            folder = os.getenv('FIREBASE_STORAGE_FOLDER')
            base_url = os.getenv('FIREBASE_STORAGE_BASE_URL')
            encoded_path = quote(file_path, safe='')
            ballot['image_path'] = f"{base_url}/{bucket}/o/{folder}%2F{encoded_path}"
            ballot['image_path'] += '?alt=media'
        else:
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

def start_firebase_listener():
    def run_listener():
        def stream_handler(message):
            event_type = message.get("event")
            data = message.get("data")
            print(data)

        firebase_db.child('ballots').stream(stream_handler)
    
    listener_thread = threading.Thread(target=run_listener, daemon=True)
    listener_thread.start()
    return listener_thread

if __name__ == '__main__':
    app.run(
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        host=os.getenv('APPLICATION_HOST'),
        port=os.getenv('APPLICATION_PORT')
    )
