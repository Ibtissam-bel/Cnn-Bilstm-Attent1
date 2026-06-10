from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import numpy as np
import librosa
import tempfile
import os
import subprocess
import pickle
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
from tensorflow.keras.models import load_model


app = FastAPI(title="SER API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/app")
def serve_app():
    return FileResponse("ser_web_app.html")

BASE   = os.path.dirname(os.path.abspath(__file__))
model  = load_model(os.path.join(BASE, "best_ser_lstm.keras"))

with open(os.path.join(BASE, "label_encoder.pkl"), "rb") as f:
    le = pickle.load(f)

CLASSES = le.classes_.tolist()

EMOTION_INFO = {
    "angry":   {"emoji": "😡", "color": "#FF4444", "french": "Colère"},
    "disgust": {"emoji": "🤢", "color": "#8BC34A", "french": "Dégoût"},
    "fear":    {"emoji": "😨", "color": "#9C27B0", "french": "Peur"},
    "happy":   {"emoji": "😊", "color": "#FFD700", "french": "Joie"},
    "neutral": {"emoji": "😐", "color": "#90A4AE", "french": "Neutre"},
    "sad":     {"emoji": "😢", "color": "#2196F3", "french": "Tristesse"},
}

SAMPLE_RATE = 22050
N_MFCC      = 40
MAX_LEN     = 130

def extract_features(file_path):
    converted = file_path + "_clean.wav"

    subprocess.run([
        "ffmpeg",
        "-y",
        "-i",
        file_path,
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        "1",
        "-sample_fmt",
        "s16",
        "-vn",
        converted
    ], capture_output=True)

    if not os.path.exists(converted) or os.path.getsize(converted) < 100:
        raise Exception("Échec conversion audio")

    try:
        audio, sr = librosa.load(
            converted,
            sr=SAMPLE_RATE,
            duration=3.0,
            offset=0.5
        )

        if len(audio) < sr * 0.5:
            raise Exception("Audio trop court")

        mfcc = librosa.feature.mfcc(
            y=audio,
            sr=sr,
            n_mfcc=N_MFCC
        )

        delta1 = librosa.feature.delta(mfcc, order=1)
        delta2 = librosa.feature.delta(mfcc, order=2)
        zcr = librosa.feature.zero_crossing_rate(audio)
        rms = librosa.feature.rms(y=audio)
        spectral_centroid = librosa.feature.spectral_centroid(y=audio, sr=sr)

        features = np.vstack([
            mfcc,
            delta1,
            delta2,
            zcr,
            rms,
            spectral_centroid
        ])

        if features.shape[1] < MAX_LEN:
            pad_width = MAX_LEN - features.shape[1]
            features = np.pad(features, ((0, 0), (0, pad_width)), mode="constant")
        else:
            features = features[:, :MAX_LEN]

        features = features.T
        print(f"✅ Features shape: {features.shape}")
        return np.expand_dims(features, axis=0)

    finally:
        if os.path.exists(converted):
            os.unlink(converted)



@app.post("/predict")
async def predict_emotion(file: UploadFile = File(...)):
   
    ext = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        features = extract_features(tmp_path)
        if features is None:
            raise HTTPException(status_code=400, detail="لا يمكن استخراج الميزات من هذا الملف")

        probs = model.predict(features, verbose=0)[0]
        best_idx = int(np.argmax(probs))
        best_emotion = CLASSES[best_idx]
        best_conf = float(probs[best_idx])

        all_results = [
            {"emotion": CLASSES[i], "confidence": float(probs[i])}
            for i in range(len(CLASSES))
        ]

        return {
            "emotion": best_emotion,
            "confidence": best_conf,
            "all_results": all_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
