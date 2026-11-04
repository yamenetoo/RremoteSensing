"""REST API for geedownload (FastAPI).

Run:  geedownload serve --port 8000      (or: uvicorn geedownload.api:app)
Docs: http://localhost:8000/docs

Server settings (environment variables):
  EE_PROJECT                 Earth Engine / Google Cloud project id
  EE_SERVICE_ACCOUNT, EE_PRIVATE_KEY_FILE   headless Earth Engine login (service account)
  GEEDOWNLOAD_API_KEY        if set, every request except / /health /logo.png needs header  X-API-Key
  GEEDOWNLOAD_WORKDIR        where jobs are stored (default ./api_jobs)
  GEEDOWNLOAD_WORKERS        parallel download jobs (default 2)
  GEEDOWNLOAD_MAX_AREA_KM2   refuse bigger areas (default 20000)
  GEEDOWNLOAD_CORS_ORIGINS   comma separated origins allowed for browser clients
"""
from __future__ import annotations

import hmac
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Union

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from shapely.geometry import mapping

from . import AUTHOR, __version__
from .aoi import VECTOR_EXT, resolve_aoi
from .boundary import save_boundary
from .catalog import list_datasets
from .errors import AreaNotFound, GeeDownloadError
from .geocode import search_area
from .utils import logger, slugify, timestamp, zip_dir

ASSETS = Path(__file__).parent / "assets"
JOB_ID = re.compile(r"^[0-9a-f]{12}$")


def _workdir() -> Path:
    p = Path(os.environ.get("GEEDOWNLOAD_WORKDIR", "api_jobs"))
    p.mkdir(parents=True, exist_ok=True)
    return p


# ----------------------------------------------------------------------------- request models
class DownloadRequest(BaseModel):
    area: Union[str, List[float]] = Field(..., description='Place name ("Masyaf, Syria") or [west, south, east, north]')
    dataset: str = Field("sentinel2", description="Dataset key (see GET /datasets) or an Earth Engine asset id")
    start: Optional[str] = Field(None, examples=["2023-06-01"])
    end: Optional[str] = Field(None, examples=["2023-09-30"])
    bands: Optional[List[str]] = Field(None, description="Band or group names; default = dataset defaults")
    cloud_max: Optional[float] = Field(20, ge=0, le=100)
    reducer: Optional[str] = Field(None, description="median, mean, min, max, sum, mode, first, mosaic")
    scale: Optional[float] = Field(None, gt=0, description="Pixel size in metres (default: native)")
    crs: Optional[str] = Field(None, examples=["EPSG:32637"])
    clip: bool = True
    mask_clouds: bool = False
    apply_scale: bool = False
    per_image: bool = False
    max_images: int = Field(10, ge=1, le=50)
    stack: bool = True
    buffer_m: float = Field(0, ge=0)
    pick: int = Field(0, ge=0, description="Which place-search candidate to use")
    make_map: bool = Field(True, description="Also render preview.jpg")
    zip_output: bool = False


class MapRequest(BaseModel):
    bands: Optional[List[str]] = Field(None, description="1 band = colour bar, 3 bands = RGB")
    cmap: Optional[str] = Field(None, description="Matplotlib colour map for a single band (default: automatic)")
    classes: Optional[str] = Field(None, description='"worldcover" or "dynamic_world" for categorical maps')
    title: Optional[str] = None
    country: Optional[str] = None
    legend_label: Optional[str] = None
    context: bool = True
    inset: bool = True
    dpi: int = Field(200, ge=72, le=400)


class AreaMapRequest(BaseModel):
    area: Union[str, List[float]]
    country: Optional[str] = None
    extent: str = Field("area", pattern="^(area|country)$")
    title: Optional[str] = None
    pick: int = Field(0, ge=0)
    admin1: bool = False
    dpi: int = Field(200, ge=72, le=400)


