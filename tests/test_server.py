"""Integration tests against a real uvicorn server (Starlette's TestClient runs every websocket
in its own event loop, which doesn't match production and deadlocks multi-client rooms)."""
import asyncio
import json
import random
import socket
import threading
import time
import urllib.request

import pytest
import uvicorn
import websockets

from server import app as app_module


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    app_module.SNAPSHOT = str(tmp_path_factory.mktemp("state") / "rooms.pkl")  # never the real file
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app_module.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def post(base, path, body):
    req = urllib.request.Request(f"http://{base}{path}", json.dumps(body).encode(), {"content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def get(base, path):
    return json.loads(urllib.request.urlopen(f"http://{base}{path}").read())


def test_full_game_two_humans_and_a_bot(base_url):
    rid = post(base_url, "/api/rooms", {"token": "t1", "name": "Alice",
                                       "seats": [{"kind": "me"}, {"kind": "bot", "bot_id": "smart"}, {"kind": "open"}]})["id"]
    app_module.rooms[rid].pause_scale = 0.0
    rng = random.Random(0)

    async def play():
        async with websockets.connect(f"ws://{base_url}/ws/{rid}?token=t1&name=Alice", max_size=None) as ws1, \
                websockets.connect(f"ws://{base_url}/ws/{rid}?token=t2&name=Bob", max_size=None) as ws2:
            assert json.loads(await ws1.recv())["room"]["host"] is True
            await ws2.send(json.dumps({"type": "take_seat", "seat": 2}))
            await asyncio.sleep(0.2)
            await ws1.send(json.dumps({"type": "start"}))
            seats = {0: ws1, 2: ws2}
            events = set()
            last_seq = -1
            while True:
                msg = json.loads(await asyncio.wait_for(ws1.recv(), 20))
                g = msg.get("game")
                if not g:
                    continue
                events.update(e["t"] for e in g["events"])
                if msg["room"]["mode"] == "finished":
                    while msg["review"] is None:  # the coach reviews the game after it ends
                        msg = json.loads(await asyncio.wait_for(ws1.recv(), 90))
                    return msg, events
                d = g["decision"]
                if d and d["player"] in seats and g["seq"] != last_seq:
                    last_seq = g["seq"]
                    a = rng.choice(d["options"])["a"]
                    await seats[d["player"]].send(json.dumps({"type": "act", "action": a, "seq": g["seq"]}))

    over, events = asyncio.run(asyncio.wait_for(play(), 240))
    assert over["game"]["over"]
    assert max(p["total"] for p in over["game"]["players"]) >= 200
    assert {"round", "draw", "round_end", "game_over"} <= events
    review = over["review"]
    assert review["decisions"] > 0 and review["moments"]
    m = review["moments"][0]
    assert m["loss"] >= 0 and any(o["a"] == m["chosen"] for o in m["options"]) and m["table"]["players"]


def test_stale_action_is_ignored(base_url):
    rid = post(base_url, "/api/rooms", {"token": "s1", "name": "Sam", "autostart": True,
                                       "seats": [{"kind": "me"}, {"kind": "bot", "bot_id": "random"}]})["id"]
    room = app_module.rooms[rid]
    room.pause_scale = 0.0

    async def run():
        async with websockets.connect(f"ws://{base_url}/ws/{rid}?token=s1&name=Sam", max_size=None) as ws:
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 20))
                g = msg.get("game")
                d = g and g["decision"]
                if d and d["player"] == 0:
                    seq = g["seq"]
                    await ws.send(json.dumps({"type": "act", "action": d["options"][0]["a"], "seq": seq - 1}))
                    await asyncio.sleep(0.3)
                    return seq

    seq = asyncio.run(run())
    assert room.seq == seq  # the out-of-date action did nothing


def test_bots_and_rooms_listing(base_url):
    ids = {b["id"] for b in get(base_url, "/api/bots")}
    assert {"smart", "random", "threshold25"} <= ids
    seats = [{"kind": "me"}, {"kind": "open"}]
    listed = post(base_url, "/api/rooms", {"token": "h", "name": "Host", "seats": seats, "public": True})["id"]
    private = post(base_url, "/api/rooms", {"token": "h", "name": "Host", "seats": seats})["id"]
    shown = {r["id"] for r in get(base_url, "/api/rooms")}
    assert listed in shown and private not in shown
    health = get(base_url, "/api/health")
    assert {"rooms", "clients", "bot_ms", "loop_lag_ms"} <= set(health)


