# VoiceAttend AI

> **AI-powered voice attendance marking system**
> FastAPI (Python) backend · PostgreSQL database · Flutter (Dart) mobile frontend

---

## Project Structure

```
voiceattend/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app entry point
│   │   ├── database.py                # PostgreSQL connection & queries
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── voice_model.py         # librosa feature extraction + AI skeleton
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   └── attendance.py          # /attendance/* endpoints
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── audio_utils.py         # Validation, format detection
│   │       └── response_utils.py      # Standardised JSON envelopes
│   ├── requirements.txt
│   └── database_setup.sql             # One-time PostgreSQL schema setup
│
└── mobile/
    ├── pubspec.yaml
    ├── android_manifest_reference.xml  # Merge into AndroidManifest.xml
    ├── ios_info_plist_additions.xml    # Merge into Info.plist
    └── lib/
        ├── main.dart                   # App entry point & theme
        ├── screens/
        │   ├── home_screen.dart        # Mic button, recognition result
        │   └── logs_screen.dart        # All attendance logs
        ├── services/
        │   ├── attendance_service.dart # HTTP calls to FastAPI
        │   └── audio_recorder_service.dart  # Mic recording
        └── widgets/
            ├── pulse_button.dart       # Animated mic button
            ├── status_card.dart        # Flow-state banner
            └── result_card.dart        # Recognition result display
```

---

## Prerequisites

| Tool | Minimum Version | Windows Download |
|------|----------------|-----------------|
| Python | 3.10+ | https://www.python.org/downloads/ |
| PostgreSQL | 14+ | https://www.postgresql.org/download/windows/ |
| Flutter SDK | 3.19+ | https://docs.flutter.dev/get-started/install/windows |
| Android Studio / Xcode | Latest | For emulator/device |
| Git | Any | https://git-scm.com |

---

## 1 · Database Setup (PostgreSQL)

Open **pgAdmin** or **psql** as the `postgres` superuser and run:

```powershell
# Windows PowerShell
psql -U postgres -f backend\database_setup.sql
```

This creates:
- Role `voiceuser` with password `voicepass`
- Database `voiceattend`
- Table `attendance_logs (id, user_name, timestamp)`

**Verify:**
```sql
-- In psql
\connect voiceattend
SELECT * FROM attendance_logs;
```

---

## 2 · Backend Setup (FastAPI)

### 2a – Create & activate virtual environment

```powershell
# Windows PowerShell (run from the project root)
cd backend

python -m venv venv
venv\Scripts\activate

# Confirm the prompt changes to (venv) ...
```

### 2b – Install dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

> **GPU Note:** The `requirements.txt` installs PyTorch CPU-only.
> For CUDA support, visit https://pytorch.org/get-started/locally/ and
> install the matching wheel **before** installing the rest.

### 2c – Configure database connection

Edit `app/database.py` → `DB_CONFIG` if your Postgres runs on a
non-default host/port:

```python
DB_CONFIG = {
    "dbname":   "voiceattend",
    "user":     "voiceuser",
    "password": "voicepass",
    "host":     "localhost",   # ← change if Postgres is on another machine
    "port":     5432,
}
```

### 2d – Run the backend

```powershell
# From the backend/ directory, with venv active
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Verify:**
- Open http://localhost:8000 → `{"status":"ok","message":"VoiceAttend AI backend is running."}`
- Open http://localhost:8000/docs → Interactive Swagger UI

---

## 3 · Mobile Frontend Setup (Flutter)

### 3a – Set your backend URL

Open `mobile/lib/services/attendance_service.dart` and update `baseUrl`:

```dart
// Android emulator → host machine's localhost:
static const String baseUrl = 'http://10.0.2.2:8000';

// Physical Android device on the same Wi-Fi network:
static const String baseUrl = 'http://192.168.1.XXX:8000';  // ← your PC's LAN IP

// iOS Simulator:
static const String baseUrl = 'http://localhost:8000';
```

Find your PC's LAN IP on Windows: `ipconfig` → look for `IPv4 Address`.

### 3b – Android permissions

Replace (or merge) `mobile/android/app/src/main/AndroidManifest.xml`
with the contents of `mobile/android_manifest_reference.xml`.

Key lines to ensure are present:
```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.INTERNET" />
```

Also add `android:usesCleartextTraffic="true"` to the `<application>` tag
for local HTTP (remove in production).

### 3c – iOS permissions (macOS only)

Merge the keys from `mobile/ios_info_plist_additions.xml` into
`mobile/ios/Runner/Info.plist`.

### 3d – Install Flutter packages

```powershell
cd mobile
flutter pub get
```

### 3e – Run the app

```powershell
# List available devices
flutter devices

