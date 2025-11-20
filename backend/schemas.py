from typing import List, Optional, Literal
from pydantic import BaseModel, Field, HttpUrl, EmailStr

# Collections:
# - user (site owner)
# - category (portraits, events, street)
# - folder (nested folders inside categories, used mainly by events)
# - image (media records)
# - settings (site-wide settings like hero image)


class User(BaseModel):
    email: EmailStr
    password_hash: str
    role: Literal["owner"] = "owner"


class Category(BaseModel):
    name: str = Field(..., examples=["Portraits", "Events", "Street"]) 
    slug: str = Field(..., examples=["portraits", "events", "street"]) 
    description: Optional[str] = None
    cover_url: Optional[HttpUrl] = None


class Folder(BaseModel):
    # belongs to a category, allows nesting via parent_id
    name: str
    slug: str
    category_slug: str
    parent_id: Optional[str] = None
    description: Optional[str] = None


class Image(BaseModel):
    url: HttpUrl
    # Optional optimized sizes/alt text for SEO
    alt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    category_slug: str
    folder_id: Optional[str] = None  # for events subfolders
    # simple tags for filtering
    tags: Optional[List[str]] = None


class ContactMessage(BaseModel):
    name: str
    email: EmailStr
    message: str
    budget: Optional[str] = None
    shoot_type: Optional[str] = Field(None, description="Portrait, Event, Street, Other")


class Settings(BaseModel):
    hero_url: Optional[HttpUrl] = None
