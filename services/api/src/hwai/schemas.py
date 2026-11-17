"""Pydantic API schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    renderer: str
    ocr: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
