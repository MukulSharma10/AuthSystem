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
from sklearn.metrics.pairwise import cosine_similarity
import soundfile as sf
import json
from librosa.sequence import dtw

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
    audio: UploadFile = File(...)
):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
            temp.write(await audio.read())
            temp_path = temp.name
        
        test_mfcc = extract_mfcc_full(temp_path)
        
        cur = conn.cursor()
        cur.execute(
            "SELECT mfcc_matrix FROM voice_features WHERE username = %s",
            (username,)
        )
        
        rows = cur.fetchall()
        
        if not rows:
            return {"error": "User not found"}
        
        scores = []

        for row in rows:
            stored_mfcc = row[0]
            
            score = dtw_cosine_mfcc(test_mfcc, stored_mfcc)
            scores.append(score)
            
        final_score = float(np.mean(scores))
        
        os.remove(temp_path)
        cur.close()
        
        os.getenv('THRESHOLD') = 0.75
        
        return {
            "result": "MATCH" if final_score >= os.getenv('THRESHOLD') else "NO_MATCH",
            "score": final_score
        }
        
    except Exception as e:
        return { "status": "error", "message": str(e)}
    
@app.post("/upload")
async def upload_audio(
    username: str = Form(...),
    audio: UploadFile = File(...)
):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
            temp.write(await audio.read())
            temp_path = temp.name
            
        mfcc_matrix = extract_mfcc_full(temp_path)
        
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO voice_features (username, mfcc_matrix) VALUES (%s, %s)", (username, json.dumps(mfcc_matrix))
        )
        conn.commit()
        cur.close()
        
        os.remove(temp_path)
        
        return {
            "message": "MFCC matrix stored successfully"
        }
    
    except Exception as e:
        return {"error": str(e)}
        
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
    
def extract_mfcc(file_path):
    y, sr = librosa.load(file_path, sr=None)

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)

    # Convert to fixed-size vector
    mfcc_mean = np.mean(mfcc, axis=1)
    mfcc_std = np.std(mfcc, axis=1)

    features = np.concatenate([mfcc_mean, mfcc_std]) 
    return features.tolist()

def build_template(cursor, username):
    cursor.execute(
        "SELECT mfcc_features FROM voice_features WHERE username = %s",
        (username,)
    )
    
    rows = cursor.fetchall()
    
    if not rows:
        return None
    
    vectors = np.array([row[0] for row in rows])
    
    template = np.mean(vectors, axis=0)
    
    return template

def extract_mfcc_full(file_path):
    y, sr = librosa.load(file_path, sr=None)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    return mfcc.tolist()

def dtw_cosine_mfcc(mfcc1, mfcc2):
    mfcc1 = np.array(mfcc1)
    mfcc2 = np.array(mfcc2)
    
    mfcc1_T = mfcc1.T
    mfcc2_T = mfcc2.T
    
    D, wp = dtw(mfcc1_T, mfcc2_T)
    
    aligned_1 = []
    aligned_2 = []
    
    for i,j in wp:
        aligned_1.append(mfcc1[:, i])
        aligned_2.append(mfcc2[:, j])
    
    aligned_1 = np.array(aligned_1)
    aligned_2 = np.array(aligned_2)
    
    similarities = [
        cosine_similarity([v1], [v2])[0][0] for v1, v2 in zip(aligned_1, aligned_2)
    ]
    
    return float(np.mean(similarities))