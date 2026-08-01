"""Public response models for the CtoN API."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel


DataT = TypeVar("DataT")


class ApiResponse(BaseModel, Generic[DataT]):
    code: int = 0
    message: str = "ok"
    data: DataT
    request_id: str


class ErrorDetail(BaseModel):
    code: int
    message: str
    data: dict[str, Any]
    request_id: str
