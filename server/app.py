"""Bust or Bank, the web app: play the bots, with friends, or watch them.

    .venv/bin/uvicorn server.app:app --host 0.0.0.0 --port 8077
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import torch

from . import insights as insights_data
from .bots import ROOT, Registry
from .rooms import COMPUTE, STATS, Room, create_room as new_room, load_rooms, save_rooms

torch.set_num_threads(2)  # bot inference shares the machine; keep it to a couple of cores

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ANALYSIS = os.path.join(ROOT, "analysis")
SNAPSHOT = os.environ.get("ROOMS_FILE", os.path.join(ROOT, "runs", "rooms.pkl"))

registry = Registry()
rooms: dict[str, Room] = {}


async def _janitor():
    """Close rooms nobody has touched for an hour."""
    while True:
        await asyncio.sleep(600)
        now = time.time()
        for rid, r in list(rooms.items()):
            if not r.clients and now - r.touched > 3600:
                if r.task:
                    r.task.cancel()
                rooms.pop(rid, None)


def _save():
    if SNAPSHOT:
        try:
            save_rooms(rooms, SNAPSHOT)
        except Exception as e:  # a failed snapshot must not take a game down
            print(f"could not save rooms: {e}")


async def _saver():
    """Snapshot rooms to disk a few seconds after they change, so a restart doesn't lose games."""
    while True:
        await asyncio.sleep(3)
        if any(r.dirty for r in rooms.values()):
            _save()


async def _lag_monitor():
    """How late the event loop wakes up: a measure of how responsive the server is."""
    while True:
        t0 = time.perf_counter()
        await asyncio.sleep(0.5)
        STATS["loop_lag_ms"].add((time.perf_counter() - t0 - 0.5) * 1000)


@asynccontextmanager
async def lifespan(_app):
    rooms.update(load_rooms(SNAPSHOT, registry))
    tasks = [asyncio.create_task(f()) for f in (_janitor, _saver, _lag_monitor)]
    yield
    for t in tasks:
        t.cancel()
    _save()


app = FastAPI(title="Bust or Bank", lifespan=lifespan)


@app.middleware("http")
async def revalidate_assets(request, call_next):
    # Browsers must re-check the page and its assets, so a normal refresh picks up UI changes
    # (unchanged files still come back as cheap 304s).
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


class SeatSpec(BaseModel):
    kind: str = "open"           # "me" | "open" | "bot"
    bot_id: str | None = None


class RoomSpec(BaseModel):
    token: str
    name: str = "Player"
    seats: list[SeatSpec]
    brutal: bool = True
    target: int = 200
    coach: bool = False
    watch: bool = False
    autostart: bool = False
    speed: float = 1.0
    public: bool = False         # listed on the home page for others on the network


@app.get("/api/bots")
def bots():
    return registry.catalog()


@app.get("/api/info")
def info():
    """The machine's LAN address, so the lobby can show a link that works for friends on the Wi-Fi."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent; this just picks the outgoing interface
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return {"lan": [ip for ip in ips if not ip.startswith("127.")]}


@app.post("/api/rooms")
async def create_room(spec: RoomSpec):
    try:
        room = new_room(registry, rooms, spec.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": room.id}


@app.get("/api/rooms")
def list_rooms():
    """Joinable rooms whose host chose to list them. Private rooms are only reachable by code."""
    out = []
    for r in rooms.values():
        if r.settings["watch"] or not r.settings.get("public"):
            continue
        open_seats = sum(1 for s in r.seats if s.kind == "open")
        humans = [s.name for s in r.seats if s.kind == "human"]
        if r.mode != "playing" and open_seats and humans:
            out.append({"id": r.id, "host": humans[0], "seats": len(r.seats), "open": open_seats})
    return out


@app.get("/api/health")
def health():
    playing = sum(1 for r in rooms.values() if r.mode == "playing")
    return {"rooms": len(rooms), "playing": playing, "clients": sum(len(r.clients) for r in rooms.values()),
            "compute_queue": COMPUTE._work_queue.qsize(), **{k: v.summary() for k, v in STATS.items()}}


@app.get("/api/insights")
def insights():
    return JSONResponse(insights_data.load(ANALYSIS))


@app.post("/api/reload-bots")
def reload_bots():
    registry.reload()
    return registry.catalog()


@app.websocket("/ws/{room_id}")
async def ws_room(ws: WebSocket, room_id: str, token: str, name: str = "Player"):
    await ws.accept()
    room = rooms.get(room_id.upper())
    if room is None:
        await ws.send_json({"type": "error", "message": "Room not found"})
        await ws.close()
        return
    room.connect(ws, token)
    room.names.setdefault(token, name[:20] or "Player")
    await room.send_full(ws, token)
    try:
        while True:
            msg = await ws.receive_json()
            try:
                await room.handle(token, msg)
            except (KeyError, ValueError, TypeError) as e:
                if ws in room.clients:
                    room.clients[ws].push(json.dumps({"type": "error", "message": f"bad message: {e}"}))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        room.disconnect(ws)
        await room.broadcast()


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
