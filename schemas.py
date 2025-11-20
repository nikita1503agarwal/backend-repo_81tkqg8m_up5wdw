from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List

class Category(BaseModel):
    name: str = Field(..., description="Display name")
    slug: str = Field(..., description="URL-friendly unique identifier")
    description: Optional[str] = Field(None, description="Short description")
    cover_url: Optional[HttpUrl] = Field(None, description="Cover image URL")

class Folder(BaseModel):
    name: str = Field(...)
    slug: str = Field(...)
    category_slug: str = Field(..., description="Parent category slug")
    parent_id: Optional[str] = Field(None, description="Parent folder ObjectId string")
    description: Optional[str] = None

class Image(BaseModel):
    url: HttpUrl
    alt: Optional[str] = None
    width: Optional[int] = Field(None, ge=1)
    height: Optional[int] = Field(None, ge=1)
    category_slug: str
    folder_id: Optional[str] = None
    tags: Optional[List[str]] = None

class ContactMessage(BaseModel):
    name: str
    email: str
    message: str
    budget: Optional[str] = None
    shoot_type: Optional[str] = None
