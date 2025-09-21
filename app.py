from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uuid, os, json
from pathlib import Path
import qrcode
from datetime import datetime
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db.json"
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOADS = BASE_DIR / "uploads"
QR_DIR = UPLOADS / "qrcodes"
IMG_DIR = UPLOADS / "images"
AUDIO_DIR = UPLOADS / "audio"

# Ensure directories exist
for d in (UPLOADS, QR_DIR, IMG_DIR, AUDIO_DIR, FRONTEND_DIR):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Artisan AI Processing (Prototype)")

# Allow frontend JS to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Utility functions ---
def load_db():
    if DB_PATH.exists():
        return json.loads(DB_PATH.read_text(encoding="utf-8"))
    else:
        return {"products": {}}

def save_db(db):
    DB_PATH.write_text(json.dumps(db, indent=2), encoding="utf-8")

def mock_transcribe(audio_filename: Optional[str] = None, transcript_field: Optional[str] = None):
    if transcript_field and transcript_field.strip():
        return transcript_field.strip()
    if audio_filename:
        name = Path(audio_filename).stem.replace("_", " ").title()
        return f"My name is {name}. I make this product with traditional techniques learned from my family."
    return "My name is Lakshmi, I weave sarees using a 200-year-old loom."

def extract_name_from_transcript(transcript: str) -> str:
    lower = transcript.lower()
    if "my name is " in lower:
        try:
            after = transcript.split("my name is ", 1)[1]
            name = after.split()[0:2]
            return " ".join(name).strip().strip(",.").title()
        except:
            pass
    return "A Local Artisan"

def generate_micro_story(transcript: str) -> str:
    name = extract_name_from_transcript(transcript)
    if "loom" in transcript.lower() or "weave" in transcript.lower():
        return f"Handwoven by {name} on a traditional loom — preserving ancestral textile art."
    if "potter" in transcript.lower() or "clay" in transcript.lower() or "pottery" in transcript.lower():
        return f"Shaped by {name}'s hands — pottery that carries generations of craft."
    return f"Made by {name}, a craftsman keeping local traditions alive."

def infer_tags(tags_field: Optional[str], image_filename: Optional[str] = None):
    if tags_field:
        parts = [t.strip().lower() for t in tags_field.split(",") if t.strip()]
        if parts:
            return parts
    if image_filename:
        fname = Path(image_filename).stem.lower()
        guesses = []
        for key in ["saree", "shawl", "pottery", "mug", "bottle", "wood", "carving", "painting", "handloom", "jewelry", "bangle"]:
            if key in fname:
                guesses.append(key)
        if guesses:
            return guesses
    return ["handmade", "traditional"]

def suggest_price_range(tags):
    tags = [t.lower() for t in tags]
    if any(x in tags for x in ["saree", "handloom", "silk", "shawl"]):
        return "₹1500–₹3500"
    if any(x in tags for x in ["pottery", "mug", "clay"]):
        return "₹300–₹1200"
    if any(x in tags for x in ["jewelry", "bangle", "wood"]):
        return "₹500–₹2500"
    return "₹200–₹800"

def generate_qr(product_id: str):
    # ⚠️ Replace this with your actual server domain
    base_url = "https://myapp.example.com"  
    cert_url = f"{base_url}/certificate/{product_id}"

    qr_path = QR_DIR / f"{product_id}.png"
    qr = qrcode.make(cert_url)
    qr.save(qr_path)
    return str(qr_path.name)


# --- Routes ---
@app.post("/process")
async def process(
    product_name: str = Form(...),
    tags: Optional[str] = Form(None),
    transcript: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
):
    img_filename = None
    audio_filename = None
    if image:
        img_filename = f"{uuid.uuid4().hex}_{image.filename}"
        path = IMG_DIR / img_filename
        with path.open("wb") as f:
            f.write(await image.read())
    if audio:
        audio_filename = f"{uuid.uuid4().hex}_{audio.filename}"
        path = AUDIO_DIR / audio_filename
        with path.open("wb") as f:
            f.write(await audio.read())

    transcript_text = mock_transcribe(audio_filename=audio_filename, transcript_field=transcript)
    story = generate_micro_story(transcript_text)
    inferred_tags = infer_tags(tags, image_filename=img_filename)
    price_range = suggest_price_range(inferred_tags)

    product_id = uuid.uuid4().hex
    qr_file = generate_qr(product_id)

    record = {
        "id": product_id,
        "name": product_name,
        "image": img_filename,
        "audio": audio_filename,
        "transcript": transcript_text,
        "story": story,
        "tags": inferred_tags,
        "price_range": price_range,
        "qr": qr_file,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }

    db = load_db()
    db["products"][product_id] = record
    save_db(db)

    return {
        "id": product_id,
        "name": product_name,
        "tags": inferred_tags,
        "story": story,
        "price_range": price_range,
        "qr_link": f"/uploads/qrcodes/{qr_file}",
        "certificate_link": f"/certificate/{product_id}",
        "image_link": f"/uploads/images/{img_filename}" if img_filename else None
    }

@app.get("/certificate/{pid}", response_class=HTMLResponse)
async def certificate(pid: str):
    db = load_db()
    product = db["products"].get(pid)
    if not product:
        return HTMLResponse("<h3>Certificate not found</h3>", status_code=404)
    img_tag = f'<img src="/uploads/images/{product["image"]}" style="max-width:300px">' if product["image"] else ""
    qr_tag = f'<img src="/uploads/qrcodes/{product["qr"]}" style="width:160px">' if product["qr"] else ""
    return f"""
    <html><head><title>Certificate - {product['name']}</title></head><body>
    <h2>Authenticity Certificate</h2>
    <h3>{product['name']}</h3>
    {img_tag}
    <p><strong>Micro-story:</strong> {product['story']}</p>
    <p><strong>Tags:</strong> {', '.join(product['tags'])}</p>
    <p><strong>Suggested Price Range:</strong> {product['price_range']}</p>
    {qr_tag}
    <p>Generated at: {product['created_at']}</p>
    </body></html>
    """

@app.get("/health")
def health():
    return {"status": "ok"}

# --- Static file serving ---
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
