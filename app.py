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
import soundfile as sf
import json
from librosa.sequence import dtw
from typing import List
import subprocess

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
    test_mfcc = None
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
            temp.write(await audio.read())
            temp_path = temp.name
        
        print("SAVED TEMP FILE: ", temp_path)
        print("Audio size: ", os.path.getsize(temp_path) )
        
        test_mfcc = safe_extract(temp_path)
        
        if test_mfcc is None:
            return {"error": "MFCC not generated"}
                
        test_mfcc = np.array(test_mfcc)
        if test_mfcc.ndim == 1:
            test_mfcc = test_mfcc.reshape(1, -1)
        test_mfcc = test_mfcc.T
        
        wav_path = temp_path + "_converted.wav"
        convert_to_wav(temp_path, wav_path)
        
        print("MFCC extracted successfully")
        
        cur = conn.cursor()
        cur.execute(
            "SELECT mfcc_matrix FROM voice_features WHERE username = %s",
            (username,)
        )
        
        rows = cur.fetchall()
        
        if not rows:
            return {"error": "User not found"}
        
        scores = []

        print("Test MFCC shape: ", np.array(test_mfcc).shape)
        
        
        for row in rows:
            
            stored_mfcc = row[0]
            
            print("Raw stored type:", type(stored_mfcc))
            print("Raw stored value preview:", str(stored_mfcc)[:100])
            
            if isinstance(stored_mfcc, str):
                stored_mfcc = json.loads(stored_mfcc)
            
            stored_mfcc = np.array(stored_mfcc)
            print("Stored mfcc: ", type(stored_mfcc))
            
            if stored_mfcc.ndim == 0:
                print("Invalid stored MFCC (scalar)")
                continue
            
            if stored_mfcc.ndim == 1:
                stored_mfcc = stored_mfcc.reshape(1, -1)
                
            stored_mfcc = stored_mfcc.T
            print("Stored mfcc: ", type(stored_mfcc))
            
            print("Stored MFCC shape: ", np.array(stored_mfcc).shape)
            
            if test_mfcc.shape[1] != stored_mfcc.shape[1]:
                print("Feature mismatch!", test_mfcc.shape, stored_mfcc.shape)
            
            score = dtw_cosine_mfcc(test_mfcc, stored_mfcc)
            
            if isinstance(score, list):
                score = np.mean(score)
            
            print("Score:", score)
            print("Type:", type(score))
            scores.append(score)
            print("Scores: ", type(scores))
        
        final_score = max((scores))
        print("FINAL SCORE: ", final_score)
        
        os.remove(temp_path)
        cur.close()
        
        threshold = 0.98
        print("THRESHOLD TYPE:", type(threshold))
        
        return {
            "result": "MATCH" if final_score >= threshold else "NO_MATCH",
            "score": final_score
        }
        
    except Exception as e:
        return { "status": "error", "message": str(e)}
    
@app.post("/check-availability")
async def check_availability(
    username: str = Form(...),
    email: str = Form(...)
):
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT username, email FROM voice_features WHERE username = %s OR email = %s LIMIT 1",
            (username, email)
        )
        row = cur.fetchone()
        cur.close()

        if not row:
            return {"available": True}

        username_exists = row[0] == username
        email_exists = row[1] == email

        return {
            "available": False,
            "username_exists": username_exists,
            "email_exists": email_exists,
            "message": (
                "Username already exists." if username_exists else ""
            ) + (
                " Email already exists." if email_exists else ""
            )
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/upload")
async def upload_audio(
    username: str = Form(...),
    email: str = Form(...),
    audios: List[UploadFile] = File(...)
):
    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT 1 FROM voice_features WHERE username = %s OR email = %s LIMIT 1",
            (username, email)
        )
        existing = cur.fetchone()
        if existing:
            cur.close()
            return {
                "error": "Username or email already exists. Please choose a different username/email."
            }

        inserted = 0
        print("Total files received: ", len(audios))

        for audio in audios:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
                temp.write(await audio.read())
                temp_path = temp.name

            mfcc_matrix = extract_mfcc_full(temp_path)

            cur.execute(
                "INSERT INTO voice_features (username, email, mfcc_matrix) VALUES (%s, %s, %s)",
                (username, email, json.dumps(mfcc_matrix))
            )

            inserted += 1
            os.remove(temp_path)

        conn.commit()
        cur.close()

        return {
            "message": "MFCC matrix and user details stored successfully",
            "rows_inserted": inserted
        }

    except Exception as e:
        return {"error": str(e)}
            
def extract_mfcc_full(file_path):
    print("Loading audio: ", file_path)
    
    y, sr = librosa.load(file_path, sr=None)
    
    print("Audio length: ", len(y))
    
    if len(y) == 0:
        raise ValueError("Empty audio signal")
    
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    
    print("MFCC shape: ", mfcc.shape)
    return mfcc.tolist()

def dtw_cosine_mfcc(mfcc1, mfcc2):
    mfcc1 = np.array(mfcc1)
    mfcc2 = np.array(mfcc2)

    if mfcc1.ndim == 1:
        mfcc1 = mfcc1.reshape(1, -1)
    if mfcc2.ndim == 1:
        mfcc2 = mfcc2.reshape(1, -1)

    if mfcc1.shape[0] != 13:
        mfcc1 = mfcc1.T
    if mfcc2.shape[0] != 13:
        mfcc2 = mfcc2.T

    D, wp = dtw(mfcc1, mfcc2)

    wp = wp[::-1]

    mfcc1_T = mfcc1.T
    mfcc2_T = mfcc2.T

    aligned_1 = mfcc1_T[wp[:, 0]]
    aligned_2 = mfcc2_T[wp[:, 1]]

    # Cosine similarity
    similarities = cosine_similarity(aligned_1, aligned_2)

    diag_sim = np.diag(similarities)

    if isinstance(diag_sim, list):
        diag_sim = np.array(diag_sim)

    if diag_sim.ndim == 0:
        return float(diag_sim)

    return float(np.mean(diag_sim))

def convert_to_wav(input_path, output_path):
    subprocess.run([
        "ffmpeg", "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "16000",
        output_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
def safe_extract(file_path):
    try:
        return extract_mfcc_full(file_path)
    except Exception as e:
        print("MFCC ERROR:", repr(e))
        return None