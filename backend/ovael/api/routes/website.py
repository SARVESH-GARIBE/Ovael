"""Website analysis: submit a URL, poll or wait for scan_complete, read the report."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select

from ...core.context import AppContext
from ...db.models import Detection, Scan
from ...services import scans
from ..deps import client_ip, get_ctx
from ..schemas import DetectionOut, ScanCreate, ScanDetail, ScanOut

router = APIRouter(prefix="/api", tags=["website"])


@router.post("/scans", response_model=ScanOut, status_code=202, summary="Submit a URL; returns a scan id")
async def create_scan(body: ScanCreate, request: Request, response: Response,
                      ctx: AppContext = Depends(get_ctx)) -> Scan:
    scan = await scans.submit(ctx, body.url, client_ip(request))
    if scan.cached:
        response.status_code = 200
    response.headers["Location"] = f"/api/scans/{scan.id}"
    return scan


@router.get("/scans", response_model=list[ScanOut], summary="Recent scans")
async def list_scans(ctx: AppContext = Depends(get_ctx), limit: int = Query(20, ge=1, le=100)) -> list[Scan]:
    async with ctx.db.read_session() as s:
        return list(await s.scalars(select(Scan).order_by(Scan.created_at.desc()).limit(limit)))


@router.get("/scans/{scan_id}", response_model=ScanDetail, summary="Scan status and finished report")
async def get_scan(scan_id: str, ctx: AppContext = Depends(get_ctx)) -> ScanDetail:
    # Primary, not the replica: clients poll this right after submitting.
    async with ctx.db.session() as s:
        scan = await s.get(Scan, scan_id)
        if scan is None:
            raise HTTPException(404, "scan not found")
        det = await s.get(Detection, scan.detection_id) if scan.detection_id else None
    out = ScanDetail.model_validate(scan)
    out.detection = DetectionOut.model_validate(det) if det else None
    return out
