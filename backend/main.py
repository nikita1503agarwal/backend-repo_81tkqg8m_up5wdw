from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os

from database import db, create_document, get_documents, update_document, delete_documents
from schemas import Category, Folder, Image, ContactMessage

app = FastAPI(title="Perspective by Adi API")

# CORS
frontend_url = os.getenv("FRONTEND_URL", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Status(BaseModel):
    status: str


@app.get("/", response_model=Status)
def root():
    return {"status": "ok"}


@app.get("/test", response_model=Status)
def test_db():
    # simple ping to ensure DB accessible
    try:
        db.list_collection_names()
        return {"status": "db_ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Categories endpoints
@app.get("/categories", response_model=List[Category])
def list_categories():
    items = get_documents("category", {}, sort=[("name", 1)])
    return items


@app.post("/categories", response_model=Category)
def create_category(payload: Category):
    inserted = create_document("category", payload.model_dump())
    return inserted


# Folders (for events nesting)
@app.get("/folders", response_model=List[Folder])
def list_folders(category_slug: Optional[str] = None, parent_id: Optional[str] = None):
    query = {}
    if category_slug:
        query["category_slug"] = category_slug
    if parent_id is not None:
        query["parent_id"] = parent_id
    return get_documents("folder", query, sort=[("name", 1)])


@app.post("/folders", response_model=Folder)
def create_folder(payload: Folder):
    inserted = create_document("folder", payload.model_dump())
    return inserted


# Images
@app.get("/images", response_model=List[Image])
def list_images(category_slug: Optional[str] = None, folder_id: Optional[str] = None, limit: Optional[int] = None):
    query = {}
    if category_slug:
        query["category_slug"] = category_slug
    if folder_id:
        query["folder_id"] = folder_id
    return get_documents("image", query, limit=limit, sort=[("created_at", -1)])


@app.post("/images", response_model=Image)
def create_image(payload: Image):
    inserted = create_document("image", payload.model_dump())
    return inserted


# Contact messages (store for follow-up)
@app.post("/contact", response_model=Status)
def contact(payload: ContactMessage):
    create_document("contactmessage", payload.model_dump())
    return {"status": "received"}


# Simple owner key auth for admin endpoints
OWNER_KEY = os.getenv("OWNER_KEY", "dev-owner-key")

def owner_auth(x_owner_key: str = Form(...)):
    if x_owner_key != OWNER_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# Admin helpers
@app.post("/admin/seed", response_model=Status)
def seed(owner_key: str = Form(...)):
    if owner_key != OWNER_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Ensure base categories exist
    base_categories = [
        {"name": "Portraits", "slug": "portraits", "description": "People & character studies"},
        {"name": "Events", "slug": "events", "description": "Documenting celebrations and milestones"},
        {"name": "Street", "slug": "street", "description": "Candid slices of city life"},
    ]
    existing = {c["slug"] for c in get_documents("category")}
    to_create = [c for c in base_categories if c["slug"] not in existing]
    if to_create:
        create_document("category", to_create)

    return {"status": "seeded"}


# File upload placeholder: in this environment we'll accept direct URL uploads for simplicity.
# In a real deployment you would integrate S3/Cloudinary. Here we store canonical URL + metadata.


