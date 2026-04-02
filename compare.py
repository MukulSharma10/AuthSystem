import librosa
from sklearn.metrics.pairwise import cosine_similarity
import sys
import warnings

# Suppress deprecation and library warnings from librosa
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)

registered_file = sys.argv[1]
login_file = sys.argv[2]

def compute_mfcc(file_path, target_sr=16000, n_mfcc=13):
    try:
        y, sr = librosa.load(file_path, sr=target_sr)  
        if sr != target_sr:
            y = librosa.resample(y, orig_sr=sr, target_sr=target_sr) 
        mfcc = librosa.feature.mfcc(y=y, sr=target_sr, n_mfcc=n_mfcc)  
        return mfcc.T 
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        exit(1)

def compare_mfcc(mfcc1, mfcc2):
    min_length = min(len(mfcc1), len(mfcc2))
    mfcc1, mfcc2 = mfcc1[:min_length], mfcc2[:min_length]
    flat_mfcc1, flat_mfcc2 = mfcc1.flatten(), mfcc2.flatten()

    cos_sim = cosine_similarity([flat_mfcc1], [flat_mfcc2])[0][0]
    return cos_sim

def main():
    file1 = registered_file
    file2 = login_file
    threshold = 0.95

    # print(f"Processing files:\n  File 1: {file1}\n  File 2: {file2}")

    mfcc1 = compute_mfcc(file1)
    mfcc2 = compute_mfcc(file2)

    similarity = compare_mfcc(mfcc1, mfcc2)

    #print(f"Similarity Score: {similarity:.4f}")
    if similarity >= threshold:
        print("MATCH")
    else:
        print("NOT_MATCH")

if __name__ == "__main__":
    main()