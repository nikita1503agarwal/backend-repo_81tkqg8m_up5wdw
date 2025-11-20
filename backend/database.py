import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient
from pymongo.collection import Collection

DATABASE_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "perspectivebyadi")

_client = MongoClient(DATABASE_URL)
db = _client[DATABASE_NAME]


def get_collection(name: str) -> Collection:
    return db[name]


def create_document(collection_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    col = get_collection(collection_name)
    now = datetime.utcnow().isoformat()
    if isinstance(data, list):
        # bulk insert
        for d in data:
            d["created_at"] = now
            d["updated_at"] = now
        result = col.insert_many(data)
        inserted = list(col.find({"_id": {"$in": result.inserted_ids}}))
    else:
        data["created_at"] = now
        data["updated_at"] = now
        result = col.insert_one(data)
        inserted = col.find_one({"_id": result.inserted_id})
        if inserted:
            inserted = [inserted]
    # Normalize ObjectId to str
    for doc in inserted:
        doc["id"] = str(doc.pop("_id"))
    return inserted[0] if len(inserted) == 1 else inserted


def get_documents(
    collection_name: str,
    filter_dict: Optional[Dict[str, Any]] = None,
    limit: Optional[int] = None,
    sort: Optional[List[tuple]] = None,
) -> List[Dict[str, Any]]:
    col = get_collection(collection_name)
    cursor = col.find(filter_dict or {})
    if sort:
        cursor = cursor.sort(sort)
    if limit:
        cursor = cursor.limit(limit)
    docs: List[Dict[str, Any]] = []
    for d in cursor:
        d["id"] = str(d.pop("_id"))
        docs.append(d)
    return docs


def update_document(collection_name: str, filter_dict: Dict[str, Any], update_dict: Dict[str, Any]) -> int:
    col = get_collection(collection_name)
    update_dict["updated_at"] = datetime.utcnow().isoformat()
    res = col.update_many(filter_dict, {"$set": update_dict})
    return res.modified_count


def delete_documents(collection_name: str, filter_dict: Dict[str, Any]) -> int:
    col = get_collection(collection_name)
    res = col.delete_many(filter_dict)
    return res.deleted_count
