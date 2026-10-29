"""Game rooms: seats (humans/bots), the game driver loop and client state.

Robustness:
* Each connection has its own send queue (``Client``); a slow or stuck client can't hold up the
  room, and one that falls far behind gets a full resync instead of every missed message.
* Bot moves and the analyst network run in a small thread pool, so a slow search in one room
  doesn't freeze every other room. A result is applied only if the game and decision are still
  the ones it was computed for.
* A human who disconnects keeps their seat. After ``GRACE`` seconds the host (or, if the host is
  away too, any seated player) may let a bot play for them; they can take the seat back when they
  return. Rooms are snapshotted to disk, so a server restart doesn't lose games.
"""
from __future__ import annotations

import asyncio
import json
import os
import pickle
import random
import secrets
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from flip7 import coach
from flip7.engine import (A_CARD0, A_PLAYER0, BUSTED, D_SWAP2, DECISION_NAMES, T_FLIP4, T_JOM_STAY,
                          T_QUEUE, Game, Rules, decode_card)
from flip7.features import draw_stats, next_card_pool
from flip7.search import SearchBot

BOT_NAMES = ["Ada", "Turing", "Hopper", "Lovelace", "Knuth", "Shannon", "Dijkstra", "Noether",
             "Gauss", "Euler", "Curie", "Hypatia"]
MAX_SEATS = 6
GRACE = float(os.environ.get("SEAT_GRACE", 30))  # seconds a disconnected player's seat is held before a bot may take over
SEND_TIMEOUT = 10.0   # a client that can't take a message in this long is dropped
QUEUE_LIMIT = 64      # messages a client may fall behind before it gets a full resync instead

COMPUTE = ThreadPoolExecutor(max_workers=2, thread_name_prefix="flip7-bots")  # None: run inline (the browser build has no threads)
COACH_PLAYOUTS = 64   # deck orders per reviewed decision in the post-game review


class Stats:
    """Rolling latency figures for /api/health."""

    def __init__(self, keep=500):
        self.values = deque(maxlen=keep)

    def add(self, ms):
        self.values.append(ms)

    def summary(self):
        v = sorted(self.values)
        if not v:
            return {"n": 0}
        pick = lambda q: round(v[min(len(v) - 1, int(q * len(v)))], 1)
        return {"n": len(v), "p50": pick(0.5), "p95": pick(0.95), "max": round(v[-1], 1)}


STATS = {"bot_ms": Stats(), "analyst_ms": Stats(), "coach_ms": Stats(100), "loop_lag_ms": Stats(240)}


async def compute(kind, fn, *args):
    """Run CPU-heavy work (a bot move, the analyst) off the event loop and time it."""
    t0 = time.perf_counter()
    try:
        if COMPUTE is None:
            return fn(*args)
        return await asyncio.get_running_loop().run_in_executor(COMPUTE, fn, *args)
    finally:
        STATS[kind].add((time.perf_counter() - t0) * 1000)


def new_token():
    return secrets.token_urlsafe(12)


def room_code():
    return "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(5))


class Seat:
    def __init__(self, kind="open", name="", bot_id=None, token=None):
        self.kind = kind          # "human" | "bot" | "open"
        self.name = name
        self.bot_id = bot_id
        self.token = token
        self.bot = None
        self.sub_id = None        # bot playing for a human who disconnected
        self.sub_bot = None
        self.left_at = None       # when the human lost their connection

    def public(self, registry, online):
        away = None
        if self.kind == "human" and not online:
            away = round(time.time() - self.left_at, 1) if self.left_at else 0.0
        return {"kind": self.kind, "name": self.name, "bot_id": self.bot_id,
                "bot_name": registry.name(self.bot_id) if self.bot_id else None,
                "online": self.kind != "human" or online, "away": away,
                "sub": registry.name(self.sub_id) if self.sub_id else None}


class Client:
    """One connection with its own send queue."""

    def __init__(self, room, ws, token):
        self.room, self.ws, self.token = room, ws, token
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self.resync = False
        self.task = asyncio.create_task(self._writer())

    def push(self, text):
        if self.resync:
            return
        try:
            self.queue.put_nowait(text)
        except asyncio.QueueFull:  # too far behind: drop the backlog, send one full state instead
            self.resync = True
            while not self.queue.empty():
                self.queue.get_nowait()
            self.queue.put_nowait(None)

    async def _writer(self):
        try:
            while True:
                text = await self.queue.get()
                if text is None:
                    self.resync = False
                    text = json.dumps(self.room.full_state(self.token))
                await asyncio.wait_for(self.ws.send_text(text), timeout=SEND_TIMEOUT)
        except asyncio.CancelledError:
            return  # disconnected; ending quietly keeps Pyodide's event loop from logging the cancel
        except Exception:
            self.room.disconnect(self.ws)
            try:
                await self.ws.close()
            except Exception:
                pass


