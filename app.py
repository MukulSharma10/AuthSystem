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
import io
from sklearn.metrics.pairwise import cosine_similarity
import soundfile as sf

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

#API ENDPOINT
@app.post('/match')
async def match_voice(
    username: str = Form(...),
    file: UploadFile = File(...)
):
    threshold = 0.95
    
    try:
        audio_bytes = await file.read()
        mfcc_input = extract_mfcc_from_bytes(audio_bytes)
        
        if mfcc_input is None:
            return {
                "status": "error",
                "message": "MFCC extraction failed for input audio"
            }
        
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
        
        similarity = compare_mfcc(
            mfcc_input,
            mfcc_stored.reshape(1, -1)
        )
        
        print(similarity)
        
        if similarity is None:
            return {
                "status": "error",
                "message": "Comparison failed"
            }
        
        
        if similarity >= threshold:
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
        if mfcc is None:
            return {
                "status": "error",
                "message": "MFCC extraction failed for uploaded audio"
            }
        
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
        try:
            data, sr = sf.read(tmp_path)
        except Exception:
            # Fall back to librosa for formats like MP3 or other unsupported containers
            data, sr = librosa.load(tmp_path, sr=None, mono=True)

        if data is None or sr is None:
            return None

        if getattr(data, 'ndim', 1) > 1:
            data = np.mean(data, axis=1)

        if np.max(np.abs(data)) > 0:
            data = data / np.max(np.abs(data))

        if sr != target_sr:
            data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)

        mfcc = librosa.feature.mfcc(y=data, sr=target_sr, n_mfcc=n_mfcc)
        return mfcc.T

    except Exception as e:
        print(f"Error processing audio: {e}")
        return None

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def compare_mfcc(mfcc1, mfcc2):
    if mfcc1 is None or mfcc2 is None:
        return None

    if len(mfcc1) == 0 or len(mfcc2) == 0:
        return None
    
    min_len = min(len(mfcc1), len(mfcc2))
    mfcc1, mfcc2 = mfcc1[:min_len], mfcc2[:min_len]
    
    flat_mfcc1, flat_mfcc2 = mfcc1.flatten(), mfcc2.flatten()
    
    if flat_mfcc1.size == 0 or flat_mfcc2.size == 0:
        return None
    
    return float(
        cosine_similarity([flat_mfcc1], [flat_mfcc2])[0][0]
    )