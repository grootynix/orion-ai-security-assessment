from typing import Literal

from pydantic import BaseModel, Field


Role = Literal["employee", "manager", "administrator"]


class UserContext(BaseModel):
    email: str
    role: Role
    projects: list[str] = Field(default_factory=list)


class TokenRequest(BaseModel):
    email: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class SendEmailRequest(BaseModel):
    to: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
