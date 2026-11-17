"""Shared upload reading with a size cap."""

from fastapi import UploadFile

from hwai.errors import ApiError
from hwai.pdfio import MAX_BYTES


def read_upload(file: UploadFile) -> bytes:
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ApiError(413, "file_too_large", "That file is over 20 MB.")
    return data
