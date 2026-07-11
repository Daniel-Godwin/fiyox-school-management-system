"""Bulk import endpoints: download a template, then upload students in one file."""
from typing import Annotated
from fastapi import (
    APIRouter, Depends, File, HTTPException, Query, Request, UploadFile,
)
from fastapi.responses import StreamingResponse
from io import BytesIO
from app.core.deps import DbDep, require_roles, tenant_scope
from app.models.school import User, Role
from app.services.importer import parse_upload, import_students, template_csv

router = APIRouter(prefix="/api/import")


@router.get("/students/template", tags=["import"])
async def download_template(
    _: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
):
    data = template_csv().encode("utf-8-sig")
    return StreamingResponse(
        BytesIO(data), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="fiyox_students_template.csv"'})


@router.post("/students", tags=["import"])
async def upload_students(
    request: Request,
    db: DbDep,
    user: Annotated[User, Depends(require_roles(Role.SCHOOL_ADMIN))],
    file: UploadFile = File(...),
    auto_create_classes: bool = Query(True,
        description="Create missing classes/arms from the sheet instead of erroring"),
    dry_run: bool = Query(False, description="Validate only; write nothing"),
):
    school_id = tenant_scope(user)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        rows = parse_upload(file.filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rows:
        raise HTTPException(status_code=400, detail="No data rows found in file")

    ip = request.client.host if request.client else None
    return await import_students(
        db, school_id, user.id, rows,
        auto_create=auto_create_classes, dry_run=dry_run, ip=ip)
