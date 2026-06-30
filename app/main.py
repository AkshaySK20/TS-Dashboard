from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.cache import clear_cache
from app.jira_client import get_dashboard_tiles, get_category_issues
from app.jira_client import (
    get_dashboard_tiles,
    get_category_issues,
    get_category_cache_meta,
    get_current_user,
)

load_dotenv()

app = FastAPI(title="TS Jira Dashboard")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def get_last_refresh_time():
    return datetime.now().strftime("%b %d, %Y %I:%M %p")

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    tiles = get_dashboard_tiles()
    meta = get_category_cache_meta("actionable")
    user = get_current_user()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "tiles": tiles,
            "current_user": user["display_name"],
            "last_sync": meta["last_sync"],
            "next_sync_iso": meta["next_sync_iso"],
        },
    )

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    tiles = get_dashboard_tiles()

    meta = get_category_cache_meta("actionable")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "tiles": tiles,
            "last_sync": meta["last_sync"],
            "next_sync": meta["next_sync"],
            "next_sync_iso": meta["next_sync_iso"],
        },
    )


@app.get("/category/{category_key}", response_class=HTMLResponse)
def category_detail(request: Request, category_key: str):
    category, issues = get_category_issues(category_key)

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    meta = get_category_cache_meta(category_key)

    return templates.TemplateResponse(
        "category.html",
        {
            "request": request,
            "category": category,
            "issues": issues,
            "count": len(issues),
            "last_sync": meta["last_sync"],
            "next_sync": meta["next_sync"],
            "next_sync_iso": meta["next_sync_iso"],
        },
    )


@app.get("/refresh")
def refresh_cache():
    clear_cache()
    return RedirectResponse(url="/")


@app.get("/health")
def health():
    return {"status": "ok"}