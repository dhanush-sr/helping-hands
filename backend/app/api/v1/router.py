"""Collects every v1 endpoint module. Add new routers here (auth, stores, shifts, ...)."""

from fastapi import APIRouter

from app.api.v1 import auth, busy_periods, health, stores

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(stores.router)
api_router.include_router(busy_periods.router)