class Room:
    def __init__(self, registry, host_token, settings):
        self.id = room_code()
        self.registry = registry
        self.host_token = host_token
        self.settings = {"brutal": True, "target": 200, "coach": False, "watch": False, "public": False}
        self.settings.update(settings or {})
        self.seats: list[Seat] = []
        self.mode = "lobby"
        self.game: Game | None = None
        self.clients: dict = {}    # websocket -> Client
        self.names = {}            # token -> display name
        self.speed = 1.0           # seconds per bot move
        self.pause_scale = 1.0     # multiplies every pause (tests set it to 0)
        self.paused = False
        self.wake = asyncio.Event()
        self.actions: asyncio.Queue = asyncio.Queue()
        self.task: asyncio.Task | None = None
        self.event_cursor = 0
        self.seq = 0               # decision counter: stale/duplicate clicks are ignored
        self.history = []          # every event of the current game
        self.thoughts = None
        self.review = []           # human decisions: position snapshot, choice, the analyst's view
        self.coach = {}            # seat -> post-game review (flip7.coach)
        self.coach_pending = False
        self.coach_task: asyncio.Task | None = None
        self.wins = {}             # name -> wins in this room
        self.games_played = 0
        self.chat = []
        self.touched = time.time()
        self.dirty = True          # changed since the last snapshot

    # ------------------------------------------------------------------ seats & connections
    def add_bot(self, bot_id, name=None):
        used = {s.name for s in self.seats}
        name = name or next((n for n in BOT_NAMES if n not in used), f"Bot {len(self.seats) + 1}")
        self.seats.append(Seat("bot", name, bot_id))

    def seat_of(self, token):
        for i, s in enumerate(self.seats):
            if s.kind == "human" and s.token == token:
                return i
        return -1

    def online_tokens(self):
        return {c.token for c in self.clients.values()}

    def connect(self, ws, token):
        self.clients[ws] = Client(self, ws, token)
        i = self.seat_of(token)
        if i >= 0:
            self.seats[i].left_at = None
        self.touched = time.time()

    def disconnect(self, ws):
        client = self.clients.pop(ws, None)
        if client is None:
            return
        client.task.cancel()
        if client.token not in self.online_tokens():
            i = self.seat_of(client.token)
            if i >= 0:
                self.seats[i].left_at = time.time()
        self.dirty = True

    def can_substitute(self, token, i):
        """Host, or any seated online player while the host is away, once the grace period is over."""
        if self.mode != "playing" or not 0 <= i < len(self.seats):
            return False
        s = self.seats[i]
        online = self.online_tokens()
        if s.kind != "human" or s.token in online or s.sub_bot is not None:
            return False
        if s.left_at is not None and time.time() - s.left_at < GRACE:
            return False
        host_away = self.host_token not in online
        return token == self.host_token or (host_away and token in online and token != s.token
                                            and self.seat_of(token) >= 0)

    # ------------------------------------------------------------------ messages
    async def handle(self, token, msg):
        self.touched = time.time()
        self.dirty = True
        t = msg.get("type")
        host = token == self.host_token
        if t == "act":
            self.actions.put_nowait((token, int(msg["action"]), msg.get("seq")))
            return
        if t == "chat":
            text = str(msg.get("text", ""))[:300].strip()
            if text:
                self.chat.append({"name": self.names.get(token, "?"), "seat": self.seat_of(token), "text": text, "t": time.time()})
                self.chat = self.chat[-60:]
        elif t == "take_seat" and self.mode != "playing":
            i = int(msg["seat"])
            if 0 <= i < len(self.seats) and self.seats[i].kind == "open" and self.seat_of(token) < 0:
                self.seats[i] = Seat("human", self.names.get(token, "Player"), token=token)
        elif t == "leave_seat" and self.mode != "playing":
            i = self.seat_of(token)
            if i >= 0:
                self.seats[i] = Seat("open")
        elif t == "rename":
            name = str(msg.get("name", "")).strip()[:20] or "Player"
            self.names[token] = name
            i = self.seat_of(token)
            if i >= 0:
                self.seats[i].name = name
        elif t == "substitute":
            i = int(msg["seat"])
            if self.can_substitute(token, i):
                s = self.seats[i]
                s.sub_id = msg.get("bot_id") or self.registry.default_id()
                s.sub_bot = self.registry.make(s.sub_id)
                self.chat.append({"name": "Server", "text": f"A bot is playing for {s.name} until they're back.", "t": time.time()})
                self.actions.put_nowait((None, None, None))  # wake the driver if it waits for this seat
        elif t == "reclaim":
            i = self.seat_of(token)
            if i >= 0 and self.seats[i].sub_bot is not None:
                self.seats[i].sub_id = self.seats[i].sub_bot = None
                self.actions.put_nowait((None, None, None))
        elif host and t == "set_seat" and self.mode != "playing":
            i = int(msg["seat"])
            kind = msg.get("kind")
            if 0 <= i < len(self.seats):
                if kind == "open":
                    self.seats[i] = Seat("open")
                elif kind == "bot":
                    bot_id = msg.get("bot_id") or self.registry.default_id()
                    used = {s.name for j, s in enumerate(self.seats) if j != i}
                    name = next((n for n in BOT_NAMES if n not in used), f"Bot {i + 1}")
                    self.seats[i] = Seat("bot", name, bot_id)
                elif kind == "remove" and len(self.seats) > 2:
                    self.seats.pop(i)
        elif host and t == "add_seat" and self.mode != "playing" and len(self.seats) < MAX_SEATS:
            if msg.get("kind") == "bot":
                self.add_bot(msg.get("bot_id") or self.registry.default_id())
            else:
                self.seats.append(Seat("open"))
        elif host and t == "settings":
            for k in ("brutal", "coach", "public"):
                if k in msg:
                    self.settings[k] = bool(msg[k])
            if "target" in msg and self.mode != "playing":
                self.settings["target"] = max(50, min(500, int(msg["target"])))
        elif host and t == "start" and self.mode != "playing":
            if 2 <= len(self.seats) <= MAX_SEATS and all(s.kind != "open" for s in self.seats):
                self.start()
        elif t == "speed" and (host or self.settings["watch"]):
            self.speed = max(0.05, min(5.0, float(msg["value"])))
            self.wake.set()
        elif t == "pause" and (host or self.settings["watch"]):
            self.paused = bool(msg.get("value", True))
            self.wake.set()
        elif t == "step" and (host or self.settings["watch"]):
            self.wake.set()
        elif host and t == "stop" and self.mode in ("playing", "finished"):
            if self.task:
                self.task.cancel()
            self.mode = "lobby"
            for s in self.seats:
                s.sub_id = s.sub_bot = None
        await self.broadcast()

    # ------------------------------------------------------------------ game loop
    def start(self):
        for s in self.seats:
            s.sub_id = s.sub_bot = None
            if s.kind == "bot":
                s.bot = self.registry.make(s.bot_id)
        rules = Rules(brutal=self.settings["brutal"], target=self.settings["target"])
        n = len(self.seats)
        self.game = Game(n, seed=random.randrange(1 << 30), rules=rules, dealer=random.randrange(n),
                         log=True)
        self.game.hold_round_end = True  # show each round's final table before it is scored
        self.game.hold_draws = True      # and deal Flip Four cards one at a time
        self.mode = "playing"
        self.event_cursor = 0
        self.seq = 0
        self.history = []
        self.review = []
        self.coach, self.coach_pending = {}, False
        if self.coach_task:
            self.coach_task.cancel()
        self.dirty = True
        self._run_driver()

    def _run_driver(self):
        self.actions = asyncio.Queue()
        self.task = asyncio.create_task(self._drive())

    async def _sleep(self, seconds):
        """Wait, but wake up early on pause/speed/step changes (watch mode)."""
        seconds *= self.pause_scale
        end = time.time() + seconds
        while True:
            if self.paused:
                self.wake.clear()
                await self.wake.wait()
                if self.paused:  # a "step" while paused
                    return
                continue
            left = end - time.time()
            if left <= 0:
                return
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=left)
            except asyncio.TimeoutError:
                return

    async def _human_action(self, seat, d):
        """Wait for the seat's player to act. None if a substitute bot should play instead."""
        g = self.game
        while True:
            if seat.sub_bot is not None:
                return None
            token, a, seq = await self.actions.get()
            if token is None:  # wake-up: a bot took over or the player reclaimed the seat
                continue
            if (self.seat_of(token) == self.seats.index(seat) and g.decision is d and a in d.options
                    and (seq is None or seq == self.seq)):
                return a

    async def _drive(self):
        g = self.game
        try:
            while g.holding:  # restored from a snapshot taken during a pause
                g.resume()
            await self._think()
            await self.broadcast()
            while not g.over:
                d = g.decision
                seat = self.seats[d.player]
                a = None
                if seat.kind == "human":
                    snap = g.clone(random.Random(0)) if len(d.options) > 1 else None
                    a = await self._human_action(seat, d)
                    if a is not None and snap is not None:
                        self.review.append({"seat": d.player, "round": g.round, "chosen": a, "game": snap})
                if a is None:  # a bot's move, or a bot standing in for an absent player
                    bot = seat.bot if seat.kind == "bot" else seat.sub_bot
                    pause = self._sleep(self.speed * (0.6 if DECISION_NAMES[d.kind] == "hit_stay" else 1.0))
                    a, _ = await asyncio.gather(compute("bot_ms", bot.act, g), pause)  # think during the pause
                    if self.game is not g or g.decision is not d or a not in d.options:
                        continue  # the table changed while the bot was thinking
                round_before = g.round
                seg = len(g.events)  # events since the last broadcast
                g.step(a)
                self.seq += 1
                self.dirty = True
                humans = any(s.kind == "human" for s in self.seats)
                while g.holding:  # a Flip Four card, or the final table of a round
                    drama = any(e["t"] in ("bust", "flip7") for e in g.events[seg:])  # the client plays a ~3 s reveal
                    seg = len(g.events)
                    await self.broadcast()
                    if g.holding == "round_end":
                        await self._sleep((3.2 if drama else 2.0) if humans else min(1.6, max(0.2, 1.6 * self.speed)))
                    else:
                        await self._sleep((2.8 if drama else 0.9) if humans else min(0.9, max(0.1, 0.9 * self.speed)))
                    g.resume()
                busts = [e["p"] for e in g.events[seg:] if e["t"] == "bust"]
                await self._think()
                await self.broadcast()
                if g.round != round_before or g.over:
                    await self._sleep(2.8 if humans else min(3.0, max(0.3, 3.0 * self.speed)))
                elif busts and humans:  # let people watch the bust play out before the bots carry on
                    await self._sleep(2.6 if any(self.seats[p].kind == "human" for p in busts) else 1.8)
            self.mode = "finished"
            self.games_played += 1
            for w in g.winners:
                name = self.seats[w].name
                self.wins[name] = self.wins.get(name, 0) + 1
            for s in self.seats:
                s.sub_id = s.sub_bot = None
            self.dirty = True
            await self.broadcast()
            self.coach_task = asyncio.create_task(self._run_coach())
        except asyncio.CancelledError:
            pass
        except Exception:
            traceback.print_exc()
            self.mode = "lobby"
            self.chat.append({"name": "Server", "text": "Something went wrong in this game and it was stopped. Sorry! Start a new one from the lobby.", "t": time.time()})
            await self.broadcast()

    async def _run_coach(self):
        """Review every human's decisions once the game is over (see flip7.coach)."""
        analyst = self.registry.analyst()
        by_seat = {}
        for r in self.review:
            by_seat.setdefault(r["seat"], []).append(r)
        if analyst is None or not by_seat:
            return
        names = [s.name for s in self.seats]
        self.coach_pending = True
        await self.broadcast()
        try:
            for seat, decisions in by_seat.items():
                if COMPUTE is None:  # no threads: one decision at a time, so a new game can start meanwhile
                    items = []
                    for item in coach.review_steps(analyst.model, decisions[-60:], names, COACH_PLAYOUTS, seat):
                        items.append(item)
                        await asyncio.sleep(0)
                    self.coach[seat] = coach.summarize([x for x in items if x])
                else:
                    self.coach[seat] = await compute("coach_ms", coach.review, analyst.model, decisions[-60:], names, COACH_PLAYOUTS, seat)
                await self.broadcast()
        except Exception:
            traceback.print_exc()
        finally:
            self.coach_pending = False
            self.dirty = True
            await self.broadcast()

    async def _think(self):
        """Ask the analyst network about the current decision (shown as win odds / coach)."""
        g = self.game
        self.thoughts = None
        if g.over or g.decision is None:
            return
        analyst = self.registry.analyst()
        if analyst is None:
            return
        d = g.decision
        probs, win, _ = await compute("analyst_ms", analyst.evaluate, g)
        q = None
        seat = self.seats[d.player]
        if self.settings["coach"] and seat.kind == "human" and seat.sub_bot is None and len(d.options) > 1:
            # the coach shows each option's win chance from search, not the network's move probabilities
            q = await compute("analyst_ms", SearchBot(analyst.model, seed=self.seq).evaluate, g)
        if self.game is g and g.decision is d:
            self.thoughts = {"player": d.player,
                             "probs": [{"a": a, "p": round(p, 4)} for a, p in probs.items()],
                             "win": [round(w, 4) for w in win],
                             "q": {str(a): round(v, 4) for a, v in q.items()} if q else None}

    # ------------------------------------------------------------------ state
    def game_state(self, consume=True):
        g = self.game
        if g is None:
            return None
        pool = next_card_pool(g)
        pool_size = sum(pool)
        players = []
        for p, pl in enumerate(g.players):
            pb = None
            if pl.status != BUSTED:
                pb = round(draw_stats(pl.line, pool, pool_size)[0], 4)
            players.append({
                "total": pl.total, "status": pl.status, "line": list(pl.line), "dead": list(pl.dead),
                "late_mods": list(pl.late_mods), "projected": g.projected(p), "p_bust": pb,
                "frozen": pl.frozen, "bounty": pl.bounty, "dare": pl.dare, "spite": pl.spite,
            })
        decision = self._decision_dict()
        tasks = []  # pending resolutions, next first (shown on the seats: "Flip Four, 2 to go")
        for task in reversed(g.stack):
            if task[0] == T_FLIP4:
                tasks.append({"t": "flip4", "p": task[1], "left": task[2], "queue": list(task[3])})
            elif task[0] == T_QUEUE:
                tasks.append({"t": "queue", "p": task[1], "queue": list(task[2])})
            elif task[0] == T_JOM_STAY:
                tasks.append({"t": "jom", "p": task[1]})
        new = []
        if consume:
            new = g.events[self.event_cursor:]
            self.event_cursor = len(g.events)
            self.history.extend(new)
        return {
            "round": g.round, "dealer": g.dealer, "n": g.n, "over": g.over, "winners": list(g.winners),
            "deck_size": len(g.deck), "discard_size": len(g.discard), "discard_top": g.discard[-1] if g.discard else None,
            "deck_counts": g.deck_counts(), "players": players, "decision": decision, "tasks": tasks,
            "last_round_scores": g.last_round_scores, "flip7_player": g.flip7_player, "seq": self.seq,
            "holding": g.holding,
            "events": new,
        }

    def _decision_dict(self):
        g = self.game
        d = g.decision
        if d is None or g.over:
            return None
        opts = []
        for a in d.options:
            if a < A_PLAYER0:
                opts.append({"a": a})
            elif a < A_CARD0:
                opts.append({"a": a, "player": a - A_PLAYER0})
            else:
                q, c = decode_card(a)
                opts.append({"a": a, "player": q, "card": c})
        decision = {"player": d.player, "kind": DECISION_NAMES[d.kind], "card": d.card, "options": opts, "by": d.by}
        if d.kind == D_SWAP2:
            q, c = decode_card(d.first)
            decision["first"] = {"player": q, "card": c}
        return decision

    def state_for(self, token, gs):
        online = self.online_tokens()
        thoughts = None
        if self.thoughts and (self.settings["coach"] or self.settings["watch"] or self.mode == "finished"):
            thoughts = self.thoughts
        elif self.thoughts and self.seat_of(token) < 0:
            thoughts = self.thoughts  # spectators may peek
        me = self.seat_of(token)
        return {
            "type": "state",
            "room": {
                "id": self.id, "mode": self.mode, "settings": dict(self.settings),
                "seats": [s.public(self.registry, s.token in online) for s in self.seats],
                "host": token == self.host_token, "you": me,
                "name": self.names.get(token, ""), "speed": self.speed, "paused": self.paused,
                "spectators": sum(1 for t in online if self.seat_of(t) < 0),
                "wins": dict(self.wins), "games_played": self.games_played, "chat": self.chat[-30:],
                "grace": GRACE, "can_sub": [i for i in range(len(self.seats)) if self.can_substitute(token, i)],
            },
            "game": gs,
            "thoughts": thoughts,
            "review": self.coach.get(me) if self.mode == "finished" else None,
            "review_pending": self.coach_pending and me >= 0 and me not in self.coach,
        }

    def full_state(self, token):
        """State for a client that just (re)connected or fell behind, including the event history."""
        gs = self.game_state(consume=False)
        if gs is not None:
            gs = {**gs, "events": self.history[-300:], "replayed": True}
        return self.state_for(token, gs)

    async def broadcast(self):
        """Queue the new state for every client (never waits on a slow one)."""
        gs = self.game_state()
        for client in list(self.clients.values()):
            client.push(json.dumps(self.state_for(client.token, gs)))

    async def send_full(self, ws, token):
        self.clients[ws].push(json.dumps(self.full_state(token)))
        # the others need to see the online indicator change
        quiet = self.game_state(consume=False)
        for other, client in list(self.clients.items()):
            if other is not ws:
                client.push(json.dumps(self.state_for(client.token, quiet)))

    # ------------------------------------------------------------------ snapshots
    def snapshot(self):
        return {
            "id": self.id, "host_token": self.host_token, "settings": dict(self.settings),
            "seats": [(s.kind, s.name, s.bot_id, s.token, s.sub_id, s.left_at) for s in self.seats],
            "mode": self.mode, "game": self.game, "names": dict(self.names), "speed": self.speed,
            "event_cursor": self.event_cursor, "seq": self.seq, "history": self.history[-400:],
            "review": self.review, "coach": self.coach, "wins": dict(self.wins), "games_played": self.games_played,
            "chat": self.chat[-60:], "touched": self.touched,
        }

    @classmethod
    def restore(cls, snap, registry):
        r = cls(registry, snap["host_token"], snap["settings"])
        r.id = snap["id"]
        for kind, name, bot_id, token, sub_id, left_at in snap["seats"]:
            s = Seat(kind, name, bot_id, token)
            s.left_at = left_at if kind != "human" else (left_at or time.time())  # nobody is connected yet
            if kind == "bot":
                s.bot = registry.make(bot_id)
            if sub_id:
                s.sub_id, s.sub_bot = sub_id, registry.make(sub_id)
            r.seats.append(s)
        for k in ("mode", "game", "names", "speed", "event_cursor", "seq", "history", "review", "wins",
                  "games_played", "chat", "touched"):
            setattr(r, k, snap[k])
        r.coach = snap.get("coach", {})
        if r.mode == "playing" and r.game is not None:
            r._run_driver()
        return r


