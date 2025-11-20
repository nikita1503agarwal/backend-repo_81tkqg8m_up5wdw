import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Form, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from bson import ObjectId
from uuid import uuid4
from pathlib import Path
from io import BytesIO

from PIL import Image

from database import db, create_document, get_documents
from schemas import Category, Folder, Image as ImageModel, ContactMessage

app = FastAPI(title="Perspective by Adi API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static uploads directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Config
try:
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "35"))  # pre-resize input cap
except Exception:
    MAX_UPLOAD_MB = 35
try:
    RESIZE_MAX_SIDE = int(os.getenv("RESIZE_MAX_SIDE", "4096"))  # px
except Exception:
    RESIZE_MAX_SIDE = 4096
try:
    JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "92"))
except Exception:
    JPEG_QUALITY = 92
try:
    WEBP_QUALITY = int(os.getenv("WEBP_QUALITY", "92"))
except Exception:
    WEBP_QUALITY = 92

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg", "image/pjpeg"}

# Helpers
class SerializedId(BaseModel):
    id: str

def serialize_doc(doc: dict) -> dict:
    if not doc:
        return doc
    d = dict(doc)
    _id = d.pop("_id", None)
    if isinstance(_id, ObjectId):
        d["id"] = str(_id)
    elif _id is not None:
        d["id"] = str(_id)
    return d

@app.get("/")
def root():
    return {"app": "Perspective by Adi API", "status": "ok"}

# Categories
@app.get("/categories")
def list_categories() -> List[dict]:
    docs = get_documents("category")
    return [serialize_doc(d) for d in docs]

@app.post("/categories")
def create_category(payload: Category) -> SerializedId:
    if db["category"].find_one({"slug": payload.slug}):
        raise HTTPException(status_code=400, detail="Category slug already exists")
    new_id = create_document("category", payload)
    return SerializedId(id=new_id)

# Folders
@app.get("/folders")
def list_folders(category_slug: Optional[str] = None, parent_id: Optional[str] = None) -> List[dict]:
    filt = {}
    if category_slug:
        filt["category_slug"] = category_slug
    if parent_id:
        filt["parent_id"] = parent_id
    docs = get_documents("folder", filt)
    return [serialize_doc(d) for d in docs]

@app.post("/folders")
def create_folder(payload: Folder) -> SerializedId:
    if not db["category"].find_one({"slug": payload.category_slug}):
        raise HTTPException(status_code=400, detail="Category not found")
    new_id = create_document("folder", payload)
    return SerializedId(id=new_id)

# Images
@app.get("/images")
def list_images(category_slug: Optional[str] = None, folder_id: Optional[str] = None, limit: Optional[int] = None) -> List[dict]:
    filt = {}
    if category_slug:
        filt["category_slug"] = category_slug
    if folder_id:
        filt["folder_id"] = folder_id
    docs = get_documents("image", filt, limit=limit)
    return [serialize_doc(d) for d in docs]

@app.post("/images")
def create_image(payload: ImageModel) -> SerializedId:
    if not db["category"].find_one({"slug": payload.category_slug}):
        raise HTTPException(status_code=400, detail="Category not found")
    new_id = create_document("image", payload)
    return SerializedId(id=new_id)

