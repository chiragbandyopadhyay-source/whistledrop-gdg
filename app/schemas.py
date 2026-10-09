from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

Category = Literal["Security", "Harassment", "Corruption", "Technical", "Other"]
Status = Literal["SUBMITTED", "UNDER_REVIEW", "RESOLVED", "DISMISSED"]


class ReportIn(BaseModel):
    category: Category
    description: str = Field(min_length=10, max_length=5000)
    evidence_url: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("description")
    @classmethod
    def _strip_desc(cls, v):
        v = v.strip()
        if len(v) < 10:
            raise ValueError("description must be at least 10 characters")
        return v

    @field_validator("evidence_url")
    @classmethod
    def _check_url(cls, v):
        if v is None or v.strip() == "":
            return None
        p = urlparse(v.strip())
        if p.scheme not in ("http", "https") or not p.netloc:
            raise ValueError("evidence_url must be a valid http(s) URL")
        return v.strip()


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class StatusChangeIn(BaseModel):
    status: Status
    message: Optional[str] = Field(default=None, max_length=1000)


class UpdateIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)

    @field_validator("message")
    @classmethod
    def _strip(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("message must not be blank")
        return v