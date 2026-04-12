from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import librosa
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import warnings
import tempfile
import os
import psycopg2
import hashlib
import base64
from cryptography.fernet import Fernet
from dotenv import load_dotenv

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)

secret = 'my_super_secret_key'
key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
cipher = Fernet(key)

load_dotenv()

conn = psycopg2.connect(
    dbname = os.getenv('PGDATABASE'),
    user = os.getenv('PGUSER'),
    password = os.getenv('PGPASSWORD') ,
    host = os.getenv('PGHOST'),
    port = os.getenv('PGPORT')
)

# def compute_mfcc(file_path, target_sr=16000, n_mfcc=13):
#     try:
#         y, sr = librosa.load(file_path, sr=target_sr)  
#         if sr != target_sr:
#             y = librosa.resample(y, orig_sr=sr, target_sr=target_sr) 
#         mfcc = librosa.feature.mfcc(y=y, sr=target_sr, n_mfcc=n_mfcc)  
#         return mfcc.T 
#     except Exception as e:
#         print(f"Error processing file {file_path}: {e}")
        
# def compare_mfcc(mfcc1, mfcc2):
#     min_length = min(len(mfcc1), len(mfcc2))
#     mfcc1, mfcc2 = mfcc1[:min_length], mfcc2[:min_length]
#     flat_mfcc1, flat_mfcc2 = mfcc1.flatten(), mfcc2.flatten()

#     cos_sim = cosine_similarity([flat_mfcc1], [flat_mfcc2])[0][0]
#     return cos_sim


#API ENDPOINT
@app.post('/match')
async def match_voice(
    username: str = Form(...),
    file: UploadFile = File(...)
):
    threshold = 0.9
    
    try:
        audio_bytes = await file.read()
        mfcc_input = extract_mfcc_from_bytes(audio_bytes, filename=file.filename, content_type=file.content_type)
        
        curr = conn.cursor()
        curr.execute(
            "SELECT mfcc_data FROM recordings WHERE username = %s",
            (username,)
        )
        result = curr.fetchone()
        
        if not result:
            return {
                "status": "fail",
                "message": "User not found"
            }
        
        encrypted_mfcc = bytes(result[0])
        decrypted_bytes = cipher.decrypt(encrypted_mfcc)
        
        mfcc_stored = np.frombuffer(decrypted_bytes, dtype=np.float32)
        
        similarity = np.dot(mfcc_input, mfcc_stored) / (
            np.linalg.norm(mfcc_input) * np.linalg.norm(mfcc_stored)
        )
        
        if similarity > threshold:
            return { 
                "status": "success",
                "score": float(similarity)
            }
        else:
            return {
                "status": "fail",
                "score": float(similarity)
            }
        
    except Exception as e:
        return { "status": "error", "message": str(e)}
    
@app.post("/upload")
async def upload_audio(
    username: str = Form(...),
    email: str = Form(...),
    audio: UploadFile = File(...)
):
    try:
        if not username or not email:
            return {"status": "fail", "message": "Missing username or email"}
        
        audio_bytes = await audio.read()
        
        mfcc = extract_mfcc_from_bytes(audio_bytes, filename=audio.filename, content_type=audio.content_type)
        
        mfcc_bytes = mfcc.astype(np.float32).tobytes()
        
        encrypted_mfcc = cipher.encrypt(mfcc_bytes)
        
        #DATABASE INSERTION OPERATION
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO recordings (username, email, mfcc_data) VALUES(%s, %s, %s)", (username, email, encrypted_mfcc)
        )
        conn.commit()
        
        return {
            "status": "success",
            "message": "User registered & Passphrase stored!"
        }
        
    except Exception as err:
        print(err)
        return {
            "status": "error",
            "message": str(err)
        }
        

def extract_mfcc_from_bytes(audio_bytes, filename=None, content_type=None, target_sr=16000, n_mfcc=13):
    suffix = None
    if filename:
        suffix = os.path.splitext(filename)[1]
    if not suffix:
        if content_type == 'audio/wav':
            suffix = '.wav'
        elif content_type in ('audio/webm', 'audio/ogg'):
            suffix = '.ogg'
        elif content_type == 'audio/mpeg':
            suffix = '.mp3'
        else:
            suffix = '.wav'

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(audio_bytes)
        tmp_path = tmp_file.name

    try:
        y, sr = librosa.load(tmp_path, sr=target_sr)
        mfcc = librosa.feature.mfcc(y=y, sr=target_sr, n_mfcc=n_mfcc)
        mfcc_mean = np.mean(mfcc.T, axis=0)
        return mfcc_mean
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
