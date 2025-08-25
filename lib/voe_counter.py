import os
import cv2
import numpy as np
import pyrebase
import warnings
import threading
import time
from urllib.parse import quote
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from dotenv import load_dotenv
import requests
from google.cloud import firestore

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
            
            # firebase_db.child("ballots").child(ballot_id).update(update_data)
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
            # try:
            #     firebase_db.child("ballots").stream(self.stream_handler)
            # except Exception as e:
            #     print(f"Error in Firebase listener: {str(e)}")
            #     self.listening = False