def create_room(registry, rooms, spec):
    """A room from a lobby request (``spec``: the POST /api/rooms body as a dict), added to ``rooms``."""
    seats = spec.get("seats") or []
    if not 2 <= len(seats) <= MAX_SEATS:
        raise ValueError("2 to 6 seats")
    token = spec["token"]
    room = Room(registry, token, {k: spec[k] for k in ("brutal", "target", "coach", "watch", "public") if k in spec})
    while room.id in rooms:
        room.id = room.id[:-1] + room.id[0]
    room.names[token] = str(spec.get("name") or "Player")[:20]
    for s in seats:
        if s.get("kind") == "me" and room.seat_of(token) < 0:
            room.seats.append(Seat("human", room.names[token], token=token))
        elif s.get("kind") == "bot":
            room.add_bot(s.get("bot_id") or registry.default_id())
        else:
            room.seats.append(Seat("open"))
    room.speed = max(0.05, min(5.0, float(spec.get("speed", 1.0))))
    rooms[room.id] = room
    if spec.get("autostart") and all(s.kind != "open" for s in room.seats):
        room.start()
    return room


def save_rooms(rooms, path):
    """Write every room's snapshot atomically."""
    data = {rid: r.snapshot() for rid, r in rooms.items()}
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(data, f)
    os.replace(tmp, path)
    for r in rooms.values():
        r.dirty = False


def load_rooms(path, registry, max_idle=3600):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
    except Exception:
        traceback.print_exc()
        return {}
    out = {}
    now = time.time()
    for rid, snap in data.items():
        if now - snap["touched"] > max_idle:
            continue
        try:
            out[rid] = Room.restore(snap, registry)
        except Exception:
            traceback.print_exc()
    return out
