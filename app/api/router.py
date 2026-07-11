"""Central API router — the one place every domain router is registered.

Adding a module = add its `routes/<name>.py`, import its `router` here, and
include it. `main.py` mounts this single aggregate router, nothing else.
"""
from fastapi import APIRouter
from app.api.routes import (
    system, auth, schools, students, results, audit, imports,
)

api_router = APIRouter()
for module in (system, auth, schools, students, results, audit, imports):
    api_router.include_router(module.router)