def _room(*seats):
    from server.rooms import Room
    r = Room(app_module.registry, "h", {})
    r.pause_scale = 0.0
    r.seats = list(seats)
    return r


def test_back_to_lobby_after_a_finished_game():
    from server.rooms import Seat

    async def run():
        r = _room(Seat("human", "H", token="h"), Seat("bot", "B", "smart"))
        r.mode = "finished"
        await r.handle("h", {"type": "stop"})
        return r.mode

    assert asyncio.run(run()) == "lobby"


def test_absent_player_gets_a_stand_in_bot_and_can_reclaim(monkeypatch):
    from server import rooms as rooms_mod
    from server.rooms import Seat
    monkeypatch.setattr(rooms_mod, "GRACE", 0.0)

    async def run():
        r = _room(Seat("human", "Host", token="h"), Seat("human", "Gone", token="g"))
        r.start()
        r.seats[1].left_at = time.time() - 1  # never connected
        subbed = False
        for _ in range(6000):
            await asyncio.sleep(0.005)
            g = r.game
            if g.over:
                break
            d = g.decision
            if d is None:
                continue
            if d.player == 0:
                r.actions.put_nowait(("h", d.options[-1], r.seq))
            elif not subbed:
                assert not r.can_substitute("g", 1)  # only the host (or a present player) may
                await r.handle("h", {"type": "substitute", "seat": 1, "bot_id": "smart"})
                subbed = True
                assert r.seats[1].sub_bot is not None
        await asyncio.sleep(0.05)
        assert subbed and r.game.over and r.mode == "finished"
        assert any("playing for Gone" in m["text"] for m in r.chat)
        # a fresh game: the absent player comes back and takes the seat back from the bot
        r.start()
        await r.handle("h", {"type": "substitute", "seat": 1, "bot_id": "smart"})
        assert r.seats[1].sub_bot is not None
        await r.handle("g", {"type": "reclaim"})
        assert r.seats[1].sub_bot is None
        r.task.cancel()

    asyncio.run(asyncio.wait_for(run(), 90))


def test_rooms_survive_a_restart(tmp_path):
    from server.rooms import Seat, load_rooms, save_rooms

    async def run():
        r = _room(Seat("human", "H", token="h"), Seat("bot", "B", "smart"))
        r.start()
        for _ in range(400):  # until it's the human's turn
            await asyncio.sleep(0.01)
            if r.game.decision is not None and r.game.decision.player == 0:
                break
        path = str(tmp_path / "rooms.pkl")
        save_rooms({r.id: r}, path)
        r.task.cancel()
        back = load_rooms(path, app_module.registry)[r.id]
        assert back.mode == "playing" and back.game.round == r.game.round and back.seq == r.seq
        assert back.seats[0].left_at is not None  # nobody is connected after a restart
        back.pause_scale = 0.0
        await asyncio.sleep(0.05)
        d = back.game.decision
        assert d.player == 0
        before = back.seq
        back.actions.put_nowait(("h", d.options[-1], back.seq))
        for _ in range(200):
            await asyncio.sleep(0.01)
            if back.seq > before:
                break
        back.task.cancel()
        return back.seq > before

    assert asyncio.run(asyncio.wait_for(run(), 30))


def test_boss_level_is_bossbot_and_plays_legal_moves():
    from flip7.engine import Game
    from flip7.model import Net
    from flip7.search import BossBot
    from server import bots

    reg = bots.Registry.__new__(bots.Registry)
    reg.models = {"flip7_rl": (Net(32, 2), {"title": "Test"})}
    boss = reg.make("search:flip7_rl")
    assert isinstance(boss, BossBot)
    g = Game(3, rng=random.Random(1))
    for _ in range(20):
        if g.over:
            break
        a = boss.act(g)
        assert a in g.legal()
        g.step(a)
