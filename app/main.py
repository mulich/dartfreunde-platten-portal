import asyncio
import base64
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field
from app.invitations import AutoAcceptor

DATA = Path(os.getenv("DATA_DIR", "data"))
DATA.mkdir(parents=True, exist_ok=True)
STATIC = Path(__file__).parent / "static"
AUTODARTS = "https://play.autodarts.com/"


class Registry:
    def __init__(self, path):
        self.path = path
        self.items = json.loads(path.read_text()) if path.exists() else []

    def save(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.items, ensure_ascii=False))
        temp.replace(self.path)

    def get(self, ident):
        return next((item for item in self.items if item["id"] == ident), None)


registry = Registry(DATA / "players.json")
contexts = {}
locks = {}
starting = set()
errors = {}
playwright = None
SETTINGS_FILE = DATA / 'automation.json'
automation_settings = json.loads(SETTINGS_FILE.read_text()) if SETTINGS_FILE.exists() else {'hosts': ['rot', 'schwarz', 'blau']}
acceptor = None


def player_profile(item):
    # Keep obsolete desktop profiles intact; Chromium must not downgrade them.
    suffix = '-autodarts' if item.get('browser') == 'chrome' else ''
    return DATA / 'profiles' / (item['id'] + suffix)


def player_lock(ident):
    return locks.setdefault(ident, asyncio.Lock())


async def start_player(ident):
    async with player_lock(ident):
        if ident in contexts:
            return
        if not registry.get(ident):
            raise HTTPException(404, "Spieler nicht gefunden")
        starting.add(ident)
        try:
            context = await playwright.chromium.launch_persistent_context(
                str(player_profile(registry.get(ident))), headless=True,
                viewport={"width": 1280, "height": 800}, locale="de-DE",
                args=["--disable-background-timer-throttling",
                      "--disable-renderer-backgrounding",
                      "--disable-backgrounding-occluded-windows"],
            )
            contexts[ident] = context
            page = context.pages[-1] if context.pages else await context.new_page()
            await page.goto(AUTODARTS, wait_until="domcontentloaded", timeout=60000)
            errors.pop(ident, None)
        except Exception:
            context = contexts.pop(ident, None)
            if context:
                await context.close()
            errors[ident] = "Sitzung konnte nicht gestartet werden. Serververbindung und Browserinstallation prüfen."
            raise
        finally:
            starting.discard(ident)


async def restore():
    # Sequential startup avoids a burst of Chromium processes on small hosts.
    for item in list(registry.items):
        try:
            await start_player(item["id"])
        except Exception:
            logging.warning("Sitzung %s konnte nicht wiederhergestellt werden", item["id"])


@asynccontextmanager
async def lifespan(app):
    global playwright, acceptor
    playwright = await async_playwright().start()
    acceptor = AutoAcceptor(contexts, registry, locks, automation_settings)
    task = asyncio.create_task(restore())
    automation_task = asyncio.create_task(acceptor.run())
    yield
    task.cancel()
    automation_task.cancel()
    await asyncio.gather(task, automation_task, return_exceptions=True)
    await asyncio.gather(*(c.close() for c in contexts.values()), return_exceptions=True)
    await playwright.stop()


app = FastAPI(lifespan=lifespan)


def same_origin(origin, host):
    return bool(origin and urlsplit(origin).netloc == host)


