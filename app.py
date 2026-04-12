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

def compute_mfcc(file_path, target_sr=16000, n_mfcc=13):
    try:
        y, sr = librosa.load(file_path, sr=target_sr)  
        if sr != target_sr:
            y = librosa.resample(y, orig_sr=sr, target_sr=target_sr) 
        mfcc = librosa.feature.mfcc(y=y, sr=target_sr, n_mfcc=n_mfcc)  
        return mfcc.T 
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        
def compare_mfcc(mfcc1, mfcc2):
    min_length = min(len(mfcc1), len(mfcc2))
    mfcc1, mfcc2 = mfcc1[:min_length], mfcc2[:min_length]
    flat_mfcc1, flat_mfcc2 = mfcc1.flatten(), mfcc2.flatten()

    cos_sim = cosine_similarity([flat_mfcc1], [flat_mfcc2])[0][0]
    return cos_sim


#API ENDPOINT
@app.post('/match')
async def match_voice(
    username: str = Form(...),
    file: UploadFile = File(...)
):
    threshold = 0.95
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp1:
            temp1.write(await file.read())
            login_path = temp1.name
            
        cur = conn.cursor()
        cur.execute(
            "SELECT audio_data FROM recordings WHERE username = %s",
            (username,)
        )
        result = cur.fetchone()
        
        if not result:
            return {"status": "fail", "message": "User not found"}
        
        encrypted_audio = bytes(result[0])
        
        
        decrypted_audio = cipher.decrypt(encrypted_audio)
        
        with tempfile.NamedTemporaryFile(delete= False, suffix= ".wav") as temp2:
            temp2.write(decrypted_audio)
            registered_path = temp2.name
            
        mfcc1 = compute_mfcc(registered_path)
        mfcc2 = compute_mfcc(login_path)
        
        similarity = compute_mfcc(mfcc1, mfcc2)
        
        os.remove(login_path)
        os.remove(registered_path)
        
        if similarity >= threshold:
            return {
                "status": "success",
                "result": "MATCH",
                "score": float(similarity)
            }
        else:
            return {
                "status": "fail",
                "result": "NOT_MATCH",
                "score": float(similarity)
            }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
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
        
        encrypted_audio = cipher.encrypt(audio_bytes)
        
        cur = conn.cursor()
        
        cur.execute(
            "INSERT INTO recordings (username, email, audio_data) VALUES(%s, %s, %s)", (username, email, encrypted_audio)
        )
        
        conn.commit()
        
        return {
            "status": "success",
            "message": "User registered & Passphrase Encrypted!"
        }
        
    except Exception as err:
        print(err)
        return {
            "status": "error",
            "message": "Error storing data"
        }