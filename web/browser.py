"""The server's game rooms (``server/rooms.py``) running inside the browser, for the static build.

``web/worker.js`` runs this module under Pyodide in a Web Worker and relays what the page would
otherwise send to the server: ``create_room`` for POST /api/rooms, and ``connect`` / ``receive`` /
``disconnect`` for a room's WebSocket. The rooms, bots and engine are the server's own code; only
the transport differs. Bot moves run inline because there are no threads here (the post-game review
goes one decision at a time), and a room is closed as soon as its page leaves, since nobody else can
reach it.
"""
from __future__ import annotations

import json

from server import rooms as R
from server.bots import Registry

R.COMPUTE = None
R.COACH_PLAYOUTS = 24  # the post-game review shares the worker with the next game; keep it light


class Socket:
    """Stands in for a WebSocket: what the room sends goes to ``post(sid, text)``, ``None`` closes."""

    def __init__(self, sid, post):
        self.sid, self.post = sid, post

    async def send_text(self, text):
        self.post(self.sid, text)

    async def close(self):
        self.post(self.sid, None)


class Host:
    def __init__(self, models_dir, post):
        self.registry = Registry(models_dir)
        self.post = post
        self.rooms = {}
        self.sockets = {}  # sid -> (room, Socket, token)

    async def create_room(self, spec):
        return json.dumps({"id": R.create_room(self.registry, self.rooms, json.loads(spec)).id})

    async def connect(self, sid, room_id, token, name):
        ws = Socket(sid, self.post)
        room = self.rooms.get(room_id.upper())
        if room is None:
            await ws.send_text(json.dumps({"type": "error", "message": "Room not found"}))
            await ws.close()
            return
        self.sockets[sid] = (room, ws, token)
        room.connect(ws, token)
        room.names.setdefault(token, name[:20] or "Player")
        await room.send_full(ws, token)

    async def receive(self, sid, text):
        if sid not in self.sockets:
            return
        room, ws, token = self.sockets[sid]
        try:
            await room.handle(token, json.loads(text))
        except (KeyError, ValueError, TypeError) as e:
            if ws in room.clients:
                room.clients[ws].push(json.dumps({"type": "error", "message": f"bad message: {e}"}))

    async def disconnect(self, sid):
        if sid not in self.sockets:
            return
        room, ws, _ = self.sockets.pop(sid)
        room.disconnect(ws)
        if not room.clients:
            for task in (room.task, room.coach_task):
                if task:
                    task.cancel()
            self.rooms.pop(room.id, None)
