import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, Form, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from bson import ObjectId
from uuid import uuid4
from pathlib import Path

from database import db, create_document, get_documents
from schemas import Category, Folder, Image, ContactMessage

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
    # Enforce unique slug
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
        try:
            filt["parent_id"] = parent_id
        except Exception:
            pass
    docs = get_documents("folder", filt)
    return [serialize_doc(d) for d in docs]

@app.post("/folders")
def create_folder(payload: Folder) -> SerializedId:
    # Optional: verify category exists
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
def create_image(payload: Image) -> SerializedId:
    # Optional: verify references
    if not db["category"].find_one({"slug": payload.category_slug}):
        raise HTTPException(status_code=400, detail="Category not found")
    new_id = create_document("image", payload)
    return SerializedId(id=new_id)

# File upload -> returns public URL
@app.post("/upload")
async def upload_image(request: Request, file: UploadFile = File(...)):
    # Validate content type minimal
    if not (file.content_type and file.content_type.startswith("image/")):
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    ext = Path(file.filename).suffix.lower() or ".jpg"
    safe_name = f"{uuid4().hex}{ext}"
    dest_path = UPLOAD_DIR / safe_name
    try:
        content = await file.read()
        dest_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)[:80]}")

    # Build absolute URL to the uploaded file
    base_url = str(request.base_url).rstrip('/')
    file_url = f"{base_url}/uploads/{safe_name}"
    return {"url": file_url, "filename": safe_name}

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