@app.delete("/images/{image_id}")
def delete_image(image_id: str):
    if not ObjectId.is_valid(image_id):
        raise HTTPException(status_code=400, detail="Invalid image id")
    doc = db["image"].find_one({"_id": ObjectId(image_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Image not found")

    # Try to remove local file if it was uploaded to our uploads directory
    try:
        url = str(doc.get("url", ""))
        marker = "/uploads/"
        if marker in url:
            fname = url.split(marker, 1)[1]
            file_path = UPLOAD_DIR / fname
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
    except Exception:
        # Ignore file deletion errors, proceed to DB delete
        pass

    db["image"].delete_one({"_id": ObjectId(image_id)})
    return {"deleted": True}

# Image processing

def _resize_and_compress(img: Image.Image) -> tuple[bytes, str, str]:
    # Ensure RGB/RGBA
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)

    # Resize if needed preserving aspect
    w, h = img.size
    max_side = max(w, h)
    if max_side > RESIZE_MAX_SIDE:
        scale = RESIZE_MAX_SIDE / float(max_side)
        new_size = (int(round(w * scale)), int(round(h * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    # Choose format: preserve alpha with WEBP, otherwise high-quality JPEG
    if has_alpha:
        fmt = "WEBP"
        ext = ".webp"
        out = BytesIO()
        img.save(out, fmt, quality=WEBP_QUALITY, method=6)  # method 6 = best
        mime = "image/webp"
    else:
        # Convert to RGB for JPEG
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        fmt = "JPEG"
        ext = ".jpg"
        out = BytesIO()
        img.save(out, fmt, quality=JPEG_QUALITY, optimize=True, progressive=True)
        mime = "image/jpeg"

    return out.getvalue(), ext, mime

# File upload -> returns processed, public URL
@app.post("/upload")
async def upload_image(request: Request, file: UploadFile = File(...)):
    # Validate content type early (best-effort; we also validate by trying to open it)
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, or WEBP images are allowed")

    # Cap raw input size
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    raw = bytearray()
    read_total = 0
    try:
        while True:
            chunk = await file.read(1024 * 1024)  # 1MB
            if not chunk:
                break
            read_total += len(chunk)
            if read_total > max_bytes:
                raise HTTPException(status_code=413, detail=f"File too large. Max {MAX_UPLOAD_MB}MB")
            raw.extend(chunk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read upload: {str(e)[:80]}")

    # Decode image with Pillow
    try:
        with Image.open(BytesIO(raw)) as img:
            img.load()
            processed_bytes, ext, final_mime = _resize_and_compress(img)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid or unsupported image: {str(e)[:80]}")

    # Save processed image
    safe_name = f"{uuid4().hex}{ext}"
    dest_path = UPLOAD_DIR / safe_name
    try:
        dest_path.write_bytes(processed_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)[:80]}")

    # Build public URL
    base_url = str(request.base_url).rstrip('/')
    file_url = f"{base_url}/uploads/{safe_name}"

    return {
        "url": file_url,
        "filename": safe_name,
        "original_size_bytes": read_total,
        "processed_size_bytes": len(processed_bytes),
        "content_type": final_mime,
        "max_side_px": RESIZE_MAX_SIDE,
        "quality": JPEG_QUALITY if final_mime == "image/jpeg" else WEBP_QUALITY,
    }

# Contact
@app.post("/contact")
def submit_contact(payload: ContactMessage) -> SerializedId:
    new_id = create_document("contactmessage", payload)
    return SerializedId(id=new_id)

# Admin seed (OWNER_KEY required via form field)
@app.post("/admin/seed")
def admin_seed(owner_key: str = Form(...)):
    expected = os.getenv("OWNER_KEY")
    if not expected or owner_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

    base_categories = [
        {"name": "Weddings", "slug": "weddings", "description": "Timeless wedding stories", "cover_url": "https://images.unsplash.com/photo-1522673607200-164d1b6ce486?q=80&w=1600&auto=format&fit=crop"},
        {"name": "Portraits", "slug": "portraits", "description": "Studio and environmental portraits", "cover_url": "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?q=80&w=1600&auto=format&fit=crop"},
        {"name": "Events", "slug": "events", "description": "Corporate and social events", "cover_url": "https://images.unsplash.com/photo-1531058020387-3be344556be6?q=80&w=1600&auto=format&fit=crop"},
        {"name": "Travel", "slug": "travel", "description": "Places and stories from the road", "cover_url": "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?q=80&w=1600&auto=format&fit=crop"}
    ]

    created = 0
    for cat in base_categories:
        if not db["category"].find_one({"slug": cat["slug"]}):
            db["category"].insert_one(cat)
            created += 1

    return {"seeded": created, "total_categories": db["category"].count_documents({})}

# Health
@app.get("/test")
def test_database():
    response = {
        "backend": "running",
        "database": "connected" if db is not None else "not-configured",
        "collections": []
    }
    try:
        if db is not None:
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"error: {str(e)[:80]}"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
