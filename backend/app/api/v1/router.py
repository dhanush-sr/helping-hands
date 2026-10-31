"""Collects every v1 endpoint module. Add new routers here (auth, stores, shifts, ...)."""

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