# Run on a connected device / emulator
flutter run

# Run in release mode (faster)
flutter run --release
```

---

## 4 · API Reference

Base URL: `http://localhost:8000`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/attendance/test` | Router health check |
| POST | `/attendance/mark` | Upload audio → recognize speaker → log |
| GET | `/attendance/logs` | All attendance records |
| GET | `/attendance/logs/{user_name}` | Records for one user |

### POST /attendance/mark

```
Content-Type: multipart/form-data
Field:        audio  (WAV / MP3 / OGG / FLAC, max 10 MB)
```

**Response:**
```json
{
  "status":     "success",
  "user_name":  "alice",
  "confidence": 0.93,
  "log": {
    "id":        1,
    "user_name": "alice",
    "timestamp": "2025-06-01T09:30:00+00:00"
  }
}
```

---

## 5 · Integrating a Real AI Model (PyTorch)

The voice pipeline in `app/models/voice_model.py` is production-ready for
plug-in. Follow these steps:

### Step 1 – Collect training data
Record audio samples (WAV, 16 kHz mono, 3-5 s) for each user.
Organise into folders: `data/alice/`, `data/bob/`, …

### Step 2 – Train the model

```python
# Pseudo-code training loop
from app.models.voice_model import extract_features, load_audio

# Build dataset: load each file → extract_features() → label
# Train SpeakerNet (defined in voice_model.py – uncomment the class)
# Save: torch.save({"model_state": model.state_dict(),
#                   "label_map":   {0: "alice", 1: "bob"}},
#                  "models/speaker_net.pt")
```

### Step 3 – Activate the model

In `voice_model.py`:
1. Uncomment the `SpeakerNet` class and `_load_model()` call.
2. Replace the stub body of `recognize_speaker()` with the
   commented-out PyTorch inference block.

### Step 4 – Restart the server

```powershell
uvicorn app.main:app --reload
```

---

## 6 · Environment Variables (Optional)

Create `backend/.env` for secret management:

```env
DB_NAME=voiceattend
DB_USER=voiceuser
DB_PASSWORD=voicepass
DB_HOST=localhost
DB_PORT=5432
```

Then update `database.py` to load with `python-dotenv`:

```python
from dotenv import load_dotenv
import os
load_dotenv()

DB_CONFIG = {
    "dbname":   os.getenv("DB_NAME",     "voiceattend"),
    "user":     os.getenv("DB_USER",     "voiceuser"),
    "password": os.getenv("DB_PASSWORD", "voicepass"),
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
}
```

---

## 7 · Common Issues

| Problem | Fix |
|---------|-----|
| `psycopg2.OperationalError: could not connect` | Ensure PostgreSQL is running and `DB_CONFIG` matches |
| `librosa not found` | Run `pip install librosa soundfile` inside venv |
| `RECORD_AUDIO permission denied` on Android | Grant in device Settings → Apps → VoiceAttend |
| Flutter can't reach backend | Check `baseUrl` — use `10.0.2.2` for Android emulator |
| `usesCleartextTraffic` error on Android | Add `android:usesCleartextTraffic="true"` to `<application>` in AndroidManifest |
| `torch` install slow | Use the CPU-only pip wheel or select CUDA build from pytorch.org |

---

## 8 · Production Checklist

- [ ] Replace `voicepass` with a strong password and use env vars
- [ ] Set `allow_origins` in CORS to your actual domain(s)
- [ ] Use HTTPS (add a reverse proxy: Nginx / Caddy)
- [ ] Remove `android:usesCleartextTraffic="true"` from the manifest
- [ ] Remove `NSAllowsArbitraryLoads` from iOS Info.plist
- [ ] Train and embed a real speaker recognition model
- [ ] Add authentication (JWT / OAuth2) to the FastAPI backend
- [ ] Run with a production ASGI server: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app`

---

## License

MIT – free to use for personal and commercial projects.