# ----------------------------------------------------------------------------- jobs
class Jobs:
    """In-memory job table (job folders stay on disk)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.items: Dict[str, dict] = {}
        self.pool = ThreadPoolExecutor(max_workers=int(os.environ.get("GEEDOWNLOAD_WORKERS", "2")))

    def create(self, request: dict) -> str:
        jid = uuid.uuid4().hex[:12]
        with self.lock:
            self.items[jid] = {"job_id": jid, "status": "queued", "created": time.time(), "request": request,
                               "folder": None, "info": None, "error": None, "preview_error": None}
        return jid

    def update(self, jid: str, **kw) -> None:
        with self.lock:
            self.items[jid].update(kw)

    def get(self, jid: str) -> dict:
        if not JOB_ID.match(jid) or jid not in self.items:
            raise HTTPException(404, "Unknown job id")
        return self.items[jid]


def _check_area(area):
    if isinstance(area, str) and Path(area).suffix.lower() in VECTOR_EXT:
        raise HTTPException(400, "File paths are not accepted by the API; send a place name or a bbox.")
    if isinstance(area, list) and len(area) != 4:
        raise HTTPException(422, "A bbox needs exactly 4 numbers: [west, south, east, north].")


def _run_download(jobs: Jobs, jid: str, req: DownloadRequest) -> None:
    from .pipeline import download_area

    jobs.update(jid, status="running")
    try:
        job_dir = _workdir() / jid
        res = download_area(
            req.area, req.dataset, req.start, req.end, out_dir=job_dir, bands=req.bands, cloud_max=req.cloud_max,
            reducer=req.reducer, scale=req.scale, crs=req.crs, clip=req.clip, mask_clouds=req.mask_clouds,
            apply_scale=req.apply_scale, per_image=req.per_image, max_images=req.max_images, stack=req.stack,
            zip_output=req.zip_output, buffer_m=req.buffer_m, pick=req.pick,
            max_area_km2=float(os.environ.get("GEEDOWNLOAD_MAX_AREA_KM2", "20000")))
        jobs.update(jid, folder=str(res.folder), info=res.info)
        preview_error = None
        raster = res.stack or (res.scenes[0] if res.scenes else None)
        if req.make_map and raster:
            try:
                from .maps import plot_map, preview_args

                plot_map(raster, res.folder / "preview.jpg", area=res.shapefile, title=res.info.get("area"),
                         country=res.info.get("country"),
                         source=f"Data: {res.info['dataset']} via Google Earth Engine, "
                                f"{res.info.get('start') or ''} to {res.info.get('end') or ''}",
                         **preview_args(res.info))
            except Exception as exc:    # a failed preview must not fail the download
                preview_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Preview failed: %s", preview_error)
        jobs.update(jid, status="done", preview_error=preview_error)
    except Exception as exc:
        logger.exception("Job %s failed", jid)
        jobs.update(jid, status="failed", error=f"{type(exc).__name__}: {exc}")


def _public(job: dict) -> dict:
    out = {k: v for k, v in job.items() if k != "folder"}
    files = []
    if job.get("folder"):
        root = Path(job["folder"]).parent
        files = sorted(str(p.relative_to(root)).replace(os.sep, "/") for p in Path(job["folder"]).rglob("*") if p.is_file())
    out["files"] = files
    return out


def _safe_file(job: dict, rel: str) -> Path:
    if not job.get("folder"):
        raise HTTPException(409, "Job has no files yet")
    root = Path(job["folder"]).parent.resolve()
    target = (root / rel).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(404, "File not found")
    return target


# ----------------------------------------------------------------------------- app
def create_app() -> FastAPI:
    api_key = os.environ.get("GEEDOWNLOAD_API_KEY")
    jobs = Jobs()

    def require_key(x_api_key: Optional[str] = Header(None)):
        if api_key and not (x_api_key and hmac.compare_digest(x_api_key, api_key)):
            raise HTTPException(401, "Missing or invalid X-API-Key header")

    app = FastAPI(
        title="geedownload API",
        version=__version__,
        summary="Search areas, get boundary shapefiles, download Earth Engine satellite data and render maps.",
        description=(
            "Search any area by name, save its boundary as a shapefile, download Sentinel / Landsat / MODIS / DEM "
            "imagery from Google Earth Engine, and render cartopy maps (JPG).\n\n"
            f"Author: **{AUTHOR['name']}** - {AUTHOR['affiliation']} - {AUTHOR['email']}"),
        contact={"name": AUTHOR["name"], "email": AUTHOR["email"], "url": AUTHOR["github"]},
        license_info={"name": "MIT"},
    )
    origins = [o.strip() for o in os.environ.get("GEEDOWNLOAD_CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    guard = [Depends(require_key)]

    # --- public
    @app.get("/", summary="API information", tags=["info"])
    def root():
        return {"name": "geedownload", "version": __version__, "docs": "/docs", "logo": "/logo.png", "gui": "/app",
                "author": AUTHOR, "auth_required": bool(api_key)}

    @app.get("/app", summary="Web interface (Arabic / Persian / English)", tags=["info"], include_in_schema=False)
    def gui():
        import json

        gui_dir = ASSETS / "gui"
        i18n = (gui_dir / "i18n.json").read_text(encoding="utf-8")
        html = (gui_dir / "index.html").read_text(encoding="utf-8")
        # JSON is embedded in a <script>: make "</" safe
        html = html.replace("/*I18N_JSON*/{}", json.dumps(json.loads(i18n), ensure_ascii=False).replace("</", "<\\/"))
        return HTMLResponse(html)

    @app.get("/health", summary="Health check", tags=["info"])
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/logo.png", summary="Package logo", tags=["info"])
    def logo():
        return FileResponse(ASSETS / "logo.png", media_type="image/png")

    # --- discovery
    @app.get("/datasets", summary="List built-in datasets", tags=["catalogue"], dependencies=guard)
    def datasets():
        return [{"key": d.key, "title": d.title, "collection_id": d.collection_id, "scale_m": d.scale,
                 "cloud_property": d.cloud_property, "default_bands": list(d.default_bands or []),
                 "band_groups": {k: list(v) for k, v in d.band_groups.items()}, "reducer": d.reducer}
                for d in list_datasets()]

    @app.get("/search", summary="Search an area by name", tags=["area"], dependencies=guard)
    def search(q: str = Query(..., min_length=2), limit: int = Query(5, ge=1, le=20),
               country_codes: Optional[str] = None, feature_type: Optional[str] = None,
               include_geometry: bool = False):
        try:
            places = search_area(q, limit=limit, country_codes=country_codes, feature_type=feature_type)
        except AreaNotFound as exc:
            raise HTTPException(404, str(exc))
        except GeeDownloadError as exc:
            raise HTTPException(502, str(exc))
        out = []
        for i, p in enumerate(places):
            item = {"pick": i, "name": p.name, "display_name": p.display_name, "bbox": list(p.bbox),
                    "has_polygon": p.has_polygon, "category": p.category, "type": p.kind, "osm_id": p.osm_id}
            if include_geometry:
                item["geometry"] = mapping(p.polygon)
            out.append(item)
        return out

    @app.get("/boundary", summary="Boundary of an area as a zipped shapefile", tags=["area"], dependencies=guard)
    def boundary(q: str = Query(..., min_length=2), pick: int = Query(0, ge=0)):
        _check_area(q)
        try:
            aoi = resolve_aoi(q, pick=pick)
        except AreaNotFound as exc:
            raise HTTPException(404, str(exc))
        except GeeDownloadError as exc:
            raise HTTPException(400, str(exc))
        folder = _workdir() / "boundaries" / f"{slugify(aoi.name)}_{timestamp()}"
        save_boundary(aoi, folder)
        zpath = zip_dir(folder, folder.with_suffix(".zip"))
        return FileResponse(zpath, media_type="application/zip", filename=f"{slugify(aoi.name)}_boundary.zip")

    # --- jobs
    @app.post("/jobs/download", status_code=202, summary="Start a download job", tags=["jobs"], dependencies=guard)
    def start_download(req: DownloadRequest):
        _check_area(req.area)
        jid = jobs.create(req.model_dump())
        jobs.pool.submit(_run_download, jobs, jid, req)
        return {"job_id": jid, "status": "queued", "status_url": f"/jobs/{jid}"}

    @app.get("/jobs", summary="List jobs", tags=["jobs"], dependencies=guard)
    def list_jobs():
        return [{"job_id": j["job_id"], "status": j["status"], "created": j["created"]} for j in jobs.items.values()]

    @app.get("/jobs/{job_id}", summary="Job status, metadata and file list", tags=["jobs"], dependencies=guard)
    def job_status(job_id: str):
        return _public(jobs.get(job_id))

    @app.get("/jobs/{job_id}/files/{path:path}", summary="Download one output file", tags=["jobs"], dependencies=guard)
    def job_file(job_id: str, path: str):
        return FileResponse(_safe_file(jobs.get(job_id), path))

    @app.get("/jobs/{job_id}/archive.zip", summary="Download the whole job folder", tags=["jobs"], dependencies=guard)
    def job_archive(job_id: str):
        job = jobs.get(job_id)
        if job["status"] != "done":
            raise HTTPException(409, f"Job is {job['status']}")
        folder = Path(job["folder"])
        return FileResponse(zip_dir(folder, folder.with_suffix(".zip")), media_type="application/zip",
                            filename=f"{folder.name}.zip")

    @app.post("/jobs/{job_id}/map", summary="Render a map (JPG) from a finished job", tags=["maps"], dependencies=guard)
    def job_map(job_id: str, req: MapRequest):
        job = jobs.get(job_id)
        if job["status"] != "done":
            raise HTTPException(409, f"Job is {job['status']}")
        from .maps import plot_map, preview_args

        folder, info = Path(job["folder"]), job["info"]
        stack = next(iter(sorted(folder.glob("*_stack.tif"))), None) or next(iter(sorted((folder / "scenes").glob("*.tif"))), None)
        if stack is None:
            raise HTTPException(409, "This job has no stacked GeoTIFF to map (run it with stack=true).")
        args = {"bands": req.bands} if req.bands else preview_args(info)
        if req.classes:
            args["classes"] = req.classes
        args["cmap"] = req.cmap or args.get("cmap", "viridis")
        try:
            out = plot_map(stack, folder / f"map_{uuid.uuid4().hex[:6]}.jpg",
                           area=folder / "boundary" / f"{slugify(info['area'])}.shp",
                           title=req.title or info["area"], country=req.country or info.get("country"),
                           legend_label=req.legend_label, context=req.context, inset=req.inset, dpi=req.dpi,
                           source=f"Data: {info['dataset']} via Google Earth Engine, "
                                  f"{info.get('start') or ''} to {info.get('end') or ''}", **args)
        except GeeDownloadError as exc:
            raise HTTPException(400, str(exc))
        return FileResponse(out, media_type="image/jpeg")

    @app.delete("/jobs/{job_id}", summary="Delete a job and its files", tags=["jobs"], dependencies=guard)
    def delete_job(job_id: str):
        import shutil

        job = jobs.get(job_id)
        if job["status"] in ("queued", "running"):
            raise HTTPException(409, "Job is still running")
        if job.get("folder"):
            shutil.rmtree(Path(job["folder"]).parent, ignore_errors=True)
        with jobs.lock:
            del jobs.items[job_id]
        return JSONResponse({"deleted": job_id})

    @app.post("/maps/area", summary="Outline map of an area / country (JPG), no Earth Engine needed",
              tags=["maps"], dependencies=guard)
    def area_map(req: AreaMapRequest):
        _check_area(req.area)
        from .maps import plot_area

        out = _workdir() / "maps" / f"area_{uuid.uuid4().hex[:8]}.jpg"
        try:
            plot_area(resolve_aoi(req.area, pick=req.pick), out, country=req.country, extent=req.extent,
                      title=req.title, admin1=req.admin1, dpi=req.dpi)
        except AreaNotFound as exc:
            raise HTTPException(404, str(exc))
        except GeeDownloadError as exc:
            raise HTTPException(400, str(exc))
        return FileResponse(out, media_type="image/jpeg")

    return app


app = create_app()
