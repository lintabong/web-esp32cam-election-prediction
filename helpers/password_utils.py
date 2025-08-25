import hashlib
import os

def hash_password(password: str, salt: bytes = None) -> tuple:
    if salt is None:
        salt = os.urandom(16)

    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',                # algoritma
        password.encode('utf-8'),# password dalam bytes
        salt,                    # salt
        100000                   # jumlah iterasi (semakin tinggi semakin aman)
    )
    return salt, pwd_hash

def verify_password(stored_hash: bytes, stored_salt: bytes, password_attempt: str) -> bool:
    _, pwd_hash_attempt = hash_password(password_attempt, stored_salt)
    return pwd_hash_attempt == stored_hash
