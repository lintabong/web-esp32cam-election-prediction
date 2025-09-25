# 🗳️ Vote Counter - Surat Suara Scanner

Aplikasi berbasis **Flask** untuk membaca hasil **surat suara** menggunakan **OpenCV** dan menyimpan hasilnya ke **Firestore/Firebase**.  
Aplikasi ini mendukung login, dashboard, statistik hasil voting, serta detail per surat suara.

---

## 🚀 Fitur
- 🔐 **Login & Logout** dengan autentikasi sederhana (Firestore).
- 📊 **Dashboard** menampilkan ringkasan hasil suara.
- 📑 **Daftar Surat Suara**: melihat semua surat suara yang dipindai.
- 📝 **Detail Surat Suara**: menampilkan hasil perhitungan OCR/OpenCV dari gambar surat suara.
- 📈 **Statistik Real-time** hasil perhitungan suara.
- 🌐 **REST API Endpoint** untuk statistik (`/api/stats`).
- 🔄 **Firebase Listener** berjalan di background untuk update otomatis.

---

## 🛠️ Teknologi
- [Python 3.9+](https://www.python.org/)
- [Flask](https://flask.palletsprojects.com/)
- [OpenCV](https://opencv.org/)
- [Google Firestore](https://firebase.google.com/docs/firestore) (database)
- [Firebase Realtime Database](https://firebase.google.com/docs/database)
- [Pyrebase](https://github.com/thisbejim/Pyrebase)
- HTML + Jinja2 (template engine)

---

---

## 📡 Alur Proses
- ESP32CAM mengunggah foto ke Firebase Storage.
- Realtime Database men-trigger listener.py.
- Listener mengunduh gambar ke folder downloads/.
- Fungsi analyze_ballot() memproses gambar dengan OpenCV + Gemini API.
- Hasil perhitungan disimpan ke Firestore.
- Flask app menampilkan data di dashboard & API.
---

## How to Run
```
python app.py
```

```
python listener.py
```
