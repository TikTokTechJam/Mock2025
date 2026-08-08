from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "freecoinalert-api"


health_router = APIRouter()


@health_router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse()
