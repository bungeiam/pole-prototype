from datetime import datetime
from typing import Literal
from pydantic import BaseModel


DocumentStatus = Literal["uploaded", "analyzed", "matched", "calculated", "reviewed", "finalized"]


class OfferDocument(BaseModel):
    document_id: str
    original_filename: str
    stored_path: str
    file_type: str
    upload_time: datetime
    status: DocumentStatus = "uploaded"