@app.middleware("http")
async def guard(request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not same_origin(request.headers.get("origin"), request.headers.get("host")):
            return HTMLResponse("Ungültiger Ursprung", status_code=403)
    return await call_next(request)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/login")
async def legacy_login():
    return RedirectResponse("/", status_code=303)


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


class Player(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@app.get("/api/players")
async def list_players():
    return [{**p, "status": "starting" if p["id"] in starting else
             "running" if p["id"] in contexts else "stopped",
             "auto_accept": p.get('auto_accept', False),
             "automation": acceptor.status.get(p['id'], {}) if acceptor else {},
             "error": errors.get(p["id"])} for p in registry.items]


class AutomationSettings(BaseModel):
    hosts: list[str] = Field(max_length=20)


class AutoAcceptSetting(BaseModel):
    enabled: bool


@app.get('/api/automation')
async def get_automation():
    return automation_settings


@app.put('/api/automation')
async def set_automation(settings: AutomationSettings):
    hosts = list(dict.fromkeys(name.strip() for name in settings.hosts if name.strip()))
    if any(len(name) > 100 for name in hosts):
        raise HTTPException(400, 'Accountname ist zu lang')
    automation_settings['hosts'] = hosts
    temp = (DATA / 'automation.json').with_suffix('.tmp')
    temp.write_text(json.dumps(automation_settings, ensure_ascii=False))
    temp.replace(DATA / 'automation.json')
    return automation_settings


@app.put('/api/players/{ident}/auto-accept')
async def set_auto_accept(ident: str, setting: AutoAcceptSetting):
    item = registry.get(ident)
    if not item:
        raise HTTPException(404, 'Spieler nicht gefunden')
    if setting.enabled and not automation_settings.get('hosts'):
        raise HTTPException(400, 'Bitte zuerst Board-Accounts freigeben')
    item['auto_accept'] = setting.enabled
    registry.save()
    if acceptor:
        acceptor.drawer_checked.pop(ident, None)
        # Enabling again explicitly allows retrying an invitation which failed.
        acceptor.attempts = {key: value for key, value in acceptor.attempts.items() if key[0] != ident}
        acceptor.report(ident, 'Wartet auf Lobby-Einladung' if setting.enabled else 'Automatik aus')
    return {'enabled': setting.enabled}


@app.post("/api/players")
async def create_player(player: Player):
    name = player.name.strip()
    if not name:
        raise HTTPException(400, "Bitte einen Namen eingeben")
    if len(registry.items) >= 32:
        raise HTTPException(400, "Maximal 32 Sitzungen")
    item = {"id": str(uuid.uuid4()), "name": name}
    registry.items.append(item)
    registry.save()
    return item


@app.post("/api/players/{ident}/start")
async def start(ident: str):
    try:
        await start_player(ident)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, errors.get(ident, "Browser konnte nicht gestartet werden"))
    return {"ok": True}


@app.post("/api/players/{ident}/stop")
async def stop(ident: str):
    if not registry.get(ident):
        raise HTTPException(404, "Spieler nicht gefunden")
    async with player_lock(ident):
        context = contexts.pop(ident, None)
        if context:
            await context.close()
    return {"ok": True}


@app.delete("/api/players/{ident}")
async def delete(ident: str):
    import shutil
    async with player_lock(ident):
        if not registry.get(ident):
            raise HTTPException(404, "Spieler nicht gefunden")
        context = contexts.pop(ident, None)
        if context:
            await context.close()
        registry.items = [p for p in registry.items if p["id"] != ident]
        registry.save()
        shutil.rmtree(DATA / "profiles" / ident, ignore_errors=True)
        shutil.rmtree(DATA / "profiles" / (ident + "-autodarts"), ignore_errors=True)
        shutil.rmtree(DATA / "profiles" / (ident + "-chromium-backup"), ignore_errors=True)
        errors.pop(ident, None)
    return {"ok": True}


@app.websocket("/ws/{ident}")
async def screen(ws: WebSocket, ident: str):
    if not same_origin(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=1008)
        return
    if ident not in contexts:
        await ws.close(code=1008)
        return
    await ws.accept()

    async def frames():
        try:
            while ident in contexts:
                async with player_lock(ident):
                    context = contexts.get(ident)
                    if not context:
                        break
                    page = context.pages[-1] if context.pages else await context.new_page()
                    screenshot = await page.screenshot(type="jpeg", quality=65, timeout=10000)
                    await ws.send_json({"type": "frame", "image": base64.b64encode(screenshot).decode(), "url": page.url})
                await asyncio.sleep(0.7)
        except Exception:
            pass
        finally:
            try:
                await ws.close()
            except RuntimeError:
                pass

    task = asyncio.create_task(frames())
    try:
        while True:
            message = await ws.receive_json()
            async with player_lock(ident):
                context = contexts.get(ident)
                if not context:
                    break
                page = context.pages[-1] if context.pages else await context.new_page()
                kind = message.get("type")
                if kind == "click":
                    await page.mouse.click(max(0, min(1279, float(message["x"]))), max(0, min(799, float(message["y"]))))
                elif kind == "text":
                    await page.keyboard.insert_text(str(message.get("text", ""))[:10000])
                elif kind == "key":
                    await page.keyboard.press(str(message.get("key", ""))[:80])
                elif kind == "scroll":
                    await page.mouse.move(max(0, min(1279, float(message.get("x", 640)))), max(0, min(799, float(message.get("y", 400)))))
                    await page.mouse.wheel(0, max(-2000, min(2000, float(message.get("dy", 0)))))
                elif kind == "home":
                    await page.goto(AUTODARTS, wait_until="domcontentloaded")
                elif kind == "back":
                    await page.go_back(wait_until="domcontentloaded")
                elif kind == "reload":
                    await page.reload(wait_until="domcontentloaded")
    except Exception:
        pass
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        try:
            await ws.close()
        except RuntimeError:
            pass
