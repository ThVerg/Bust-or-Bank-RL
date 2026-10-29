// Bust or Bank: web client for the game and its bots (plain ES modules, no build step).

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const app = $("#app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x) => `${Math.round(x * 100)}%`;
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const signed = (v) => (v > 0 ? `+${v}` : v < 0 ? `−${-v}` : "0");

// ------------------------------------------------------------------ icons & small parts (SVG sprite in index.html)
const icon = (name, cls = "ico") => `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const TAILS = '<svg class="ribbon__tail ribbon__tail--l" viewBox="0 0 40 40" preserveAspectRatio="none" aria-hidden="true"><path d="M1.5 1.5H38.5V38.5H1.5L12 20Z" vector-effect="non-scaling-stroke"/></svg><svg class="ribbon__tail ribbon__tail--r" viewBox="0 0 40 40" preserveAspectRatio="none" aria-hidden="true"><path d="M1.5 1.5H38.5V38.5H1.5L12 20Z" vector-effect="non-scaling-stroke"/></svg>';
const ribbon = (html, cls = "") => `<div class="ribbon ${cls}">${TAILS}<span class="ribbon__band">${html}</span></div>`;
const BACK_EMBLEM = '<svg class="card__emblem" viewBox="0 0 48 48" aria-hidden="true"><use href="#g-back"/></svg>';
const LOGO = '<span class="brand-logo" role="img" aria-label="Bust or Bank"><span class="brand-logo__word">Bust</span><span class="brand-logo__cards"><span class="brand-logo__card"><i>or</i></span></span><span class="brand-logo__word">Bank</span></span>';

// ------------------------------------------------------------------ cards (mirror of flip7/cards.py)
const U7 = 15, L14 = 16, DIV2 = 22, TAX = 23, SPITE = 24, JOM = 25, FLIP4 = 26, SWAP = 27, STEAL = 28, DISCARD = 29;
const DELIVERY = 30, BOUNTY = 31, DARE = 32, SHAKEDOWN = 33, ROBIN = 34;
const N_NUM = 17, FIRST_MOD = 17, FIRST_KEEPER = 23;
const COUNTS = [1, 1, 2, 3, 4, 5, 6, 6, 8, 9, 10, 11, 12, 13, 13, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 2, 2, 2, 2, 2, 2, 2];
const MOD_TEXT = { 17: "−2", 18: "−4", 19: "−6", 20: "−8", 21: "−10", 22: "÷2" };
const ACTION_NAME = { [JOM]: "Just One More", [FLIP4]: "Flip Four", [SWAP]: "Swap", [STEAL]: "Steal", [DISCARD]: "Discard",
  [DELIVERY]: "Special Delivery", [BOUNTY]: "Bounty", [DARE]: "Double Dare", [SHAKEDOWN]: "Shakedown", [ROBIN]: "Robin Hood",
  [TAX]: "Tax Collector", [SPITE]: "Spite" };
const ACTION_KEY = { [JOM]: "more", [FLIP4]: "flip", [SWAP]: "swap", [STEAL]: "steal", [DISCARD]: "discard", [DELIVERY]: "deliver",
  [BOUNTY]: "bounty", [DARE]: "dare", [SHAKEDOWN]: "shake", [ROBIN]: "robin", [TAX]: "tax", [SPITE]: "spite" };
const ACTION_LABEL = { [JOM]: "Just one more!", [FLIP4]: "Flip four!", [SWAP]: "Swap", [STEAL]: "Steal", [DISCARD]: "Discard",
  [DELIVERY]: "Delivery", [BOUNTY]: "Bounty", [DARE]: "Double dare", [SHAKEDOWN]: "Shakedown", [ROBIN]: "Robin Hood",
  [TAX]: "Tax collector", [SPITE]: "Spite" };
const rank = (c) => (c < 15 ? c : c === U7 ? 7 : c === L14 ? 14 : -1);
const isNum = (c) => c < N_NUM;
const isMod = (c) => c >= FIRST_MOD && c < FIRST_KEEPER;
const numColor = (c) => (c === U7 ? "var(--ice-deep)" : c === L14 ? "var(--clover)" : `var(--n${c})`);
const isLite = (c) => c === 0 || c === 1 || c === 2 || c === 3;

function cardName(c) {
  if (c === 0) return "The Zero";
  if (c === U7) return "Unlucky Frozen 7";
  if (c === L14) return "Lucky 14";
  if (c < 15) return String(c);
  if (isMod(c)) return MOD_TEXT[c];
  return ACTION_NAME[c];
}

// size: "" (default 110px) | "card--lg" | "card--sm" | "card--xs"
function cardHTML(c, cls = "", attrs = "", style = "") {
  let kind, inner;
  if (c === 0) { kind = "card--zero card--tag card--lite"; inner = '<span class="card__i">0</span><span class="card__v">0</span><span class="card__tag">The Zero</span>'; }
  else if (c === U7) { kind = "card--unlucky card--frozen card--tag"; inner = '<span class="card__i">7</span><svg class="card__glyph"><use href="#g-frost"/></svg><span class="card__v">7</span><svg class="card__crack" viewBox="0 0 60 80" aria-hidden="true"><path d="M38 4 30 28l8 7-11 22 4 6-3 13"/></svg><span class="card__tag">Frozen</span>'; }
  else if (c === L14) { kind = "card--2d card--lucky card--tag"; inner = '<span class="card__i">14</span><span class="card__v">14</span><span class="card__tag">Lucky</span>'; }
  else if (c < 15) { kind = `${c >= 10 ? "card--2d" : ""} ${isLite(c) ? "card--lite" : ""}`; style = `--c:var(--n${c});${style}`; inner = `<span class="card__i">${c}</span><span class="card__v">${c}</span>`; }
  else if (isMod(c)) { kind = "card--mod"; inner = `<span class="card__tag">Brutal</span><span class="card__burst"></span><span class="card__v">${MOD_TEXT[c]}</span>`; }
  else { kind = `card--act ${c < JOM ? "card--keep" : ""}`; style = `--a:var(--a-${ACTION_KEY[c]});${style}`; inner = `<span class="card__medal"><svg viewBox="0 0 48 48"><use href="#g-${ACTION_KEY[c]}"/></svg></span><span class="card__name">${ACTION_LABEL[c]}</span>`; }
  return `<div class="card ${kind} ${cls}" style="${style}" ${attrs} title="${esc(cardName(c))}">${inner}</div>`;
}
const CARD_X = '<svg class="card__x" viewBox="0 0 40 56" preserveAspectRatio="none" aria-hidden="true"><path class="o" d="M9 11 31 45M31 11 9 45"/><path class="i" d="M9 11 31 45M31 11 9 45"/></svg>';
// crossed: a busted player's card, turned face down and marked with an X
const backHTML = (cls = "", attrs = "", crossed = false) => `<div class="card card--back ${crossed ? "is-x" : ""} ${cls}" ${attrs}>${BACK_EMBLEM}${crossed ? CARD_X : ""}</div>`;

// Number kinds that would bust a line if drawn next (mirror of flip7/features.py).
function bustingKinds(line) {
  const held = new Set();
  let fourteens = 0;
  const hasL14 = line.includes(L14);
  for (const c of line) if (isNum(c)) { const r = rank(c); if (r === 14) fourteens++; else held.add(r); }
  const out = new Set();
  for (let c = 0; c < N_NUM; c++) {
    if (c === U7) continue;
    const r = rank(c);
    if (r === 14) { if (fourteens + 1 > (hasL14 || c === L14 ? 2 : 1)) out.add(c); }
    else if (held.has(r)) out.add(c);
  }
  return out;
}

// ------------------------------------------------------------------ actions (mirror of flip7/engine.py)
const A_PLAYER0 = 2, A_CARD0 = 8, NK = 25;
const aCard = (p, c) => A_CARD0 + p * NK + c;
const aPlayer = (p) => A_PLAYER0 + p;

// ------------------------------------------------------------------ client state
const S = {
  token: localStorage.getItem("flip7_token") || (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)),
  name: localStorage.getItem("flip7_name") || "",
  bots: [],
  lan: null,
  ws: null,
  roomId: null,
  state: null,
  view: null,          // "lobby" | "table"
  gameKey: null,
  log: [],
  prev: { lines: {}, status: {}, totals: {} },
  announce: null,
  side: { open: false, tab: "log" },
  chatSeen: 0,
  chatCollapsed: false,
  menu: false,
  odds: localStorage.getItem("flip7_odds") !== "0",
  overlayTimer: null,
  lastMine: -1,
  bust: {},            // seat -> "reveal" (drawn card shown face up) | "flip" (turning face down) | "done"
  retry: 0,            // reconnect attempts since the connection dropped
  stateAt: 0,          // when the last state arrived (for the "away" timers)
  pickKey: 0,          // number keys handed out to selectable cards this render
};
localStorage.setItem("flip7_token", S.token);

// ------------------------------------------------------------------ sound (synthesized, no assets)
const Sound = {
  ctx: null,
  on: localStorage.getItem("flip7_sound") !== "0",
  ensure() {
    try {
      if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      if (this.ctx.state === "suspended") this.ctx.resume();
    } catch { this.ctx = null; }
  },
  tone(freq, start, dur, type = "sine", vol = 0.12, slideTo = null) {
    const c = this.ctx, o = c.createOscillator(), g = c.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, c.currentTime + start);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, c.currentTime + start + dur);
    g.gain.setValueAtTime(0.0001, c.currentTime + start);
    g.gain.exponentialRampToValueAtTime(vol, c.currentTime + start + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + start + dur);
    o.connect(g).connect(c.destination);
    o.start(c.currentTime + start);
    o.stop(c.currentTime + start + dur + 0.05);
  },
  noise(start, dur, freq, vol) {
    const c = this.ctx, len = Math.floor(c.sampleRate * dur), buf = c.createBuffer(1, len, c.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len) ** 2;
    const src = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
    src.buffer = buf; f.type = "bandpass"; f.frequency.value = freq; f.Q.value = 0.9; g.gain.value = vol;
    src.connect(f).connect(g).connect(c.destination);
    src.start(c.currentTime + start);
  },
  play(kind, delay = 0) {
    if (!this.on || !this.ctx) return;
    try {
      if (kind === "card") this.noise(delay, 0.07, 2600, 0.5);
      else if (kind === "bust") { this.tone(170, delay, 0.32, "sine", 0.22, 48); this.noise(delay, 0.18, 300, 0.45); }
      else if (kind === "flip7") [523, 659, 784, 1046].forEach((f, i) => this.tone(f, delay + i * 0.09, 0.32, "triangle", 0.11));
      else if (kind === "turn") { this.tone(659, delay, 0.16, "sine", 0.08); this.tone(880, delay + 0.12, 0.24, "sine", 0.08); }
      else if (kind === "stay") this.tone(520, delay, 0.08, "sine", 0.06);
      else if (kind === "action") { this.tone(392, delay, 0.12, "square", 0.04); this.tone(587, delay + 0.08, 0.16, "square", 0.04); }
      else if (kind === "kick") {
        this.noise(Math.max(0, delay - 0.15), 0.17, 1300, 0.32);
        this.tone(150, delay, 0.24, "sine", 0.3, 42);
        this.noise(delay, 0.09, 480, 0.7);
        [0.07, 0.12, 0.19, 0.27].forEach((t) => this.noise(delay + t, 0.06, 2400 + t * 3000, 0.28));
      }
      else if (kind === "win") [392, 523, 659, 784, 1046].forEach((f, i) => this.tone(f, delay + i * 0.11, 0.4, "triangle", 0.1));
    } catch { /* audio is a nicety */ }
  },
};
document.addEventListener("pointerdown", () => Sound.ensure(), { once: true });
document.addEventListener("keydown", () => Sound.ensure(), { once: true });

// ------------------------------------------------------------------ small helpers
function toast(text, ms = 2600) {
  const el = document.createElement("div");
  el.className = "t";
  el.textContent = text;
  $("#toast").appendChild(el);
  setTimeout(() => el.remove(), ms);
}
// The static build (web/, GitHub Pages) has no server: the rooms run in a Web Worker instead.
const LOCAL = window.STATIC_SITE ? await import("./local.js") : null;
const REPO = "https://github.com/ThVerg/Bust-or-Bank-RL";
function send(obj) { if (S.ws && S.ws.readyState === 1) S.ws.send(JSON.stringify(obj)); }
async function api(path, body) {
  if (LOCAL) return LOCAL.api(path, body);
  const r = await fetch(path, body ? { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) } : {});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
function copy(text, label) {
  (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(() => toast(`${label} copied`), () => toast(text, 7000));
}
const initial = (name) => esc(((name || "?").trim()[0] || "?").toUpperCase());
const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const seatInfo = (p) => S.state?.room.seats[p] || {};
// Seconds a human has been disconnected (null if they're here), counting on from the last state.
const awayFor = (p) => {
  const s = seatInfo(p);
  return s.away == null ? null : s.away + (performance.now() - S.stateAt) / 1000;
};
const clock = (sec) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;
const seatName = (i) => S.state?.room.seats[i]?.name ?? `P${i + 1}`;
const meIdx = () => (S.state && !S.state.room.settings.watch ? S.state.room.you : -1);

// Monogram token. Bots get the rounded square, humans the circle.
function avatar(p, { cls = "", name, bot, dealer = false, online } = {}) {
  const s = seatInfo(p);
  const isBot = bot ?? s.kind === "bot";
  const on = online === undefined ? "" : `<i class="online ${online ? "" : "off"}"></i>`;
  return `<span class="avatar ${isBot ? "avatar--bot" : ""} sc${((p % 6) + 6) % 6} ${cls}" aria-hidden="true"><b>${initial(name ?? s.name)}</b>${dealer ? '<i class="dealer">D</i>' : ""}${on}</span>`;
}

// Short label for what kind of bot sits in a seat.
function botTag(id) {
  if (!id) return "Bot";
  if (id.startsWith("search:")) return "RL+Search";
  if (id.startsWith("rollout")) return "RL+Rollouts";
  if (id === "nn:rl_rookie") return "RL rookie";
  if (id.startsWith("nn:")) return "RL";
  if (id === "smart") return "Card counter";
  if (id.startsWith("threshold")) return "Simple";
  if (id === "random") return "Random";
  return "Bot";
}

// ------------------------------------------------------------------ name
function updateMeChip() {
  $("#me-name").textContent = S.name || "Set your name";
  $("#me-av b").textContent = (S.name || "?")[0].toUpperCase();
}
function askName(force = false) {
  return new Promise((resolve) => {
    if (S.name && !force) return resolve(S.name);
    $("#overlay").innerHTML = `
      <div class="scrim"><form class="sheet" id="name-form">
        ${ribbon("Pull up a chair", "ribbon--mustard")}
        <p class="sub" style="margin-top:6px">What should the table call you?</p>
        <div class="row"><input class="input" type="text" id="name-input" maxlength="20" placeholder="Your name" value="${esc(S.name)}" autocomplete="nickname"><button class="btn btn--orange btn--lg">Sit down</button></div>
      </form></div>`;
    const input = $("#name-input");
    input.focus();
    input.select();
    $("#name-form").onsubmit = (e) => {
      e.preventDefault();
      S.name = input.value.trim().slice(0, 20) || "Player";
      localStorage.setItem("flip7_name", S.name);
      updateMeChip();
      $("#overlay").innerHTML = "";
      send({ type: "rename", name: S.name });
      resolve(S.name);
    };
  });
}
$("#me-chip").onclick = () => askName(true);

// ------------------------------------------------------------------ routing
function route() {
  const [page, arg] = location.hash.replace(/^#\/?/, "").split("/");
  $$(".nav a").forEach((a) => a.classList.toggle("on", a.dataset.nav === (page || "home") || (page === "room" && a.dataset.nav === "home")));
  if (page === "room" && arg) return openRoom(arg.toUpperCase());
  closeRoom();
  document.title = "Bust or Bank";
  if (page === "watch") renderWatchSetup();
  else if (page === "insights") renderInsights();
  else if (page === "rules") renderRules();
  else renderHome();
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

// ------------------------------------------------------------------ bots & difficulty
const LEVELS = [
  { id: "nn:rl_rookie", name: "Rookie", blurb: "Early snapshot", lvl: 1, seat: 4 },
  { id: "nn:flip7_rl", name: "Shark", blurb: "Pure RL", lvl: 2, seat: 1 },
  { id: "search:flip7_rl", name: "Boss", blurb: "RL + lookahead", lvl: 3, seat: 2 },
];
const hasBot = (id) => S.bots.some((b) => b.id === id);
const SHORT_BOT = { "search:flip7_rl": "Boss", "nn:flip7_rl": "Shark", "nn:rl_rookie": "Rookie", smart: "SmartBot", threshold25: "Steady Eddie", random: "Chaos Monkey" };
const shortBot = (id, fallback) => SHORT_BOT[id] || fallback || id;
const bestBot = () => (hasBot("search:flip7_rl") ? "search:flip7_rl" : S.bots[0]?.id || "smart");

// ------------------------------------------------------------------ home
function renderHome() {
  setTools("");
  const fan = [[1, -24, -258, 72], [3, -16, -172, 32], [5, -8, -86, 8], [7, 0, 0, 0], [9, 8, 86, 8], [11, 16, 172, 32], [13, 24, 258, 72]]
    .map(([c, r, x, y]) => cardHTML(c, "", "", `--r:${r}deg;--x:${x}px;--y:${y}px`)).join("");
  const levels = LEVELS.filter((l) => hasBot(l.id));
  const classics = S.bots.filter((b) => b.kind === "heuristic");
  let bot = levels.some((l) => l.id === bestBot()) ? bestBot() : levels[0]?.id || bestBot();
  app.innerHTML = `
  <div class="page">
    <section class="hero">
      <div class="hero__copy">
        <h1 class="hero__logo">${LOGO}</h1>
        <p class="hero__tag">${icon("flame")}Push your luck <span>·</span> Wreck your rivals</p>
        <p class="hero__line">Play the bots that <b>taught themselves</b> — then try to out-luck them.</p>
        <div class="hero__ctas">
          <button class="btn btn--orange btn--xl" id="quick">${icon("play")}Play now</button>
          <a class="btn btn--stock btn--xl" href="#/watch">${icon("eye")}Watch the bots</a>
        </div>
        <div class="stat"><span class="stat__ico">${icon("bot")}</span><div><small>Taught itself over</small><b>1,600,000+<span>games</span></b><small>of self-play</small></div></div>
      </div>
      <div class="hero__art" aria-hidden="true">
        <div class="fan">${fan}</div>
        <div class="flip7-note"><b>Seven different numbers</b><span>=</span><b class="hl">Flip 7</b><span>+15 bonus</span></div>
      </div>
    </section>

    <div class="section-head" id="setup"><div><h2>Choose your table</h2><p>${LOCAL ? "Everything runs in your browser: the same bots as on the server, on your device." : "Everything runs on this computer. Friends on your Wi-Fi can join with a link."}</p></div></div>
    <section class="modes">
      <section class="mode mode--bots">
        <header class="mode__head"><span class="mode__ico">${icon("bot")}</span><h2>Play vs bots</h2><p>Solo · you + 1–5 bots</p></header>
        <div class="mode__body">
          <div class="field"><span class="label">Pick your rival</span>
            <div class="diff" id="opp-level">${levels.map((l) => `<button class="diff__tile ${l.id === bot ? "on" : ""}" data-bot="${l.id}">${avatar(l.seat, { name: l.name, bot: true })}<b>${l.name}</b><span class="pips" aria-label="${l.lvl} of 3">${[1, 2, 3].map((i) => `<i class="${i <= l.lvl ? "on" : ""}"></i>`).join("")}</span><em>${l.blurb}</em></button>`).join("")}</div>
          </div>
          <div class="field-row">
            <div class="field"><span class="label">Opponents</span><div class="seg" id="opp-count">${[1, 2, 3, 4, 5].map((n) => `<button data-n="${n}" class="${n === 3 ? "on" : ""}">${n}</button>`).join("")}</div></div>
            <div class="field"><span class="label">Or a hand-written bot</span><select class="select" id="opp-classic" aria-label="Hand-written bot"><option value="">—</option>${classics.map((b) => `<option value="${esc(b.id)}">${esc(b.name)}</option>`).join("")}</select></div>
          </div>
          <div class="row" style="gap:22px"><label class="toggle"><input type="checkbox" id="vb-coach"> Coach hints</label><label class="toggle"><input type="checkbox" id="vb-brutal" checked> Brutal Mode</label></div>
          <button class="btn btn--orange btn--lg btn--block" id="play-bots">${icon("play")}<span id="play-label">Deal me in</span></button>
        </div>
      </section>
      <section class="mode mode--friends">
        <header class="mode__head"><span class="mode__ico">${icon("users")}</span><h2>With friends</h2><p>${LOCAL ? "Self-hosted" : "Private by default"}</p></header>
        ${LOCAL ? `<div class="mode__body">
          <p class="muted">Tables with friends need the game server, which this page runs without. Hosting one takes a single Docker command on any computer; friends on the same Wi-Fi join with a link.</p>
          <a class="btn btn--teal btn--lg btn--block" href="${REPO}#run-it-yourself" target="_blank" rel="noopener">${icon("users")}Host a table</a>
        </div>` : `<div class="mode__body">
          <div class="field-row"><span class="label">Seats</span><div class="seg" id="seat-count">${[2, 3, 4, 5, 6].map((n) => `<button data-n="${n}" class="${n === 4 ? "on" : ""}">${n}</button>`).join("")}</div></div>
          <button class="btn btn--teal btn--lg btn--block" id="create-room">${icon("plus")}Create room</button>
          <div class="or">or join with a code</div>
          <label class="toggle"><input type="checkbox" id="fr-public"> List it for others on this network</label>
          <form class="join" id="join-form"><input class="input" type="text" id="join-code" maxlength="5" placeholder="KX7Q" aria-label="Room code"><button class="btn btn--lg">${icon("enter")}Join</button></form>
          <div class="open-rooms" id="open-rooms"></div>
        </div>`}
      </section>
      <section class="mode mode--watch">
        <header class="mode__head"><span class="mode__ico">${icon("eye")}</span><h2>Watch the bots</h2><p>Bot vs bot</p></header>
        <div class="mode__body">
          <div class="lineups">
            ${[
              ["rl-smart", "Boss vs SmartBot", "One-on-one: the network against a card-counting expert", [2, 1]],
              ["rl-4", "Four-way grudge match", "Four RL bots at one table", [2, 1, 2, 1]],
              ["mixed", "RL vs hand-written", "Boss, Shark, SmartBot and Steady Eddie", [2, 1, 3, 4]],
            ].map(([id, t, s, dots]) => `<button class="lineup" data-lineup="${id}"><div><b>${t}</b><small>${s}</small></div><div class="dots">${dots.map((d, i) => avatar(d, { name: t.split(/[\s,]+/)[0] === "Four-way" ? "R" : ["B", "S", "S", "E"][i], bot: true })).join("")}</div></button>`).join("")}
          </div>
          <a class="btn btn--plum btn--lg btn--block" href="#/watch">${icon("eye")}Build a line-up</a>
        </div>
      </section>
    </section>
    <footer class="home__foot">
      <a class="footlink" href="#/insights"><span class="footlink__ico">${icon("chart")}</span><span><b>Insights</b> — what the bots learned</span>${icon("arrow", "ico arr")}</a>
      <a class="footlink" href="#/rules"><span class="footlink__ico" style="background:var(--orange)">${icon("book")}</span><span><b>Rules</b> — learn it in two minutes</span>${icon("arrow", "ico arr")}</a>
      <a class="footlink" href="${REPO}" target="_blank" rel="noopener"><span class="footlink__ico" style="background:var(--teal)">${icon("code")}</span><span><b>Source</b> — open source on GitHub</span>${icon("arrow", "ico arr")}</a>
      <p class="home__legal">Bust or Bank is an unofficial fan variant of Flip 7: With a Vengeance, not affiliated with or endorsed by its publisher, The Op Games. The card designs and rules text here are this project's own.</p>
    </footer>
  </div>`;

  let opp = 3, seats = 4;
  const label = () => { const l = LEVELS.find((x) => x.id === bot); $("#play-label").textContent = `Deal me in vs ${l ? l.name : shortBot(bot, S.bots.find((b) => b.id === bot)?.name)}`; };
  label();
  const segPick = (sel, cb) => $$(`${sel} button`).forEach((b) => (b.onclick = () => { $$(`${sel} button`).forEach((x) => x.classList.toggle("on", x === b)); cb(+b.dataset.n); }));
  segPick("#opp-count", (n) => (opp = n));
  if (!LOCAL) segPick("#seat-count", (n) => (seats = n));
  $$("#opp-level .diff__tile").forEach((b) => (b.onclick = () => { bot = b.dataset.bot; $("#opp-classic").value = ""; $$("#opp-level .diff__tile").forEach((x) => x.classList.toggle("on", x === b)); label(); }));
  $("#opp-classic").onchange = (e) => { if (e.target.value) { bot = e.target.value; $$("#opp-level .diff__tile").forEach((x) => x.classList.remove("on")); label(); } };
  $("#quick").onclick = async () => { await askName(); createRoom({ seats: [{ kind: "me" }, ...Array(3).fill({ kind: "bot", bot_id: bestBot() })], autostart: true }); };
  $("#play-bots").onclick = async () => {
    await askName();
    createRoom({ seats: [{ kind: "me" }, ...Array(opp).fill({ kind: "bot", bot_id: bot })], autostart: true, brutal: $("#vb-brutal").checked, coach: $("#vb-coach").checked });
  };
  if (!LOCAL) {
    $("#create-room").onclick = async () => { await askName(); createRoom({ seats: [{ kind: "me" }, ...Array(seats - 1).fill({ kind: "open" })], public: $("#fr-public").checked }); };
    $("#join-form").onsubmit = (e) => { e.preventDefault(); const c = $("#join-code").value.trim().toUpperCase(); if (c) location.hash = `#/room/${c}`; };
  }
  $$("[data-lineup]").forEach((b) => (b.onclick = () => {
    const boss = bestBot(), shark = hasBot("nn:flip7_rl") ? "nn:flip7_rl" : boss;
    const lineups = { "rl-smart": [boss, "smart"], "rl-4": [boss, shark, boss, shark], mixed: [boss, shark, "smart", "threshold25"] };
    createRoom({ seats: lineups[b.dataset.lineup].map((id) => ({ kind: "bot", bot_id: id })), watch: true, autostart: true, speed: 1.1 });
  }));
  if (!LOCAL) api("/api/rooms").then((rooms) => {
    const el = $("#open-rooms");
    if (el && rooms.length) el.innerHTML = `<span class="label">Open tables</span>` + rooms.map((r) => `<a href="#/room/${r.id}"><span><b>${esc(r.host)}</b>'s table</span><span class="muted">${r.open} of ${r.seats} open · ${r.id}</span></a>`).join("");
  }).catch(() => {});
}

async function createRoom(spec) {
  try {
    const { id } = await api("/api/rooms", { token: S.token, name: S.name || "Player", ...spec });
    location.hash = `#/room/${id}`;
  } catch (e) { toast("Could not create the room: " + e.message); }
}

// ------------------------------------------------------------------ watch setup
function renderWatchSetup() {
  setTools("");
  let n = 4;
  const picks = {};
  const draw = () => {
    $("#wseats").innerHTML = Array.from({ length: n }, (_, i) => {
      const def = picks[i] || (i % 2 === 0 ? bestBot() : "smart");
      return `<div class="setup-seat"><div class="t">${avatar(i, { name: String(i + 1), bot: true })}Seat ${i + 1}</div><select class="select" data-wseat="${i}" aria-label="Seat ${i + 1} bot">${S.bots.map((b) => `<option value="${esc(b.id)}" ${b.id === def ? "selected" : ""}>${esc(b.name)}</option>`).join("")}</select></div>`;
    }).join("");
    $$("[data-wseat]").forEach((s) => (s.onchange = () => (picks[s.dataset.wseat] = s.value)));
  };
  app.innerHTML = `
  <div class="page">
    <div class="pagehead"><h1>Watch the bots</h1><p>Pick the line-up and watch them play. You'll see every player's chance of winning the game, and how likely the RL network thinks each possible move is.</p></div>
    <div class="setup">
      <div class="panel">
        <div class="field-row"><span class="label">Players</span><div class="seg" id="wcount">${[2, 3, 4, 5, 6].map((k) => `<button data-n="${k}" class="${k === n ? "on" : ""}">${k}</button>`).join("")}</div></div>
        <div class="setup-seats" id="wseats"></div>
        <div class="field"><span class="label">Pace: <span id="wspeed-l">1.1</span> s per move</span><input type="range" id="wspeed" min="0.1" max="3" step="0.1" value="1.1"></div>
        <label class="toggle"><input type="checkbox" id="wbrutal" checked> Brutal Mode</label>
        <div><button class="btn btn--plum btn--xl" id="wgo">${icon("play")}Start the show</button></div>
      </div>
      <div class="panel"><h3>The line-up</h3><div class="bot-notes">${S.bots.map((b) => `<div><b>${esc(b.name)}</b><br>${esc(b.blurb)}</div>`).join("")}</div></div>
    </div>
  </div>`;
  draw();
  $$("#wcount button").forEach((b) => (b.onclick = () => { n = +b.dataset.n; $$("#wcount button").forEach((x) => x.classList.toggle("on", x === b)); draw(); }));
  $("#wspeed").oninput = (e) => ($("#wspeed-l").textContent = (+e.target.value).toFixed(1));
  $("#wgo").onclick = () => createRoom({
    seats: Array.from({ length: n }, (_, i) => ({ kind: "bot", bot_id: $(`[data-wseat="${i}"]`).value })),
    watch: true, autostart: true, brutal: $("#wbrutal").checked, speed: +$("#wspeed").value,
  });
}

// ------------------------------------------------------------------ room connection
function openRoom(id) {
  if (S.roomId === id && S.ws && S.ws.readyState <= 1) return;
  closeRoom();
  S.roomId = id;
  S.state = null;
  S.view = null;
  S.gameKey = null;
  S.log = [];
  S.prev = { lines: {}, status: {}, totals: {} };
  S.announce = null;
  S.chatSeen = 0;
  app.innerHTML = `<div class="page"><div class="pagehead"><h1>Finding table ${esc(id)}…</h1></div></div>`;
  S.retry = 0;
  connect(id);
}

// (Re)connect without touching what's on screen; while the connection is down a banner says so.
function connect(id) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = LOCAL ? new LOCAL.Socket(id, S.token, S.name || "Guest")
    : new WebSocket(`${proto}://${location.host}/ws/${id}?token=${encodeURIComponent(S.token)}&name=${encodeURIComponent(S.name || "Guest")}`);
  S.ws = ws;
  ws.onmessage = (e) => { S.retry = 0; setNetBanner(false); onMessage(JSON.parse(e.data)); };
  ws.onclose = () => {
    if (S.ws !== ws) return;
    S.ws = null;
    if (S.roomId !== id) return;
    setNetBanner(true);
    const delay = Math.min(5000, 800 * 2 ** S.retry++);
    setTimeout(() => { if (S.roomId === id && !S.ws) connect(id); }, delay);
  };
}

function setNetBanner(down) {
  let el = $("#netbar");
  if (!down) { el?.remove(); return; }
  if (!el) {
    el = document.createElement("div");
    el.id = "netbar";
    el.setAttribute("role", "status");
    el.innerHTML = `<span class="spin"></span><span>Connection lost — reconnecting…</span>`;
    document.body.appendChild(el);
  }
}

function closeRoom() {
  if (S.ws) { const ws = S.ws; S.ws = null; ws.close(); }
  setNetBanner(false);
  S.roomId = null;
  S.view = null;
  S.menu = false;
  document.body.classList.remove("in-game");
  clearTimeout(S.overlayTimer);
  $("#overlay").innerHTML = "";
  $(".menu")?.remove();
}

function onMessage(msg) {
  if (msg.type === "error") {
    if (msg.message === "Room not found") {
      S.roomId = null;
      app.innerHTML = `<div class="page"><div class="pagehead"><h1>That table is gone</h1><p>${LOCAL ? "Games here run in this browser tab, so a table ends when you leave or reload the page." : "Rooms close an hour after everyone leaves."}</p></div><a class="btn btn--orange btn--lg" href="#/">Back to the lobby</a></div>`;
    } else toast(msg.message);
    return;
  }
  if (msg.type !== "state") return;
  const first = !S.state;
  S.state = msg;
  S.stateAt = performance.now();
  const { room, game } = msg;
  let events = [];
  if (game) {
    const key = `${room.games_played}:${room.mode === "lobby" ? "l" : "g"}`;
    if (S.gameKey !== key && room.mode === "playing") { S.log = []; S.prev = { lines: {}, status: {}, totals: {} }; S.announce = null; }
    S.gameKey = key;
    if (game.replayed) S.log = game.events.slice();
    else if (game.events.length) {
      S.log.push(...game.events);
      if (S.log.length > 500) S.log = S.log.slice(-500);
      events = game.events;
    }
  }
  if (first && !S.name && room.you < 0 && room.seats.some((s) => s.kind === "open")) askName();
  if (room.mode === "lobby" || !game) {
    S.view = "lobby";
    document.body.classList.remove("in-game");
    renderLobby(room);
  } else {
    if (S.view !== "table") { buildTable(room); S.view = "table"; }
    updateTable(msg, events);
  }
  const slot = $("#review-slot");
  if (slot && msg.review && slot.dataset.filled !== "1") { S.review = msg.review; slot.innerHTML = reviewHTML(msg.review); slot.dataset.filled = "1"; }
  else if (slot && msg.review_pending && !slot.dataset.filled) { slot.innerHTML = `<div class="review"><h4>Coach's review</h4><p class="row-r"><span class="spin"></span>The coach is replaying your decisions…</p></div>`; slot.dataset.filled = "pending"; }
}

// ------------------------------------------------------------------ event text
const W = (i) => `<span class="w">${esc(seatName(i))}</span>`;
const modChip = (c) => `<span class="log__mod">${MOD_TEXT[c]}</span>`;
const EV_ICON = { round: ["flag", "var(--ink-2)"], draw: ["plus", "var(--ink-2)"], stay: ["snow", "var(--ice-deep)"], bust: ["skull", "var(--rust)"], flip7: ["star", "var(--mustard)"],
  unlucky7: ["skull", "var(--unlucky)"], action: ["spark", "var(--denim)"], modifier: ["minus", "var(--ink)"], steal: ["mask", "var(--plum)"], swap: ["swap", "var(--teal)"],
  discard: ["x", "var(--rust)"], fizzle: ["x", "var(--ink-3)"], reshuffle: ["layers", "var(--ink-2)"], flip7_bonus: ["star", "var(--mustard)"], round_end: ["flag", "var(--ink-2)"], game_over: ["trophy", "var(--orange)"],
  reveal: ["eye", "var(--orange)"], delivery: ["arrow", "var(--orange)"], bounty: ["flag", "var(--berry)"], bounty_claim: ["trophy", "var(--berry)"], dare: ["flame", "var(--tangerine)"],
  shakedown: ["mask", "var(--ink-2)"], pay: ["minus", "var(--ink-2)"], refuse: ["plus", "var(--orange)"], robin: ["arrow", "var(--olive)"], spite: ["skull", "var(--rust)"], keeper: ["plus", "var(--ink-2)"] };

function fmtEvent(ev) {
  const c = (card) => (isMod(card) ? modChip(card) : `<b>${esc(cardName(card))}</b>`);
  switch (ev.t) {
    case "round": return { html: `Round ${ev.round} · ${esc(seatName(ev.dealer))} deals`, cls: "round" };
    case "draw": {
      const via = { flip4: ` <span class="muted">(Flip Four, ${ev.left} left)</span>`, jom: ' <span class="muted">(Just One More)</span>', deal: ' <span class="muted">(deal)</span>', shakedown: ' <span class="muted">(Shakedown)</span>' }[ev.via] || "";
      return { html: `${W(ev.p)} drew ${c(ev.card)}${via}` };
    }
    case "stay": return { html: ev.forced ? `${W(ev.p)} is forced to stay` : `${W(ev.p)} stays` };
    case "bust": return { html: `${W(ev.p)} busts`, cls: "bad" };
    case "flip7": return { html: `${W(ev.p)} flips 7!`, cls: "good" };
    case "unlucky7": return { html: `${W(ev.p)}'s Unlucky Frozen 7 ${ev.wiped.length ? `wipes ${ev.wiped.map(cardName).join(", ")} and ` : ""}freezes them`, cls: "bad" };
    case "action": return { html: `${W(ev.p)} plays <b>${cardName(ev.card)}</b> on ${ev.target === ev.p ? "themselves" : W(ev.target)}` };
    case "modifier": return { html: `${W(ev.p)} gives ${c(ev.card)} to ${ev.target === ev.p ? "themselves" : W(ev.target)}`, cls: ev.target === ev.p ? "" : "bad" };
    case "steal": return { html: `${W(ev.p)} steals ${W(ev.victim)}'s ${c(ev.card)}` };
    case "swap": return { html: `${W(ev.p)} swaps ${W(ev.a)}'s ${c(ev.card_a)} with ${W(ev.b)}'s ${c(ev.card_b)}` };
    case "discard": return { html: `${W(ev.p)} discards ${ev.victim === ev.p ? "their own" : W(ev.victim) + "'s"} ${c(ev.card)}` };
    case "fizzle": return { html: `${W(ev.p)}'s ${cardName(ev.card)} has no target` };
    case "reshuffle": return { html: `Deck empty: ${ev.size} discards reshuffled`, cls: "round" };
    case "flip7_bonus": return { html: ev.target === ev.p ? `${W(ev.p)} takes the +15 bonus` : `${W(ev.p)} makes ${W(ev.target)} lose 15`, cls: "good" };
    case "round_end": return { html: `Round over: ${ev.scores.map((s, i) => `${esc(seatName(i))} ${signed(s)}`).join(" · ")}${(ev.taxes || []).filter((x) => x.amount).map((x) => ` · Tax: ${esc(seatName(x.from))} pays ${esc(seatName(x.p))} ${x.amount}`).join("")}`, cls: "round" };
    case "reveal": return { html: `${W(ev.p)} flips ${c(ev.card)} for a Special Delivery` };
    case "delivery": return { html: `${W(ev.p)} delivers ${c(ev.card)} to ${ev.target === ev.p ? "themselves" : W(ev.target)}`, cls: ev.target === ev.p ? "" : "bad" };
    case "bounty": return { html: `${W(ev.p)} puts a Bounty on ${W(ev.target)}`, cls: "bad" };
    case "bounty_claim": return { html: `${W(ev.p)} collects the Bounty on ${W(ev.victim)}: +${ev.amount}`, cls: "good" };
    case "dare": return { html: `${W(ev.p)} double-dares ${W(ev.target)}: two forced hits` };
    case "shakedown": return { html: `${W(ev.p)} shakes down ${W(ev.target)}` };
    case "pay": return { html: `${W(ev.p)} pays ${W(ev.to)} ${ev.amount}`, cls: "bad" };
    case "refuse": return { html: `${W(ev.p)} won't pay ${W(ev.to)} and takes a card` };
    case "robin": return { html: ev.amount ? `Robin Hood: ${W(ev.rich)} gives ${W(ev.poor)} ${ev.amount}` : "Robin Hood finds nobody to rob" };
    case "spite": return { html: `${W(ev.p)}'s Spite costs ${W(ev.target)} ${ev.amount} this round`, cls: "bad" };
    case "keeper": return { html: `${W(ev.p)} keeps ${c(ev.card)}` };
    case "game_over": return { html: `${ev.winners.map((w) => esc(seatName(w))).join(" & ")} win${ev.winners.length > 1 ? "" : "s"} the game`, cls: "good" };
    default: return null;
  }
}

const PRIORITY = { game_over: 10, flip7: 9, flip7_bonus: 8.5, bounty_claim: 8.2, bust: 8, unlucky7: 7, spite: 7, steal: 6, swap: 6, discard: 6, delivery: 6, robin: 6,
  action: 5, bounty: 5, dare: 5, pay: 5, refuse: 5, shakedown: 4.5, modifier: 4, round_end: 3, keeper: 3, draw: 2, stay: 2, reveal: 1.5, fizzle: 1, reshuffle: 1, round: 0.5 };

// The announcer ribbon: who did what, in one line.
function announceFor(ev) {
  const me = meIdx();
  const subj = (i) => (i === me ? "You" : esc(seatName(i)));
  const obj = (i) => (i === me ? "you" : esc(seatName(i)));
  const poss = (i) => (i === me ? "your" : `${esc(seatName(i))}'s`);
  const xs = (c) => cardHTML(c, "card--xs");
  switch (ev.t) {
    case "flip7": return { p: ev.p, label: "Flip 7", title: `${subj(ev.p)} flipped 7!`, tone: "ribbon--mustard" };
    case "flip7_bonus": return ev.target === ev.p ? { p: ev.p, label: "Flip 7 bonus", title: `+15 for ${obj(ev.p)}`, tone: "ribbon--mustard" } : { p: ev.p, label: "Revenge", title: `−15 for ${obj(ev.target)}`, sub: `${subj(ev.p)} chose revenge over the bonus`, tone: "ribbon--rust" };
    case "bust": return { p: ev.p, label: "Bust", title: `${subj(ev.p)} busted on ${xs(ev.line[ev.line.length - 1])}`, sub: `${ev.line.filter(isNum).length} cards lost`, tone: "ribbon--rust" };
    case "unlucky7": return { p: ev.p, label: "Frozen 7", title: `${xs(U7)} freezes ${obj(ev.p)}`, sub: `${ev.wiped.length ? `${ev.wiped.length} card${ev.wiped.length === 1 ? "" : "s"} wiped · ` : ""}no more cards this round`, tone: "ribbon--ice" };
    case "delivery": return { p: ev.p, label: "Special Delivery", title: `${xs(ev.card)} for ${ev.target === ev.p ? (ev.p === me ? "yourself" : "themselves") : obj(ev.target)}`, sub: `delivered by ${obj(ev.p)}`, tone: ev.target === ev.p ? "ribbon--teal" : "ribbon--orange" };
    case "bounty": return { p: ev.p, label: "Bounty", title: `Bounty on ${obj(ev.target)}`, sub: "bust them with your card: +10", tone: "ribbon--rust" };
    case "bounty_claim": return { p: ev.p, label: "Bounty collected", title: `${subj(ev.p)} +${ev.amount}`, sub: `for busting ${obj(ev.victim)}`, tone: "ribbon--mustard" };
    case "dare": return { p: ev.p, label: "Double Dare", title: `${subj(ev.target)} must hit twice`, sub: `dared by ${obj(ev.p)}`, tone: "ribbon--orange" };
    case "shakedown": return { p: ev.p, label: "Shakedown", title: `${subj(ev.p)} ${ev.p === me ? "shake" : "shakes"} down ${obj(ev.target)}`, sub: "pay 10 or take a card", tone: "ribbon--plum" };
    case "pay": return { p: ev.p, label: "Paid up", title: `${subj(ev.p)} ${ev.p === me ? "pay" : "pays"} ${obj(ev.to)} ${ev.amount}`, tone: "ribbon--ink" };
    case "refuse": return { p: ev.p, label: "No deal", title: `${subj(ev.p)} ${ev.p === me ? "take" : "takes"} a card instead`, tone: "ribbon--orange" };
    case "robin": return { p: ev.p, label: "Robin Hood", title: ev.amount ? `${subj(ev.rich)} → ${obj(ev.poor)}: ${ev.amount}` : "Nobody to rob", sub: ev.amount ? "from the richest to the poorest" : "", tone: "ribbon--teal" };
    case "spite": return { p: ev.p, label: "Spite", title: `${subj(ev.target)} ${ev.target === me ? "lose" : "loses"} ${ev.amount}`, sub: `${poss(ev.p)} parting shot`, tone: "ribbon--rust" };
    case "keeper": return { p: ev.p, label: "Keeper", title: `${subj(ev.p)} ${ev.p === me ? "keep" : "keeps"} ${xs(ev.card)}`, tone: "ribbon--ink", calm: true };
    case "reveal": return { p: ev.p, label: "Special Delivery", title: `${subj(ev.p)} flipped ${xs(ev.card)}`, sub: "choosing who gets it", tone: "ribbon--ink", calm: true };
    case "steal": return { p: ev.p, label: "Last play", title: `${subj(ev.p)} stole ${poss(ev.victim)} ${xs(ev.card)}!`, tone: "ribbon--plum" };
    case "swap": return { p: ev.p, label: "Swap", title: `${poss(ev.a)} ${xs(ev.card_a)} ⇄ ${poss(ev.b)} ${xs(ev.card_b)}`, sub: `${subj(ev.p)} swapped them`, tone: "ribbon--teal" };
    case "discard": return { p: ev.p, label: "Discard", title: `${subj(ev.p)} binned ${ev.victim === ev.p ? (ev.p === me ? "your own" : "their own") : poss(ev.victim)} ${xs(ev.card)}` };
    case "action": return { p: ev.p, label: cardName(ev.card), title: `${xs(ev.card)} ${ev.card === FLIP4 ? "Flip Four" : "Just One More"} for ${ev.target === ev.p ? (ev.p === me ? "yourself" : "themselves") : obj(ev.target)}`, sub: `played by ${obj(ev.p)}` };
    case "modifier": return { p: ev.p, label: "Brutal", title: `${subj(ev.p)} gave ${ev.target === ev.p ? (ev.p === me ? "yourself" : "themselves") : obj(ev.target)} ${xs(ev.card)}`, tone: ev.target === ev.p ? "" : "ribbon--rust" };
    case "round_end": return { label: "Scores in", title: "Round over", tone: "ribbon--mustard", calm: true };
    case "game_over": return { p: ev.winners[0], label: "Game over", title: `${ev.winners.map(subj).join(" & ")} win${ev.winners.length > 1 || ev.winners[0] === me ? "" : "s"}!`, tone: "ribbon--mustard" };
    case "draw": return { p: ev.p, label: { flip4: `Flip Four · ${ev.left} to go`, jom: "Just One More", deal: "Opening deal", shakedown: "Shakedown" }[ev.via] || "Last card", title: `${subj(ev.p)} drew ${xs(ev.card)}`, tone: "ribbon--ink", calm: true };
    case "stay": {
      const pl = S.state.game.players[ev.p];
      const frozen = ev.forced ? `Just One More: no more cards this round${pl && pl.status === 1 ? ` · frozen at ${pl.projected}` : ""}`
        : pl && pl.status === 1 ? `Frozen at ${pl.projected} points` : "";
      return { p: ev.p, label: "Banked", title: `${subj(ev.p)} ${ev.forced ? "must stay" : ev.p === me ? "stay" : "stays"}`, sub: frozen, tone: "ribbon--ice", calm: true };
    }
    case "fizzle": return { p: ev.p, label: "No target", title: `${xs(ev.card)} fizzles`, tone: "ribbon--ink", calm: true };
    case "reshuffle": return { label: "Deck empty", title: "Reshuffle", sub: `${ev.size} cards back in the deck`, tone: "ribbon--ink", calm: true };
    case "round": return { p: ev.dealer, label: `${subj(ev.dealer)} ${ev.dealer === me ? "deal" : "deals"}`, title: `Round ${ev.round}`, tone: "ribbon--mustard", calm: true };
    default: return null;
  }
}

// ------------------------------------------------------------------ lobby
function renderLobby(room) {
  setTools("");
  const link = `${location.origin}/#/room/${room.id}`;
  const local = /^(localhost|127\.|0\.0\.0\.0)/.test(location.hostname);
  const lanLink = S.lan ? `http://${S.lan}:${location.port || 80}/#/room/${room.id}` : null;
  const n = room.seats.length;
  const base = room.you >= 0 ? room.you : 0;
  const seatsHTML = room.seats.map((s, i) => {
    const k = (i - base + n) % n;
    const th = Math.PI / 2 + (2 * Math.PI * k) / n;
    const x = 50 + 50 * Math.cos(th), y = 50 + 50 * Math.sin(th);
    let sub, ctl = "";
    if (s.kind === "open") sub = "Open seat";
    else if (s.kind === "bot") sub = esc(botTag(s.bot_id));
    else sub = i === room.you ? "You" : s.online ? "Online" : "Offline";
    if (room.host && !(s.kind === "human" && i === room.you)) {
      ctl = `<select class="select" data-seat="${i}" aria-label="Seat ${i + 1}">
        ${LOCAL && s.kind === "bot" ? "" : `<option value="open" ${s.kind !== "bot" ? "selected" : ""}>${s.kind === "human" ? esc(s.name) + " (human)" : "Open for a friend"}</option>`}
        ${S.bots.map((b) => `<option value="bot:${esc(b.id)}" ${s.kind === "bot" && s.bot_id === b.id ? "selected" : ""}>Bot: ${esc(shortBot(b.id, b.name))}</option>`).join("")}
        ${n > 2 ? `<option value="remove">Remove this seat</option>` : ""}</select>`;
    } else if (s.kind === "open" && room.you < 0) ctl = `<button class="btn btn--orange btn--sm" data-cmd="sit" data-seat="${i}">Sit here</button>`;
    else if (i === room.you && !room.host) ctl = `<button class="btn btn--stock btn--sm" data-cmd="leave">Leave seat</button>`;
    const av = s.kind === "open" ? `<span class="avatar avatar--open"><b>?</b></span>` : avatar(i, { online: s.kind === "human" ? s.online : undefined });
    return `<div class="lseat ${s.kind === "open" ? "open" : ""}" style="left:${x}%;top:${y}%">
      <div class="plate">${av}<div class="who"><div class="nm">${s.kind === "open" ? "Empty" : esc(s.name)}</div><div class="sub">${sub}</div></div></div>${ctl}</div>`;
  }).join("");
  const canStart = room.seats.every((s) => s.kind !== "open");
  const chatVal = $("#lobby-chat-input")?.value || "";
  const chatFocus = document.activeElement?.id === "lobby-chat-input";
  app.innerHTML = `
  <div class="page">
    <div class="lobby-head"><h1>Your table</h1>${ribbon(esc(room.id), "ribbon--mustard")}</div>
    <p class="muted">${room.host ? (LOCAL ? "Pick the bots, then deal." : "Share the link, fill the seats, then deal.") : "The host deals when everyone's seated."}</p>
    <div class="lobby">
      <div>
        <div class="mini-table"><div class="disc-label">${LOGO}<span class="chip ${room.settings.brutal ? "chip--brutal" : ""}">${room.settings.brutal ? `${icon("flame")}Brutal Mode` : "Standard rules"}</span></div>${seatsHTML}</div>
        ${room.host && n < 6 ? `<div class="lobby-actions">${LOCAL ? "" : `<button class="btn btn--stock btn--sm" data-cmd="add-open">${icon("plus")}Seat for a friend</button>`}<button class="btn btn--stock btn--sm" data-cmd="add-bot">${icon("bot")}Add a bot</button></div>` : ""}
        <div class="start-row">${room.host ? `<button class="btn btn--orange btn--xl" data-cmd="start" ${canStart ? "" : "disabled"}>${icon("play")}${room.mode === "finished" ? "Deal a new game" : "Deal the cards"}</button>${canStart ? "" : '<span class="muted">Fill or remove the empty seats first.</span>'}` : `<span class="muted">Waiting for the host…</span>`}</div>
      </div>
      <div class="lobby-side">
        ${LOCAL ? "" : `<section class="panel"><h2 class="panel__head"><span class="mark"></span><span class="ttl">Invite friends</span></h2><div class="body">
          <div class="linkbox"><code>${esc(link)}</code><button class="btn btn--sm" data-copy="${esc(link)}">${icon("copy")}Copy</button></div>
          ${local && lanLink ? `<div class="linkbox"><code>${esc(lanLink)}</code><button class="btn btn--teal btn--sm" data-copy="${esc(lanLink)}">${icon("copy")}Wi-Fi link</button></div><span class="note">The first link only works on this computer. Friends on your Wi-Fi use the second.</span>` : ""}
        </div></section>`}
        <section class="panel"><h2 class="panel__head"><span class="mark"></span><span class="ttl">House rules</span></h2><div class="body">
          <label class="toggle"><input type="checkbox" data-setting="brutal" ${room.settings.brutal ? "checked" : ""} ${room.host ? "" : "disabled"}> Brutal Mode</label>
          <label class="toggle"><input type="checkbox" data-setting="coach" ${room.settings.coach ? "checked" : ""} ${room.host ? "" : "disabled"}> Coach (show what the bot would do)</label>
          ${LOCAL ? "" : `<label class="toggle"><input type="checkbox" data-setting="public" ${room.settings.public ? "checked" : ""} ${room.host ? "" : "disabled"}> Listed on the home page (otherwise only people with the code can join)</label>`}
          <label class="row" style="gap:10px;font-size:14px">Race to <input class="input" type="number" min="50" max="500" step="10" value="${room.settings.target}" data-setting="target" style="width:96px" ${room.host ? "" : "disabled"}> points</label>
        </div></section>
        <section class="panel"><h2 class="panel__head"><span class="mark"></span><span class="ttl">Table talk</span></h2><div class="body">
          <div class="msgs" style="max-height:200px">${chatHTML(room) || '<span class="empty-note">Say hi.</span>'}</div>
          <form class="chat__form" data-chat><input class="input" type="text" id="lobby-chat-input" maxlength="300" placeholder="Message the table" aria-label="Chat message"><button class="btn btn--teal btn--sm btn--icon" aria-label="Send">${icon("send")}</button></form>
        </div></section>
      </div>
    </div>
  </div>`;
  const ci = $("#lobby-chat-input");
  ci.value = chatVal;
  if (chatFocus) ci.focus();
}

function chatHTML(room) {
  return room.chat.map((m) => {
    const seat = m.seat ?? room.seats.findIndex((s) => s.name === m.name);
    if (m.name === "Server") return `<span class="chat__sys">${esc(m.text)}</span>`;
    const mine = seat >= 0 ? seat === room.you : m.name === S.name;
    return `<div class="msg ${mine ? "msg--me" : ""}">${mine ? "" : seat >= 0 ? avatar(seat, { name: m.name }) : `<span class="avatar sc5"><b>${initial(m.name)}</b></span>`}<div class="msg__bubble"><b>${esc(m.name)}</b>${esc(m.text)}</div></div>`;
  }).join("");
}

// ------------------------------------------------------------------ table: shell
function setTools(html) { $("#tools").innerHTML = html; }

function buildTable(room) {
  document.body.classList.add("in-game");
  S.side.open = false;
  S.side.tab = "log";
  const watch = room.settings.watch;
  app.innerHTML = `
  <div class="game" id="game">
    <main class="board" id="board">
      <div class="arena" aria-hidden="true"></div>
      <div class="toprow" id="toprow"></div>
      <div class="midrow">
        <div class="slot slot-l" id="slot-l"></div>
        <div class="center">
          <div id="announcer"></div>
          <div class="piles"><div class="pile pile--deck" id="deck"></div><div class="pile pile--discard" id="discard"></div></div>
        </div>
        <div class="slot slot-r" id="slot-r"></div>
      </div>
      <div class="me-row" id="me-row"><div id="hand-slot"></div><section class="decision" id="dock" aria-live="polite"></section></div>
    </main>
    <aside class="side" id="side" aria-label="Table details">
      <section class="panel panel--scores">
        <h2 class="panel__head"><span class="mark"></span><span class="ttl" id="scores-ttl">Scoreboard</span><span class="panel__sub" id="scores-sub"></span><button class="btn btn--stock btn--xs btn--icon close-side" data-cmd="side" aria-label="Close panel">${icon("x")}</button></h2>
        <div class="wins__body" id="pane-odds"></div>
      </section>
      <section class="panel panel--log">
        <h2 class="panel__head"><span class="mark"></span><span class="ttl">Table log</span><div class="tabs">${[["log", "Log"], ["deck", "Deck"]].map(([k, l]) => `<button class="${S.side.tab === k ? "on" : ""}" data-tab="${k}">${l}</button>`).join("")}</div></h2>
        <div class="pane ${S.side.tab === "log" ? "on" : ""}" data-pane="log" id="pane-log"><div class="log" id="log"></div></div>
        <div class="pane deck-pane ${S.side.tab === "deck" ? "on" : ""}" data-pane="deck" id="pane-deck"></div>
      </section>
      ${watch ? "" : `<section class="panel panel--chat ${S.chatCollapsed ? "collapsed" : ""}" id="chat-panel">
        <h2 class="panel__head"><span class="mark"></span><span class="ttl">Chat</span><span class="badge-dot" id="chat-badge" hidden></span><button class="panel__toggle" data-cmd="toggle-chat" aria-label="Collapse chat">${icon("chev")}</button></h2>
        <div class="chat__body"><div class="msgs" id="chat-msgs"></div>
          <form class="chat__form" data-chat><input class="input" type="text" id="chat-input" maxlength="300" placeholder="Say something…" aria-label="Chat message"><button class="btn btn--teal btn--sm btn--icon" aria-label="Send">${icon("send")}</button></form></div>
      </section>`}
    </aside>
  </div>`;
}

function setSide(open) {
  S.side.open = open;
  $("#side")?.classList.toggle("open", open);
  if (open) markChatSeen();
  renderTools();
}

function setTab(tab) {
  S.side.tab = tab;
  $$(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  $$(".pane").forEach((p) => p.classList.toggle("on", p.dataset.pane === tab));
  if (tab === "log") { const l = $("#pane-log"); if (l) l.scrollTop = l.scrollHeight; }
}

const sideVisible = () => window.innerWidth > 1180 || window.innerWidth <= 760 || S.side.open;
function markChatSeen() {
  if (S.state && sideVisible() && !S.chatCollapsed) S.chatSeen = S.state.room.chat.length;
  renderChatBadge();
}

// ------------------------------------------------------------------ table: update
function captureRects() {
  const rects = {};
  $$("#board .card[data-k]").forEach((el) => (rects[el.dataset.k] = el.getBoundingClientRect()));
  const deck = $("#deck .card");
  return { rects, deck: deck ? deck.getBoundingClientRect() : null };
}

const bustRevealMs = () => {
  const r = S.state.room;
  return r.settings.watch ? clamp(r.speed * 1500, 450, 1500) : 1500;
};

// A seat that just busted shows its line face up (the new card lands, the pair lights up),
// then turns it face down and crosses it out.
function trackBusts(game) {
  game.players.forEach((pl, p) => {
    if (pl.status !== 2) { delete S.bust[p]; return; }
    if (S.prev.status[p] === undefined || S.prev.status[p] === 2 || S.bust[p]) return;
    S.bust[p] = "reveal";
    const key = S.gameKey;
    setTimeout(() => {
      if (S.bust[p] !== "reveal" || S.gameKey !== key || S.view !== "table") return;
      S.bust[p] = "flip";
      renderSeats();
      S.bust[p] = "done";
    }, bustRevealMs());
  });
}

function updateTable(msg, events) {
  const before = captureRects();
  const kicks = captureKicks(events);
  const focusA = document.activeElement?.dataset?.a;
  trackBusts(msg.game);
  renderTools();
  renderSeats();
  renderCenter(events);
  renderDock();
  renderSide(events);
  runFlights(before, events);
  runKicks(kicks);
  runEffects(events);
  if (focusA !== undefined) $(`#game [data-a="${focusA}"]`)?.focus();
  const { game } = msg;
  game.players.forEach((pl, p) => {
    S.prev.lines[p] = pl.status === 2 ? [] : pl.line.slice();
    S.prev.status[p] = pl.status;
    S.prev.totals[p] = pl.total;
  });
  const mine = game.decision && game.decision.player === msg.room.you && msg.room.mode === "playing";
  document.title = mine ? "▶ Your move · Bust or Bank" : `Table ${msg.room.id} · Bust or Bank`;
}

function renderTools() {
  const st = S.state;
  if (!st || S.view !== "table") return;
  const { room, game } = st;
  const unread = room.chat.length - S.chatSeen;
  setTools(`
    <span class="chip room-chip hide-sm">${icon("key")}Room <b>${esc(room.id)}</b>${room.settings.watch || LOCAL ? "" : `<button class="chip__btn" data-cmd="invite" aria-label="Invite friends">${icon("link")}</button>`}</span>
    <div class="center-ribbon">${ribbon(`Round ${game.round} <small>· to ${room.settings.target}</small>`, "ribbon--mustard")}</div>
    ${room.settings.brutal ? `<span class="chip chip--brutal hide-sm">${icon("flame")}Brutal</span>` : ""}
    <button class="btn btn--stock btn--sm btn--icon side-toggle ${S.side.open ? "on" : ""}" data-cmd="side" title="Scores, log and chat" aria-label="Scores, log and chat">${icon("panel")}${unread > 0 && !room.settings.watch ? `<span class="badge-dot">${unread}</span>` : ""}</button>
    <button class="btn btn--sm btn--icon" data-cmd="sound" title="${Sound.on ? "Mute" : "Unmute"}" aria-label="${Sound.on ? "Mute" : "Unmute"}">${icon(Sound.on ? "sound" : "mute")}</button>
    <button class="btn btn--stock btn--sm btn--icon ${S.menu ? "on" : ""}" data-cmd="menu" title="Table options" aria-label="Table options">${icon("menu")}</button>
    <a class="btn btn--stock btn--sm" href="#/" aria-label="Leave the table">${icon("leave")}<span class="hide-sm">Leave</span></a>`);
}

function decisionContext() {
  const { room, game, thoughts } = S.state;
  const d = game.decision;
  const me = room.you;
  const mine = !!d && d.player === me && me >= 0 && room.mode === "playing";
  const probs = {};
  const brain = !!(thoughts && d && thoughts.player === d.player);
  if (brain) for (const o of thoughts.probs) probs[o.a] = o.p;
  const showOnBoard = brain && (room.settings.watch || me < 0 || (mine && room.settings.coach));
  const topA = brain ? thoughts.probs.reduce((a, b) => (b.p > a.p ? b : a)).a : null;
  const optA = new Set(d ? d.options.map((o) => o.a) : []);
  return {
    d, me, mine, probs, brain, showOnBoard, topA, optA,
    pickPlayers: mine && ["target", "modifier", "flip7", "deliver", "bounty", "dare", "shakedown", "spite"].includes(d.kind),
    pickCards: mine && ["steal", "swap1", "swap2", "discard"].includes(d.kind),
  };
}

// Who handed out each modifier this round (from the log), for the little badge on the card.
function modGivers() {
  const out = {};
  for (const ev of S.log) {
    if (ev.t === "round") for (const k in out) delete out[k];
    else if (ev.t === "modifier" || (ev.t === "delivery" && isMod(ev.card))) out[ev.card] = ev.p;
  }
  return out;
}

function overlapFor(count, me, tight) {
  if (me) return count <= 7 ? -0.02 : -0.22;
  const base = count <= 4 ? -0.12 : count === 5 ? -0.2 : count === 6 ? -0.3 : count === 7 ? -0.38 : -0.46;
  return tight ? Math.max(base - 0.1, -0.52) : base;
}

function lineHTML(p, ctx, size, tight) {
  const pl = S.state.game.players[p];
  const me = size === "card--lg";
  if (pl.status === 2) {
    // busted: first the line is shown face up with the duplicate marked, then it is turned face
    // down and crossed out; modifiers given afterwards still count
    const reveal = S.bust[p] === "reveal";
    const counts = {};
    for (const c of pl.dead) if (isNum(c)) counts[rank(c)] = (counts[rank(c)] || 0) + 1;
    const hasL14 = pl.dead.includes(L14);
    const dupRank = Object.keys(counts).map(Number).find((r) => counts[r] > (r === 14 && hasL14 ? 2 : 1));
    const seen = {};
    const dead = pl.dead.map((c, i) => {
      seen[c] = (seen[c] || 0) + 1;
      const attrs = `data-k="${p}:${c}${seen[c] > 1 ? "b" : ""}" style="--i:${i}"`;
      return reveal ? cardHTML(c, `${size} ${isNum(c) && rank(c) === dupRank ? "is-dup" : ""}`, attrs) : backHTML(size, attrs, true);
    }).join("");
    const late = pl.late_mods.map((c) => cardHTML(c, size, `data-k="${p}:${c}"`)).join("");
    const n = pl.dead.length + pl.late_mods.length;
    return `<div class="line line--busted" style="--ov:${overlapFor(n, me, tight)}">${dead}${late ? `<span class="gap"></span>${late}` : ""}</div>`;
  }
  if (!pl.line.length) return `<div class="line"><span class="empty">${me ? "Your cards land here" : "No cards yet"}</span></div>`;
  const givers = modGivers();
  const seen = {};
  const card = (c) => {
    const a = aCard(p, c);
    const cls = [size];
    seen[c] = (seen[c] || 0) + 1;
    let attrs = `data-k="${p}:${c}${seen[c] > 1 ? "b" : ""}"`;
    let key = "";
    if (ctx.pickCards && ctx.optA.has(a)) {
      cls.push("pickable");
      const k = ++S.pickKey;
      const label = describeOption(ctx.d.options.find((o) => o.a === a), ctx.d);
      attrs += ` data-a="${a}" tabindex="0" role="button" aria-label="${esc(label)}"${k <= 9 ? ` data-key="${k}"` : ""}`;
      if (k <= 9) key = `<span class="kbd card__key">${k}</span>`;
    }
    if (ctx.d && ctx.d.kind === "swap2" && ctx.d.first && ctx.d.first.player === p && ctx.d.first.card === c) cls.push("chosen");
    let html = cardHTML(c, cls.join(" "), attrs);
    let extra = key;
    if (isMod(c) && givers[c] !== undefined && givers[c] !== p && size !== "card--sm") extra += avatar(givers[c], { cls: "from" }).replace('aria-hidden="true"', `title="Given by ${esc(seatName(givers[c]))}"`);
    const pr = ctx.probs[a];
    if (ctx.showOnBoard && pr !== undefined && pr >= 0.02) extra += `<span class="pct">${pct(pr)}</span>`;
    if (extra) html = html.replace(/<\/div>$/, `${extra}</div>`);
    return html;
  };
  const nums = pl.line.filter(isNum), mods = pl.line.filter((c) => !isNum(c));
  const picking = ctx.pickCards && pl.line.some((c) => ctx.optA.has(aCard(p, c)));
  const many = me && pl.line.length > 7;
  return `<div class="line ${picking ? "picking" : ""} ${many ? "many" : ""}" style="--ov:${overlapFor(pl.line.length, me, tight)}">${nums.map(card).join("")}${mods.length ? `<span class="gap"></span>${mods.map(card).join("")}` : ""}</div>`;
}

function statusHTML(p, ctx, me) {
  const { game, room } = S.state;
  const pl = game.players[p];
  const away = awayFor(p);
  if (away != null && !seatInfo(p).sub && room.mode === "playing") return `<span class="status status--away">${icon("wifi")}Away ${clock(away)}</span>`;
  if (ctx.d && ctx.d.player === p && room.mode === "playing") return `<span class="status status--turn">${icon("play")}${me ? "Your turn" : "Their turn"}</span>`;
  if (game.flip7_player === p) return `<span class="status status--flip7">${icon("star")}Flip 7!</span>`;
  if (pl.status === 2) return `<span class="status status--busted">${icon("skull")}Busted</span>`;
  if (pl.status === 1) return pl.frozen ? `<span class="status status--frozen">${icon("snow")}Frozen</span>` : `<span class="status status--stayed">${icon("snow")}Stayed</span>`;
  return `<span class="status">${icon("hourglass")}In play</span>`;
}

function ptsHTML(pl) {
  if (pl.status === 2) return `<div class="pts ${pl.projected < 0 ? "pts--neg" : ""}"><small>Bust</small><b>${signed(pl.projected)}</b></div>`;
  if (pl.status === 1) return `<div class="pts pts--banked"><small>${icon("snow")}Banked</small><b>${pl.projected}</b></div>`;
  return `<div class="pts ${pl.projected < 0 ? "pts--neg" : ""}"><small>Round</small><b>${signed(pl.projected)}</b></div>`;
}

function metaHTML(p, me, ctx) {
  const { game, room } = S.state;
  const pl = game.players[p];
  const tags = [];
  const myTurn = ctx.d && ctx.d.player === p && ctx.d.kind === "hit_stay" && me;
  if (S.odds && pl.status === 0 && pl.p_bust != null && pl.line.length && !myTurn) tags.push(`<span class="tag tag--risk ${pl.p_bust > 0.3 ? "hi" : ""}">${icon("skull")}bust ${pct(pl.p_bust)}</span>`);
  if (pl.bounty) tags.push(`<span class="tag tag--bounty">${icon("flag")}Bounty${pl.bounty > 1 ? ` ×${pl.bounty}` : ""} · +${10 * pl.bounty}</span>`);
  if (pl.dare) tags.push(`<span class="tag tag--task">${icon("flame")}Must hit ×${pl.dare}</span>`);
  if (pl.spite) tags.push(`<span class="tag tag--spite">${icon("skull")}Spite −${pl.spite}</span>`);
  for (const t of game.tasks || []) {
    if (t.p !== p) continue;
    if (t.t === "queue" && t.queue.length) tags.push(`<span class="tag tag--task">Up next: ${t.queue.map(cardName).join(", ")}</span>`);
    else if (t.t === "jom") tags.push(`<span class="tag tag--task">Stays after this card</span>`);
  }
  return tags.join("");
}

function leaderOf() {
  const totals = S.state.game.players.map((pl) => pl.total);
  const top = Math.max(...totals);
  return top > 0 && totals.filter((t) => t === top).length === 1 ? totals.indexOf(top) : -1;
}

function seatHTML(p, ctx, { me = false, tight = false } = {}) {
  const { room, game } = S.state;
  const pl = game.players[p], seat = room.seats[p];
  const cls = ["seat", me ? "seat--me" : "seat--opp", `sc${p % 6}`];
  if (ctx.d && ctx.d.player === p && room.mode === "playing") cls.push("is-turn");
  if (pl.status === 2) cls.push("is-busted"); else if (pl.status === 1) cls.push("is-stayed");
  if (S.bust[p] === "reveal") cls.push("bust-reveal");
  if (S.bust[p] === "flip") cls.push("just-busted");
  if (S.prev.status[p] === 0 && pl.status === 1) cls.push("just-stayed");
  if (game.flip7_player === p) cls.push("is-flip7");
  let attrs = `data-seat="${p}"`;
  if (ctx.pickPlayers && ctx.optA.has(aPlayer(p))) { cls.push("target"); attrs += ` data-a="${aPlayer(p)}"`; }
  const tp = ctx.probs[aPlayer(p)];
  const showT = (ctx.pickPlayers && room.settings.coach) || (ctx.showOnBoard && ["target", "modifier", "flip7", "deliver", "bounty", "dare", "shakedown", "spite"].includes(ctx.d?.kind));
  const f4 = (game.tasks || []).find((t) => t.t === "flip4" && t.p === p);
  if (f4) cls.push("is-flip4");
  const tpct = f4 ? `<span class="seat__flip4">${icon("layers")}Flip Four <b>${4 - f4.left}/4</b></span>`
    : showT && tp !== undefined ? `<span class="tpct">${pct(tp)}</span>` : "";
  const tags = [];
  if (seat.kind === "bot") tags.push(`<span class="tag">${icon("bot")}${esc(botTag(seat.bot_id))}</span>`);
  else if (seat.sub) tags.push(`<span class="tag tag--task">${icon("bot")}Bot playing</span>`);
  else if (me) tags.push(`<span class="tag tag--light">You</span>`);
  else tags.push(`<span class="tag tag--light">${icon("users")}${seat.online ? "Friend" : "Away"}</span>`);
  if (leaderOf() === p) tags.push(`<span class="tag tag--lead">${icon("star")}Leader</span>`);
  const av = avatar(p, { cls: "seat__av", dealer: game.dealer === p, online: seat.kind === "human" && !me ? seat.online : undefined });
  const total = `<span class="total">${icon("trophy")}<b data-total="${p}">${pl.total}</b><small>/${room.settings.target}</small></span>`;
  const meta = metaHTML(p, me, ctx);
  return `<article class="${cls.join(" ")}" ${attrs} aria-label="${esc(seat.name)}, ${pl.total} points">
    ${tpct}${statusHTML(p, ctx, me)}
    <header class="seat__head">${av}<div class="seat__id"><h3 class="seat__name">${esc(seat.name)}</h3><div class="seat__tags">${tags.join("")}</div></div>${total}${me ? ptsHTML(pl) : ""}</header>
    <div class="seat__body">${lineHTML(p, ctx, me ? "card--lg" : "card--sm", tight)}${me ? "" : ptsHTML(pl)}</div>
    ${meta ? `<div class="seat__meta">${meta}</div>` : ""}
  </article>`;
}

// Opponent slots by count, clockwise from the bottom seat: left, top-left, top, top-right, right.
const SLOTS = [[], ["t"], ["l", "r"], ["l", "t", "r"], ["l", "tl", "tr", "r"], ["l", "tl", "t", "tr", "r"]];

function renderSeats() {
  const { room, game } = S.state;
  const ctx = decisionContext();
  S.pickKey = 0;
  const n = game.n;
  const me = meIdx();
  const bottom = me >= 0 ? me : 0;
  const others = Array.from({ length: n - 1 }, (_, k) => (bottom + k + 1) % n);
  const slots = SLOTS[others.length];
  const at = {};
  others.forEach((p, i) => (at[slots[i]] = p));
  const top = ["tl", "t", "tr"].filter((s) => at[s] !== undefined);
  const tight = top.length === 3;
  const toprow = $("#toprow");
  toprow.className = `toprow ${top.length === 2 ? "two" : ""}`;
  toprow.innerHTML = top.map((s) => seatHTML(at[s], ctx, { tight })).join("");
  $("#slot-l").innerHTML = at.l !== undefined ? seatHTML(at.l, ctx) : "";
  $("#slot-r").innerHTML = at.r !== undefined ? seatHTML(at.r, ctx) : "";
  $("#hand-slot").innerHTML = seatHTML(bottom, ctx, { me: me >= 0 });
  const meRow = $("#me-row");
  if (meRow) $("#board").style.setProperty("--me-h", `${meRow.offsetHeight}px`);
}

function renderCenter(events) {
  const { game } = S.state;
  const deckN = game.deck_size, discN = game.discard_size;
  const deck = $("#deck"), disc = $("#discard");
  deck.className = `pile pile--deck ${deckN < 3 ? "low" : ""}`;
  deck.innerHTML = `<div class="pile__card">${deckN ? backHTML() : '<div class="slot-empty"></div>'}${deckN ? `<span class="pile__count" aria-label="${deckN} cards left">${deckN}</span>` : ""}</div><span class="pile__label">Draw</span>`;
  const top = game.discard_top;
  disc.innerHTML = `<div class="pile__card">${discN && top != null ? cardHTML(top) : '<div class="slot-empty"></div>'}</div><span class="pile__label">Discard${discN ? ` · ${discN}` : ""}</span>`;
  if (events.length) {
    let best = null, bp = -1;
    for (const ev of events) { const p = PRIORITY[ev.t] ?? 0; if (p >= bp) { best = ev; bp = p; } }
    const a = best && announceFor(best);
    if (a) S.announce = { ...a, id: Math.random().toString(36).slice(2), delay: best.t === "bust" && flightsAllowed() ? 550 : 0 };
  }
  const el = $("#announcer");
  const A = S.announce || { label: "Get ready", title: `Round ${game.round}`, tone: "ribbon--mustard", calm: true, id: "start" };
  if (el.dataset.id === A.id) return;  // don't restart the animation on unrelated updates
  el.dataset.id = A.id;
  const av = A.p !== undefined ? avatar(A.p) : "";
  const show = () => { if (el.dataset.id === A.id) el.innerHTML = `<div class="announce ${A.calm ? "calm" : ""}" role="status"><span class="announce__label"><i></i>${A.label || "Last play"}</span>${ribbon(`${av}${A.title}`, A.tone || "")}${A.sub ? `<p class="announce__sub">${A.sub}</p>` : ""}</div>`; };
  if (A.delay) setTimeout(show, A.delay); else show();
}

function describeOption(o, d) {
  const n = (i) => seatName(i);
  if (d.kind === "pay") return o.a === 0 ? `Pay ${n(d.by)} 10` : "Take a card";
  if (o.a === 0) return "Stay";
  if (o.a === 1) return "Hit";
  if (o.card === undefined) {
    if (d.kind === "flip7") return o.player === d.player ? "+15 for themselves" : `−15 to ${n(o.player)}`;
    if (d.kind === "spite") return `Spite → ${n(o.player)}`;
    return `${cardName(d.card)} → ${o.player === d.player ? "self" : n(o.player)}`;
  }
  const c = `${o.player === d.player ? "own" : n(o.player) + "'s"} ${cardName(o.card)}`;
  return { steal: `Steal ${c}`, swap1: `Swap ${c} …`, swap2: `… for ${c}`, discard: `Discard ${c}` }[d.kind] || c;
}

function promptFor(d, mine) {
  const { game } = S.state;
  const nm = esc(seatName(d.player));
  const card = d.card >= 0 ? cardName(d.card) : "";
  // a card taken because of Just One More: it is resolved as usual, then the player has to stay
  const jom = (game.tasks || []).some((t) => t.t === "jom" && t.p === d.player) && d.kind !== "hit_stay";
  if (mine && jom) {
    const [t, sub] = promptForMine(d, card);
    return [t, `This is your <b>Just One More</b> card. ${sub} After that you have to stay.`];
  }
  if (mine) return promptForMine(d, card);
  if (jom) {
    const [t, sub] = promptForOthers(d, nm, card);
    return [t, `${sub} · their Just One More card, then they stay`];
  }
  return promptForOthers(d, nm, card);
}

function promptForMine(d, card) {
  switch (d.kind) {
    case "hit_stay": return ["Hit or Stay?", ""];
    case "target": return d.card === JOM ? ["Just One More!", "Pick who takes exactly one more card and then has to stay."] : ["Flip Four!", "Pick who has to take the next four cards."];
    case "modifier": return [`You drew ${card}`, d.card === DIV2 ? "Hand it to someone: it halves their number total." : "Hand it to someone: it comes off their round score."];
    case "steal": return ["Steal!", "Take any card from another player's line. Click a glowing card."];
    case "swap1": return ["Swap!", "Pick the first card. The second must belong to someone else."];
    case "swap2": return ["Swap: second card", `Pick a card to trade for ${d.first.player === d.player ? "your" : esc(seatName(d.first.player)) + "'s"} ${cardName(d.first.card)}.`];
    case "discard": return ["Discard!", "Throw away any card on the table, your own included."];
    case "flip7": return ["Flip 7!", "Take +15 for yourself, or make someone lose 15."];
    case "deliver": return [`Special Delivery: ${card}`, isNum(d.card) ? "Choose who gets it. If they already hold that number, they bust." : "Choose who gets it."];
    case "bounty": return ["Bounty!", "Put it on a rival. If someone's card busts them this round, that player banks +10."];
    case "dare": return ["Double Dare!", "Pick a rival who's still drawing: they must hit on their next two turns."];
    case "shakedown": return ["Shakedown!", "Pick a rival: they pay you 10 points, or take a card instead."];
    case "pay": return [`${esc(seatName(d.by))} shook you down`, "Pay 10 points, or take a card instead."];
    case "spite": return ["Spite!", "You busted holding Spite. Pick who loses 10 points this round."];
  }
  return ["", ""];
}

function promptForOthers(d, nm, card) {
  switch (d.kind) {
    case "hit_stay": return [`${nm}'s turn`, "Hit or stay?"];
    case "target": return [`${nm} drew ${card}`, "Choosing a target"];
    case "modifier": return [`${nm} drew ${card}`, "Choosing who gets it"];
    case "steal": return [`${nm} is stealing`, "Choosing a card"];
    case "swap1": case "swap2": return [`${nm} is swapping`, "Choosing cards"];
    case "discard": return [`${nm} is discarding`, "Choosing a card"];
    case "flip7": return [`${nm} flipped 7!`, "+15 for themselves, or −15 for someone?"];
    case "deliver": return [`${nm} flipped ${card}`, "Special Delivery: choosing who gets it"];
    case "bounty": return [`${nm} drew a Bounty`, "Choosing who to put it on"];
    case "dare": return [`${nm} drew Double Dare`, "Choosing who to dare"];
    case "shakedown": return [`${nm} drew Shakedown`, "Choosing who to shake down"];
    case "pay": return [`${nm} is being shaken down`, "Pay 10 or take a card?"];
    case "spite": return [`${nm} busted holding Spite`, "Choosing who loses 10"];
  }
  return ["", ""];
}

function gaugeSVG(v) {
  v = clamp(v, 0, 1);
  const th = Math.PI * (1 - v), cx = (60 + 48 * Math.cos(th)).toFixed(1), cy = (58 - 48 * Math.sin(th)).toFixed(1);
  const arc = 'd="M12 58A48 48 0 0 1 108 58" fill="none" stroke-linecap="round"';
  return `<svg class="gauge__svg" viewBox="0 0 120 66" aria-hidden="true"><path ${arc} stroke="#1E110A" stroke-width="16"/><path ${arc} stroke="#5B3A24" stroke-width="10"/><path ${arc} stroke="url(#gaugeGrad)" stroke-opacity=".3" stroke-width="10"/><path ${arc} stroke="url(#gaugeGrad)" stroke-width="10" pathLength="100" stroke-dasharray="${(v * 100).toFixed(1)} 200"/><circle cx="${cx}" cy="${cy}" r="7" fill="#FFF8EA" stroke="#1E110A" stroke-width="2.5"/></svg>`;
}

// What picking a card would do, shown while a selectable card is hovered or focused.
function pickPreview(a) {
  const { game, room } = S.state;
  const d = game.decision;
  const o = d && d.options.find((x) => x.a === a);
  if (!o || o.card === undefined) return "";
  const who = (q) => (q === room.you ? "you" : esc(seatName(q)));
  const lineOf = (q) => game.players[q].line;
  const busts = (q, without, add) => isNum(add) && bustingKinds(lineOf(q).filter((c, i, l) => i !== l.indexOf(without))).has(add);
  let text = esc(describeOption(o, d));
  if (d.kind === "steal" && busts(d.player, -1, o.card)) text += " — <b>you'd bust</b>";
  if (d.kind === "swap2" && d.first) {
    const { player: q1, card: c1 } = d.first;
    const hit = [];
    if (busts(q1, c1, o.card)) hit.push(who(q1));
    if (busts(o.player, o.card, c1)) hit.push(who(o.player));
    text = `${esc(cardName(c1))} (${who(q1)}) ⇄ ${esc(cardName(o.card))} (${who(o.player)})${hit.length ? ` — <b>${hit.join(" and ")} would bust</b>` : ""}`;
  }
  return text;
}

function hitStayHTML(ctx, coach) {
  const { game } = S.state;
  const { d, probs, topA } = ctx;
  const pl = game.players[d.player];
  const has = (a) => d.options.some((o) => o.a === a);
  const nums = pl.line.filter(isNum);
  const danger = bustingKinds(pl.line);
  const bustN = [...danger].reduce((s, c) => s + (game.deck_counts[c] || 0), 0);
  const risk = pl.p_bust ?? 0;
  const pips = Array.from({ length: 7 }, (_, i) => (i < nums.length
    ? `<span class="f7__pip ${isLite(nums[i]) ? "lite" : ""}" style="--c:${numColor(nums[i])}">${rank(nums[i])}</span>`
    : '<span class="f7__pip f7__pip--empty">?</span>')).join("");
  const left = Math.max(0, 7 - nums.length);
  const stats = `<div class="decision__stats">
      <div class="well"><div class="well__title">Bust risk</div>
        <div class="gauge">${gaugeSVG(risk)}<div class="gauge__val"><b>${pl.line.length ? pct(risk) : "0%"}</b><small>${pl.line.length ? (game.deck_size ? `<strong>${bustN} of ${game.deck_size}</strong> cards<br>bust you` : "deck reshuffles<br>next draw") : "first card<br>can't bust"}</small></div></div></div>
      <div class="well"><div class="well__title">Flip 7 <em>+15 bonus</em></div><div class="f7" aria-label="${nums.length} of 7 numbers">${pips}</div>
        <div class="f7__more">${left ? `Flip 7 in <span>${left}</span> more` : "Flip 7!"}<small>${left ? "numbers" : ""}</small></div></div>
    </div>`;
  let coachRow = "";
  const q = S.state.thoughts?.q;
  const bestA = q ? d.options.map((o) => o.a).reduce((x, y) => ((q[y] ?? -1) > (q[x] ?? -1) ? y : x)) : topA;
  if (coach && q) {
    coachRow = `<div class="coach"><span class="coach__ico">${icon("bot")}</span><span class="coach__txt"><small>Coach · win chance by move</small>${d.options.map((o) => `${o.a === 1 ? "Hit" : "Stay"} <b>${pct(q[o.a] ?? 0)}</b>`).join(" · ")}</span></div>`;
  } else if (coach) {
    const best = d.options.find((o) => o.a === topA);
    if (best) coachRow = `<div class="coach"><span class="coach__ico">${icon("bot")}</span><span class="coach__txt"><small>Coach · neural net</small>Bots would <b>${best.a === 1 ? "HIT" : "STAY"}</b></span><span class="coach__pct">${pct(probs[topA])}</span></div>`;
  }
  const pick = (a) => (coach && a === bestA ? `<span class="pick">${icon("bot")}Coach pick</span>` : "");
  const hit = has(1) ? `<button class="btn btn--act btn--orange" data-a="1">${pick(1)}<span class="btn__row">HIT <span class="kbd">H</span></span><span class="btn__sub">${pl.line.length ? "Flip one more card" : "Take your first card"}</span></button>` : "";
  const stay = has(0) ? `<button class="btn btn--act btn--teal" data-a="0">${pick(0)}<span class="btn__row">STAY <span class="kbd">S</span></span><span class="btn__sub">Bank ${signed(pl.projected)} ${icon("arrow")} total ${pl.total + pl.projected}</span></button>` : "";
  const why = !has(0) && pl.line.length ? `<p class="decision__text">${pl.line.includes(0) ? "You hold <b>The Zero</b>: you can't stay." : "You have to take a card."}</p>` : "";
  return `${stats}${coachRow}${why}<div class="decision__actions ${hit && stay ? "" : "one"}">${hit}${stay}</div>`;
}

function renderDock() {
  const { room, game } = S.state;
  const ctx = decisionContext();
  const { d, mine, probs, topA, brain } = ctx;
  const dock = $("#dock");
  const coach = room.settings.coach && mine && brain;
  let title = "", tone = "ribbon--mustard", body = "";
  if (room.mode === "finished" || game.over) {
    title = "Game over";
    const names = game.winners.map((w) => esc(seatName(w))).join(" & ");
    body = `<p class="decision__text"><b>${names}</b> won the game.</p>
      <div class="decision__actions ${room.host || room.settings.watch ? "" : "one"}">${room.host || room.settings.watch
        ? `<button class="btn btn--orange btn--lg" data-cmd="start">${icon("play")}${room.settings.watch ? "Run it back" : "Rematch"}</button>${room.host && !room.settings.watch ? `<button class="btn btn--stock btn--lg" data-cmd="stop">Back to lobby</button>` : `<a class="btn btn--stock btn--lg" href="#/">Leave</a>`}`
        : '<p class="decision__text">Waiting for the host…</p>'}</div>`;
  } else if (!d) {  // the server pauses after each Flip Four card and on each round's final table
    const f4 = game.holding === "draw" && (game.tasks || []).find((t) => t.t === "flip4");
    if (f4) {
      title = "Flip Four!";
      tone = "ribbon--orange";
      const who = f4.p === room.you && !room.settings.watch ? "You take" : `${esc(seatName(f4.p))} takes`;
      body = `<p class="decision__text">${who} four cards, one at a time.<br><b>${4 - f4.left} of 4</b> drawn${f4.queue.length ? ` · then ${f4.queue.map(cardName).join(", ")}` : ""}</p>`;
    } else {
      title = "Round over";
      body = `<p class="decision__text">Scoring the round…</p>`;
    }
  } else if (d) {
    const [t, sub] = promptFor(d, mine);
    title = t;
    const bot = room.seats[d.player]?.kind === "bot";
    if (mine && d.kind === "hit_stay") {
      tone = "ribbon--mustard";
      body = hitStayHTML(ctx, coach);
    } else if (mine && d.kind === "pay") {
      tone = "ribbon--plum";
      const pl = game.players[d.player];
      const has = (a) => d.options.some((o) => o.a === a);
      body = `<p class="decision__text">${sub}</p><div class="decision__actions ${has(0) && has(1) ? "" : "one"}">
        ${has(0) ? `<button class="btn btn--act btn--teal" data-a="0"><span class="btn__row">PAY 10 <span class="kbd">S</span></span><span class="btn__sub">${esc(seatName(d.by))} gets the points</span></button>` : ""}
        ${has(1) ? `<button class="btn btn--act btn--orange" data-a="1"><span class="btn__row">DRAW <span class="kbd">H</span></span><span class="btn__sub">Take a card instead · bust risk ${pct(pl.p_bust ?? 0)}${pl.bounty ? " · a bust pays your Bounty" : ""}</span></button>` : ""}</div>`;
    } else if (mine && ["target", "modifier", "flip7", "deliver", "bounty", "dare", "shakedown", "spite"].includes(d.kind)) {
      tone = d.kind === "flip7" ? "ribbon--mustard" : "ribbon--orange";
      body = `<p class="decision__text">${sub}</p><div class="pick-grid">${d.options.map((o, i) => {
        const self = o.player === room.you;
        const label = d.kind === "flip7" ? (self ? "+15 for me" : `−15 to ${esc(seatName(o.player))}`) : self ? "Me" : esc(seatName(o.player));
        const qv = S.state.thoughts?.q?.[o.a];
        const pc = coach && qv !== undefined ? `<span class="pct">${pct(qv)} win</span>` : coach && probs[o.a] !== undefined ? `<span class="pct">${pct(probs[o.a])}</span>` : "";
        return `<button class="btn ${d.kind === "flip7" && self ? "btn--teal" : "btn--stock"} pick-btn" data-a="${o.a}" data-key="${i + 1}">${avatar(o.player)}<span>${label}</span>${pc}<span class="kbd">${i + 1}</span></button>`;
      }).join("")}</div>`;
    } else if (mine) {
      tone = "ribbon--orange";
      let hint = "";
      if (coach) {
        const q = S.state.thoughts?.q;
        const a = q ? d.options.map((o) => o.a).reduce((x, y) => ((q[y] ?? -1) > (q[x] ?? -1) ? y : x)) : topA;
        const best = d.options.find((o) => o.a === a);
        if (best) hint = `<div class="coach"><span class="coach__ico">${icon("bot")}</span><span class="coach__txt"><small>Coach · ${q ? "best win chance" : "neural net"}</small><b>${esc(describeOption(best, d))}</b></span><span class="coach__pct">${pct(q ? q[a] : probs[topA])}</span></div>`;
      }
      body = `<p class="decision__text">${sub}</p>${hint}<p class="decision__text" id="pick-preview"><b>Click a glowing card</b>, or press its number.</p>`;
    } else if (awayFor(d.player) != null && !seatInfo(d.player).sub) {
      const away = awayFor(d.player), nm = esc(seatName(d.player));
      tone = "ribbon--ink";
      title = `Waiting for ${nm}`;
      const allowed = (room.can_sub || []).includes(d.player) || (room.host && away >= room.grace);
      body = `<p class="decision__text">${nm} lost their connection <b>${clock(away)}</b> ago. Their seat is kept for them.</p>
        ${allowed ? `<div class="decision__actions one"><button class="btn btn--stock btn--lg" data-cmd="substitute" data-seat="${d.player}">${icon("bot")}Let a bot play for ${nm}</button></div>`
          : room.host ? `<p class="decision__text">You can let a bot take over in <b>${clock(Math.max(0, room.grace - away))}</b>.</p>` : ""}`;
    } else {
      tone = "ribbon--ink";
      title = `${title}${bot || seatInfo(d.player).sub ? '<span class="thinking"><i></i><i></i><i></i></span>' : ""}`;
      if (brain && (room.settings.watch || room.you < 0)) {
        const top = d.options.map((o) => ({ o, p: probs[o.a] ?? 0 })).sort((a, b) => b.p - a.p).slice(0, 3);
        body = `<p class="decision__text">${sub}<br>How the RL network rates the options:</p><div class="reads">${top.map(({ o, p }) => `<div class="read ${o.a === topA ? "top" : ""}"><span>${esc(describeOption(o, d))}</span><b>${pct(p)}</b><div class="bar"><i style="width:${(p * 100).toFixed(1)}%"></i></div></div>`).join("")}</div>`;
      } else {
        const me = room.you >= 0 ? game.players[room.you] : null;
        const mineLine = me ? (me.status === 2 ? "You busted this round." : me.status === 1 ? `You banked <b>${me.projected}</b> this round.` : `You're on <b>${signed(me.projected)}</b> this round.`) : "";
        body = `<p class="decision__text">${sub}${mineLine ? `<br>${mineLine}` : ""}</p>`;
      }
    }
  }
  if (room.settings.watch) {
    body += `<div class="transport">
      <button class="btn btn--stock btn--sm btn--icon" data-cmd="pause" title="${room.paused ? "Resume" : "Pause"}" aria-label="${room.paused ? "Resume" : "Pause"}">${icon(room.paused ? "play" : "pause")}</button>
      ${room.paused ? `<button class="btn btn--stock btn--sm btn--icon" data-cmd="step" title="Next move" aria-label="Next move">${icon("step")}</button>` : ""}
      <label class="speed">Pace ${room.speed.toFixed(1)}s<input type="range" min="0.1" max="3" step="0.1" value="${room.speed}" data-input="speed" aria-label="Pace"></label></div>`;
  }
  if (room.you >= 0 && seatInfo(room.you).sub && room.mode === "playing") {
    body = `<div class="coach"><span class="coach__ico">${icon("bot")}</span><span class="coach__txt"><small>While you were away</small>${esc(seatInfo(room.you).sub)} is playing for you</span><button class="btn btn--teal btn--sm" data-cmd="reclaim">Take your seat back</button></div>${body}`;
  }
  dock.className = `decision ${mine ? "mine" : "idle"}`;
  dock.innerHTML = `${title ? `<div class="decision__ribbon">${ribbon(title, tone)}</div>` : ""}${body}`;
  if (mine && S.lastMine !== game.seq) { S.lastMine = game.seq; Sound.play("turn"); }
}

function renderSide(events) {
  const { room, game, thoughts } = S.state;
  const ctx = decisionContext();
  const target = room.settings.target;
  const lead = leaderOf();
  const winShown = !!thoughts;
  $("#scores-ttl").textContent = winShown ? "Win chance" : "Scoreboard";
  $("#scores-sub").textContent = winShown ? "AI estimate" : `first to ${target}`;
  let html = "";
  if (winShown) {
    const order = game.players.map((_, p) => p).sort((a, b) => thoughts.win[b] - thoughts.win[a]);
    html += `<div class="winbar" role="img" aria-label="${order.map((p) => `${esc(seatName(p))} ${pct(thoughts.win[p])}`).join(", ")}">${order.map((p) => `<span class="sc${p % 6}" style="--w:${(thoughts.win[p] * 100).toFixed(1)}%">${thoughts.win[p] >= 0.12 ? pct(thoughts.win[p]) : ""}</span>`).join("")}</div>`;
  }
  html += `<div class="scores">${game.players.map((pl, p) => ({ pl, p })).sort((a, b) => b.pl.total - a.pl.total || a.p - b.p).map(({ pl, p }) => `
    <div class="score-row sc${p % 6} ${p === room.you && !room.settings.watch ? "is-you" : ""} ${p === lead ? "is-lead" : ""}">${avatar(p)}
      <div class="nm"><span>${p === room.you && !room.settings.watch ? "You" : esc(seatName(p))}</span><div class="prog"><i style="width:${clamp(pl.total / target, 0, 1) * 100}%"></i></div></div>
      <span class="tot">${pl.total}</span>${winShown ? `<span class="win">${pct(thoughts.win[p])}</span>` : ""}</div>`).join("")}</div>`;
  if (ctx.d && ctx.brain && (room.settings.watch || room.you < 0 || room.settings.coach || room.mode === "finished")) {
    html += `<div class="opts"><h4>${esc(seatName(ctx.d.player))}'s options, as the RL bot sees them</h4>${ctx.d.options.map((o) => ({ o, p: ctx.probs[o.a] ?? 0 })).sort((a, b) => b.p - a.p).slice(0, 5).map(({ o, p }) => `<div class="optrow ${o.a === ctx.topA ? "top" : ""}"><span>${esc(describeOption(o, ctx.d))}</span><b>${pct(p)}</b></div>`).join("")}</div>`;
  }
  $("#pane-odds").innerHTML = html;

  const me = room.you;
  const focus = me >= 0 && !room.settings.watch && game.players[me].status !== 2 ? me : ctx.d ? ctx.d.player : -1;
  const danger = focus >= 0 && game.players[focus].status !== 2 ? bustingKinds(game.players[focus].line) : new Set();
  const dc = game.deck_counts;
  const cell = (c, l) => `<div class="cnt ${danger.has(c) && dc[c] ? "danger" : ""} ${dc[c] ? "" : "gone"}" title="${esc(cardName(c))}: ${dc[c]} of ${COUNTS[c]} left"><span class="l">${l}</span><b>${dc[c]}</b></div>`;
  $("#pane-deck").innerHTML = `
    <h4>Numbers left in the deck</h4><div class="counter">${[0, 1, 2, 3, 4, 5, 6, 7, U7, 8, 9, 10, 11, 12, 13, 14, L14].map((c) => cell(c, c === U7 ? "F7" : c === L14 ? "L14" : c)).join("")}</div>
    <p class="counter-note">${focus >= 0 && game.players[focus].status !== 2 ? `Red: cards that would bust <b>${focus === me ? "you" : esc(seatName(focus))}</b>, ${game.players[focus].p_bust != null ? pct(game.players[focus].p_bust) : "–"} of what's left.` : ""}${game.deck_size === 0 ? " The deck is empty: the next card comes from the reshuffled discards." : ""}</p>
    <h4>Modifiers & actions left</h4><div class="counter">${[17, 18, 19, 20, 21, 22].map((c) => cell(c, MOD_TEXT[c])).join("")}${cell(JOM, "+1")}${cell(FLIP4, "×4")}</div>
    <div class="counter" style="margin-top:4px">${cell(SWAP, "Swp")}${cell(STEAL, "Stl")}${cell(DISCARD, "Dsc")}${cell(DELIVERY, "Dlv")}${cell(BOUNTY, "Bty")}${cell(DARE, "Dare")}${cell(SHAKEDOWN, "Shk")}${cell(ROBIN, "Rob")}</div>
    <div class="counter" style="margin-top:4px">${cell(TAX, "Tax")}${cell(SPITE, "Spt")}</div>
    <p class="counter-note" style="padding-bottom:12px">${game.deck_size} cards in the deck, ${game.discard_size} in the discard pile.</p>`;

  const logEl = $("#log"), pane = $("#pane-log");
  const nowKey = `${S.log.length}:${ctx.mine ? game.seq : ""}`;
  if (logEl.dataset.k !== nowKey) {
    const atBottom = pane.scrollHeight - pane.scrollTop - pane.clientHeight < 40;
    const rows = S.log.map((ev) => ({ ev, f: fmtEvent(ev) })).filter((r) => r.f).slice(-220).map(({ ev, f }) => {
      if (f.cls === "round") return `<div class="ev round">${f.html}</div>`;
      const [ic, col] = EV_ICON[ev.t] || ["plus", "var(--ink-2)"];
      return `<div class="ev ${f.cls || ""}"><span class="ev__ico" style="--ic:${col}">${icon(ic)}</span><span>${f.html}</span></div>`;
    });
    if (ctx.mine) rows.push(`<div class="ev is-now"><span class="ev__ico" style="--ic:var(--orange)">${icon("play")}</span><span><b>Your turn</b> — ${esc(promptFor(ctx.d, true)[0])}</span></div>`);
    logEl.innerHTML = rows.join("");
    logEl.dataset.k = nowKey;
    if (atBottom || !logEl.dataset.init) { pane.scrollTop = pane.scrollHeight; logEl.dataset.init = "1"; }
  }
  const msgs = $("#chat-msgs");
  if (msgs && msgs.dataset.n !== String(room.chat.length)) {
    msgs.innerHTML = chatHTML(room) || '<span class="chat__sys">Say hi to the table.</span>';
    msgs.dataset.n = room.chat.length;
    msgs.scrollTop = msgs.scrollHeight;
  }
  markChatSeen();
}

function renderChatBadge() {
  const b = $("#chat-badge");
  if (!b || !S.state) return;
  const unread = S.state.room.chat.length - S.chatSeen;
  b.hidden = !(unread > 0);
  b.textContent = unread;
}

// ------------------------------------------------------------------ animation
function flightsAllowed() {
  const r = S.state.room;
  return !reduceMotion() && !(r.settings.watch && r.speed < 0.35) && document.visibilityState === "visible";
}

function fly(fromRect, toEl, faceUp, delay) {
  const to = toEl.getBoundingClientRect();
  if (!to.width) return;
  let ghost;
  if (faceUp) {
    ghost = toEl.cloneNode(true);
    ghost.classList.remove("pickable", "chosen");
  } else {
    ghost = document.createElement("div");
    ghost.className = "card card--back";
    ghost.innerHTML = BACK_EMBLEM;
  }
  ghost.classList.add("ghost-card");
  ghost.style.cssText += `;left:${to.left}px;top:${to.top}px;width:${to.width}px;height:${to.height}px;--h:${to.height}px`;
  document.body.appendChild(ghost);
  toEl.style.visibility = "hidden";
  const dx = fromRect.left + fromRect.width / 2 - (to.left + to.width / 2);
  const dy = fromRect.top + fromRect.height / 2 - (to.top + to.height / 2);
  const s = fromRect.width / to.width;
  const anim = ghost.animate(
    [{ transform: `translate(${dx}px, ${dy}px) scale(${s}) rotate(-14deg)` }, { transform: "translate(0, 0) scale(1) rotate(0deg)" }],
    { duration: 430, delay, easing: "cubic-bezier(.2,.75,.25,1)", fill: "both" });
  Sound.play("card", delay / 1000);
  anim.onfinish = () => {
    ghost.remove();
    if (!toEl.isConnected) return;
    toEl.style.visibility = "";
    if (!faceUp) toEl.animate([{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], { duration: 170, easing: "ease-out" });
  };
}

function runFlights(before, events) {
  if (!before.deck || !flightsAllowed()) return;
  const origin = {};  // destination card key -> previous key it came from
  for (const ev of events) {
    if (ev.t === "steal") origin[`${ev.p}:${ev.card}`] = `${ev.victim}:${ev.card}`;
    if (ev.t === "swap") { origin[`${ev.a}:${ev.card_b}`] = `${ev.b}:${ev.card_b}`; origin[`${ev.b}:${ev.card_a}`] = `${ev.a}:${ev.card_a}`; }
  }
  let i = 0;
  for (const el of $$("#board .card[data-k]")) {
    const k = el.dataset.k;
    if (before.rects[k]) continue;
    const src = origin[k] && before.rects[origin[k]];
    if (src) fly(src, el, true, i * 120);
    else fly(before.deck, el, false, i * 150);
    i++;
    if (i > 10) break;
  }
}

function confetti(el) {
  if (reduceMotion() || !el) return;
  const r = el.getBoundingClientRect();
  const colors = ["#E3A62A", "#F2C75A", "#C9561A", "#1D756F", "#7A3657", "#FFF8EA", "#7F8A31"];
  for (let i = 0; i < 70; i++) {
    const c = document.createElement("div");
    c.className = "confetti";
    c.style.background = colors[i % colors.length];
    c.style.left = `${r.left + r.width / 2}px`;
    c.style.top = `${r.top + r.height / 3}px`;
    document.body.appendChild(c);
    const a = Math.random() * Math.PI * 2, v = 120 + Math.random() * 260;
    const dx = Math.cos(a) * v, dy = Math.sin(a) * v - 180;
    c.animate([
      { transform: "translate(0,0) rotate(0deg)", opacity: 1 },
      { transform: `translate(${dx}px, ${dy + 420}px) rotate(${Math.random() * 900 - 450}deg)`, opacity: 0 },
    ], { duration: 1400 + Math.random() * 700, easing: "cubic-bezier(.15,.7,.4,1)" }).onfinish = () => c.remove();
  }
}

// Unlucky 7: a boot swings in from off-screen and kicks the wiped cards off the table. The cards are
// copied before the table re-renders, so they can fly away from where they were.
const KICK_WORDS = ["THWACK!", "WHAM!", "BOOT!"];
const KICK_TOE = [148, 226], KICK_HIP = 73;  // toe tip and leg centre, in the boot's own units

function bootSVG(top) {
  return `<svg class="kick__boot" viewBox="0 ${top} 150 ${270 - top}" aria-hidden="true">
    <g class="kick__whoosh" fill="none" stroke="#3A2315" stroke-linecap="round" stroke-width="4"><path d="M10 150q-10 44 12 92"/><path d="M28 126q-12 52 10 100"/></g>
    <path d="M56 ${top}h34l22 ${160 - top}q-40 16-80 0z" fill="#3E5E8A" stroke="#3A2315" stroke-width="5" stroke-linejoin="round"/>
    <path d="M84 ${top}l10 ${148 - top}" stroke="#FFF8EA" stroke-width="2" stroke-dasharray="5 5" opacity=".5" fill="none"/>
    <path d="M63 ${top}l-6 ${130 - top}" stroke="#2B4466" stroke-width="3" fill="none" stroke-linecap="round"/>
    <path d="M54 164v56q0 18 18 18h60q16 0 16-15t-22-23q-20-4-32-14v-22z" fill="#9A6233" stroke="#3A2315" stroke-width="5" stroke-linejoin="round"/>
    <path d="M112 196q7 20 1 42" fill="none" stroke="#6E4422" stroke-width="3" stroke-linecap="round"/>
    <path d="M50 236h99q1 12-15 12H68q-17 0-18-12z" fill="#3A2315" stroke="#3A2315" stroke-width="3" stroke-linejoin="round"/>
    <path d="M54 246h24v6q0 3-3 3H57q-3 0-3-3z" fill="#3A2315"/>
    <path d="M126 205q14 5 17 15" fill="none" stroke="#FFF8EA" stroke-width="4" stroke-linecap="round" opacity=".75"/>
    <path d="M60 180v30" fill="none" stroke="#FFF8EA" stroke-width="3" stroke-linecap="round" opacity=".3"/>
    <path d="M86 178l11 5M86 188l12 5" stroke="#FFF8EA" stroke-width="3.5" stroke-linecap="round"/>
    <g fill="none" stroke-linecap="round" stroke-width="5"><path d="M33 150q39 15 78 0" stroke="#A93A1C"/><path d="M33 157q39 15 78 0" stroke="#C9561A"/><path d="M32 164q40 15 80 0" stroke="#E3A62A"/></g>
    <path d="M31 168q41 16 82 0" fill="none" stroke="#3A2315" stroke-width="4" stroke-linecap="round"/>
  </svg>`;
}

function powSVG(word) {
  const pts = [];
  for (let i = 0; i < 26; i++) {
    const a = (Math.PI * i) / 13 - Math.PI / 2, k = i % 2 ? 0.68 + 0.08 * Math.sin(i * 2.3) : 1 + 0.1 * Math.cos(i * 1.7);
    pts.push(`${(170 + Math.cos(a) * 165 * k).toFixed(1)},${(110 + Math.sin(a) * 100 * k).toFixed(1)}`);
  }
  const d = `M${pts.join("L")}Z`;
  return `<svg class="kick__pow" viewBox="-10 -10 360 240" aria-hidden="true"><path d="${d}" fill="#3A2315" transform="translate(6 7)"/>
    <path d="${d}" fill="#F2C75A" stroke="#3A2315" stroke-width="4" stroke-linejoin="round"/>
    <text x="170" y="126" text-anchor="middle" font-family="Fraunces, Georgia, serif" font-weight="900" font-size="${word.length > 6 ? 46 : 58}" fill="#A93A1C" stroke="#3A2315" stroke-width="1.5" paint-order="stroke" transform="rotate(-7 170 110)">${word}</text></svg>`;
}

function captureKicks(events) {
  if (!flightsAllowed()) return [];
  return events.filter((ev) => ev.t === "unlucky7" && ev.wiped.length).map((ev) => ({
    p: ev.p,
    cards: $$(`#board [data-seat="${ev.p}"] .card[data-k]`).map((el) => ({ k: el.dataset.k, el: el.cloneNode(true), r: el.getBoundingClientRect() })),
  }));
}

function runKicks(kicks) {
  for (const { p, cards } of kicks) {
    const seat = $(`#board [data-seat="${p}"]`);
    const gone = cards.filter((c) => !seat || !seat.querySelector(`.card[data-k="${c.k}"]`));
    if (gone.length) kickAway(p, gone, 150, true);
  }
}

// `delay`: ms until the boot appears. `keepU7`: hold the arriving Unlucky 7 above the kicked cards.
function kickAway(p, cards, delay, keepU7) {
  const layer = document.createElement("div");
  layer.className = "kick";
  document.body.appendChild(layer);
  cards = cards.slice().sort((a, b) => a.r.left - b.r.left);
  for (const { el, r } of cards) {
    el.classList.remove("pickable", "chosen");
    el.classList.add("ghost-card", "kicked");
    el.style.cssText += `;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;--h:${r.height}px;visibility:visible`;
    el.querySelectorAll(".card__key, .pct, .from").forEach((x) => x.remove());
    layer.appendChild(el);
  }
  // the boot swings in from the roomier side and kicks the cards towards the other one
  const first = cards[0].r, last = cards[cards.length - 1].r, h = first.height;
  const dir = first.left >= window.innerWidth - last.right ? 1 : -1;
  if (dir < 0) cards.reverse();
  const D = 1150, impact = delay + 0.5 * D;

  // a long leg hinged above the top of the screen, so the swing reads as a kick from off-screen
  const ix = dir > 0 ? first.left + h * 0.04 : last.right - h * 0.04, iy = first.top + h * 0.6;
  const s = Math.max(h, 46) * 0.95 / 75;
  const top = Math.min(-20, Math.round(-(iy + 140) / s + KICK_TOE[1]));
  const L = (KICK_TOE[1] - top) * s;
  const rot = (x) => `rotate(${(dir * Math.atan2(x, L) * 180) / Math.PI}deg)`;
  const back = Math.max(h * 2, 110), through = h * 0.9;
  const toeX = dir > 0 ? KICK_TOE[0] : 150 - KICK_TOE[0], hipX = dir > 0 ? KICK_HIP : 150 - KICK_HIP;
  const wrap = document.createElement("div");
  wrap.className = `kick__leg${dir < 0 ? " kick__leg--flip" : ""}`;
  wrap.innerHTML = bootSVG(top);
  wrap.style.cssText = `left:${ix - toeX * s}px;top:${iy - L}px;width:${150 * s}px;height:${(270 - top) * s}px;transform-origin:${hipX * s}px 0`;
  layer.appendChild(wrap);
  wrap.animate([
    { transform: rot(back * 1.25), opacity: 0, easing: "cubic-bezier(.2,.8,.3,1)" },
    { transform: rot(back), opacity: 1, offset: 0.22, easing: "ease-in-out" },
    { transform: rot(back * 1.18), offset: 0.4, easing: "cubic-bezier(.6,0,.95,.5)" },
    { transform: rot(0), offset: 0.5, easing: "cubic-bezier(.1,.6,.3,1)" },
    { transform: rot(-through), offset: 0.62, easing: "ease-out" },
    { transform: rot(-through * 0.8), offset: 0.74, easing: "cubic-bezier(.5,0,.9,.6)" },
    { transform: `${rot(back * 0.5)} translateY(${-L * 0.4}px)`, opacity: 1, offset: 0.92 },
    { transform: `${rot(back * 0.6)} translateY(${-L * 0.5}px)`, opacity: 0 },
  ], { duration: D, delay, fill: "both" });
  wrap.querySelector(".kick__whoosh").animate(
    [{ opacity: 0 }, { opacity: 0, offset: 0.4 }, { opacity: 0.55, offset: 0.48 }, { opacity: 0, offset: 0.6 }, { opacity: 0 }],
    { duration: D, delay, fill: "both" });

  // the old cards tremble as the Unlucky 7 lands, then fly off one after another
  cards.forEach(({ el, r }, i) => {
    el.animate([{ transform: "none" }, { transform: "rotate(-3deg) translateY(-2px)" }, { transform: "rotate(3deg)" }, { transform: "rotate(-2deg) translateY(-1px)" }, { transform: "rotate(2deg)" }, { transform: "none" }],
      { duration: 360, delay: impact - 420 + i * 18 });
    const vx = dir * ((dir > 0 ? window.innerWidth - r.left : r.right) + h + Math.random() * 260), peak = Math.max(h, 90) * (1.4 + Math.random() * 1.4);
    const spin = dir * (420 + Math.random() * 520) * (Math.random() < 0.2 ? -1 : 1), frames = [];
    for (let k = 0; k <= 12; k++) {
      const t = k / 12;
      frames.push({ transform: `translate(${vx * t}px, ${peak * (-5 * t + 6.25 * t * t)}px) rotate(${spin * t}deg)${k === 1 ? " scaleX(.86)" : ""}`, opacity: t < 0.75 ? 1 : 1 - (t - 0.75) * 4 });
    }
    el.animate(frames, { duration: 950 + i * 50, delay: impact + i * 26, easing: "cubic-bezier(.3,.5,.6,1)", fill: "both" });
  });

  // THWACK, dust, a jolt for the seat
  const pow = document.createElement("div");
  pow.className = "kick__powwrap";
  const pw = Math.max(h * 2.6, 150);
  // beside the boot, on the side the cards fly to
  const px = clamp(dir > 0 ? ix + h * 0.15 : ix - h * 0.15 - pw, 8, window.innerWidth - pw - 8), py = Math.max(8, iy - h * 0.8 - pw * 0.45);
  pow.style.cssText = `left:${px}px;top:${py}px;width:${pw}px;height:${pw * 0.667}px;transform-origin:50% 60%`;
  pow.innerHTML = powSVG(KICK_WORDS[Math.floor(Math.random() * KICK_WORDS.length)]);
  layer.appendChild(pow);
  pow.animate([
    { transform: "scale(.2) rotate(-18deg)", opacity: 0 },
    { transform: "scale(1.14) rotate(-4deg)", opacity: 1, offset: 0.14 },
    { transform: "scale(1) rotate(-6deg)", opacity: 1, offset: 0.24 },
    { transform: "scale(1) rotate(-6deg)", opacity: 1, offset: 0.78 },
    { transform: "scale(1.06) rotate(-6deg) translateY(-12px)", opacity: 0 },
  ], { duration: 1050, delay: impact, easing: "ease-out", fill: "both" });
  for (let i = 0; i < 7; i++) {
    const puff = document.createElement("div");
    puff.className = "kick__puff";
    const size = h * (0.16 + Math.random() * 0.14), a = Math.PI * (0.55 + Math.random() * 0.9);
    puff.style.cssText = `left:${ix - size / 2}px;top:${iy - size / 2}px;width:${size}px;height:${size}px`;
    layer.appendChild(puff);
    puff.animate([
      { transform: "translate(0,0) scale(.3)", opacity: 0.95 },
      { transform: `translate(${dir * Math.cos(a) * h * 0.8}px, ${Math.sin(a) * h * 0.55 - h * 0.2}px) scale(1.5)`, opacity: 0 },
    ], { duration: 520 + Math.random() * 200, delay: impact, easing: "cubic-bezier(.2,.8,.4,1)", fill: "both" });
  }
  setTimeout(() => $(`#board [data-seat="${p}"]`)?.animate(
    [{ transform: "none" }, { transform: "translateX(-5px) rotate(-.6deg)" }, { transform: "translateX(6px) rotate(.5deg)" }, { transform: "translateX(-3px)" }, { transform: "none" }],
    { duration: 380, easing: "ease-out" }), impact);
  Sound.play("kick", impact / 1000);

  if (keepU7) setTimeout(() => {
    const u = $(`#board [data-seat="${p}"] .card[data-k="${p}:${U7}"]`);
    if (!u || !u.isConnected) return;
    const r = u.getBoundingClientRect(), keep = u.cloneNode(true);
    keep.classList.add("ghost-card", "kick__keep");
    keep.style.cssText += `;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;--h:${r.height}px;visibility:visible`;
    layer.appendChild(keep);
    setTimeout(() => keep.remove(), impact + 250 - 440);
  }, 440);
  setTimeout(() => layer.remove(), impact + 1400 + cards.length * 80);
}

function countUp(el, from, to) {
  if (!el || from === to || reduceMotion()) return;
  const t0 = performance.now(), dur = 800;
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - (1 - k) ** 3;
    el.textContent = Math.round(from + (to - from) * e);
    if (k < 1 && el.isConnected) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function runEffects(events) {
  const { game, room } = S.state;
  for (const ev of events) {
    if (ev.t === "bust") Sound.play("bust", flightsAllowed() ? 0.55 : 0);
    else if (ev.t === "stay") Sound.play("stay");
    else if (["action", "steal", "swap", "discard"].includes(ev.t)) Sound.play("action");
    else if (ev.t === "flip7") {
      Sound.play("flip7");
      setTimeout(() => confetti($(`[data-seat="${ev.p}"] .seat__head`)), 150);
    }
  }
  for (const [p, prev] of Object.entries(S.prev.totals)) {
    const now = game.players[p]?.total;
    if (now !== undefined && now !== prev) countUp($(`[data-total="${p}"]`), prev, now);
  }
  const end = events.find((e) => e.t === "round_end"), over = events.find((e) => e.t === "game_over");
  if (over) { showGameOver(end, over); if (over.winners.includes(room.you)) Sound.play("win", 0.3); }
  else if (end) showRoundEnd(end);
}

// ------------------------------------------------------------------ overlays
function standingsHTML(end) {
  const rows = end.totals.map((t, i) => ({ i, t, s: end.scores[i] })).sort((a, b) => b.t - a.t);
  return `<div class="standings">${rows.map((r, k) => `<div class="standing ${k === 0 ? "lead" : ""}">
    <span class="pos">${k + 1}</span>${avatar(r.i)}
    <div class="nm">${esc(seatName(r.i))}${end.flip7 === r.i ? "<small>Flipped 7</small>" : r.s < 0 ? "<small>Lost points</small>" : r.s === 0 ? "<small>Nothing this round</small>" : ""}</div>
    <span class="delta ${r.s > 0 ? "pos" : r.s < 0 ? "neg" : ""}">${signed(r.s)}</span><span class="tot">${r.t}</span></div>`).join("")}</div>`;
}

function showRoundEnd(end) {
  clearTimeout(S.overlayTimer);
  const close = () => { if ($("#round-sheet")) $("#overlay").innerHTML = ""; };
  $("#overlay").innerHTML = `<div class="scrim light" id="round-sheet"><div class="sheet">${ribbon(`Round ${S.state.game.round - (S.state.game.over ? 0 : 1) || 1} over`, "ribbon--mustard")}${standingsHTML(end)}<p class="muted" style="text-align:center;font-size:13px">Next round coming up…</p></div></div>`;
  $("#round-sheet").onclick = close;
  const sp = S.state.room.speed || 1;
  S.overlayTimer = setTimeout(close, S.state.room.settings.watch ? clamp(sp * 2600, 900, 2800) : 2600);
}

// The coach replays each decision on many shuffles of the unseen cards (flip7/coach.py): "lost"
// is the win chance the choice gave up against the best option, with a 95% interval.
const pct1 = (x) => `${(x * 100).toFixed(1)}%`;
function reviewHTML(rv) {
  if (!rv || !rv.decisions) return "";
  const top = rv.moments.filter((m) => m.loss - m.ci > 0.005).slice(0, 4);
  return `<div class="review"><h4>Coach's review</h4>
    <div class="agree">${rv.good}/${rv.decisions}<small>decisions were the best move or within the coach's margin of error${rv.lost > 0 ? `<br>About <b>${pct1(rv.lost)}</b> win chance given up over the game` : ""}</small></div>
    ${top.length ? top.map((m) => {
      const chosen = m.options.find((o) => o.a === m.chosen), best = m.options.find((o) => o.a === m.best);
      return `<div class="row-r"><div><span class="when">Round ${m.round}</span> You chose <b>${esc(chosen.label)}</b> (${pct(chosen.win)} to win). Better: <b>${esc(best.label)}</b> (${pct(best.win)}) <b class="loss">−${pct1(m.loss)}</b> <span class="pm">± ${pct1(m.ci)}</span>${best.facts[0] ? `<small>${esc(best.facts[0])}${chosen.facts[0] ? ` · your choice: ${esc(chosen.facts[0])}` : ""}</small>` : ""}</div>
        <button class="btn btn--stock btn--xs" data-cmd="replay" data-i="${m.i}">${icon("play")}Replay</button></div>`;
    }).join("") : `<p class="row-r">No clear mistakes: every decision was within the coach's margin of error.</p>`}
  </div>`;
}

const REPLAY_PROMPT = {
  hit_stay: () => "Hit or stay?",
  target: (t) => `${cardName(t.card)}: who takes it?`,
  modifier: (t) => `You drew ${cardName(t.card)}: who gets it?`,
  steal: () => "Steal: which card?",
  swap1: () => "Swap: the first card?",
  swap2: (t) => `Swap your pick of ${t.first ? `${t.first[0] === t.me ? "your" : esc(seatName(t.first[0])) + "'s"} ${cardName(t.first[1])}` : "a card"} for…`,
  discard: () => "Discard: which card?",
  flip7: () => "Flip 7! +15 for you, or −15 for someone?",
};

// Replay one reviewed decision: the table as it was, choose again, then see every option's value.
function showReplay(i, picked) {
  const m = S.review?.moments.find((x) => x.i === i);
  if (!m) return;
  const t = m.table;
  const status = (p) => (p.status === 2 ? "busted" : p.status === 1 ? "stayed" : "in");
  const players = t.players.map((p, q) => `<div class="rp-player ${q === t.me ? "me" : ""}">
      ${avatar(q)}<div class="rp-who"><b>${q === t.me ? "You" : esc(seatName(q))}</b><small>${p.total} pts · ${status(p)} · round ${signed(p.projected)}</small></div>
      <div class="line">${p.line.map((c) => cardHTML(c, "card--xs")).join("") || '<span class="empty">no cards</span>'}</div></div>`).join("");
  const opts = picked === undefined
    ? `<div class="rp-options">${m.options.map((o) => `<button class="btn btn--stock" data-cmd="replay-pick" data-i="${i}" data-a="${o.a}">${esc(o.label)}</button>`).join("")}</div>`
    : `<div class="rp-results">${[...m.options].sort((a, b) => b.win - a.win).map((o) => `<div class="rp-row ${o.a === m.best ? "best" : ""}">
        <div class="rp-label"><b>${esc(o.label)}</b>${o.a === picked ? '<span class="tag tag--task">your pick now</span>' : ""}${o.a === m.chosen ? '<span class="tag tag--light">in the game</span>' : ""}${o.a === m.best ? '<span class="tag tag--lead">best</span>' : ""}</div>
        <div class="rp-bar"><i style="width:${(o.win * 100).toFixed(1)}%"></i><span>${pct1(o.win)}</span></div>
        ${o.facts.length ? `<small>${o.facts.map(esc).join(" · ")}</small>` : ""}</div>`).join("")}
        <p class="note">Win chances come from replaying each option on many shuffles of the cards still unseen at that moment (±${pct1(m.ci || 0.01)}).</p></div>`;
  let el = $("#replay");
  if (!el) { el = document.createElement("div"); el.id = "replay"; document.body.appendChild(el); }
  el.innerHTML = `<div class="scrim"><div class="sheet wide replay">
    ${ribbon(`Round ${m.round} · replay`, "ribbon--mustard")}
    <button class="btn btn--stock btn--xs btn--icon x" data-cmd="replay-close" aria-label="Close">${icon("x")}</button>
    <div class="rp-table">${players}</div>
    <h2 class="rp-prompt">${(REPLAY_PROMPT[m.kind] || (() => "Your move"))(t)}</h2>
    ${t.deck ? `<p class="sub">${t.deck} cards in the deck · first to ${t.target}</p>` : ""}
    ${opts}
    ${picked !== undefined ? `<div class="actions"><button class="btn btn--stock" data-cmd="replay" data-i="${i}">Try again</button><button class="btn btn--orange" data-cmd="replay-close">Back to the review</button></div>` : ""}
  </div></div>`;
}

function showGameOver(end, over) {
  clearTimeout(S.overlayTimer);
  const { room } = S.state;
  const youWon = over.winners.includes(room.you);
  const seated = room.you >= 0 && !room.settings.watch;
  const names = over.winners.map((w) => esc(seatName(w))).join(" & ");
  $("#overlay").innerHTML = `<div class="scrim" id="over-sheet"><div class="sheet wide">
    ${ribbon("Game over", "ribbon--mustard")}
    <div class="trophy ${seated && !youWon ? "lost" : ""}">${icon(youWon || !seated ? "trophy" : "flag")}</div>
    <h2>${youWon ? "You win!" : `${names} win${over.winners.length > 1 ? "" : "s"}`}</h2>
    <p class="sub">${youWon ? "Beat the bots at their own game." : seated ? "The cards weren't with you this time." : "Final standings"}</p>
    ${end ? standingsHTML(end) : ""}
    <div id="review-slot"></div>
    <div class="actions">
      ${room.host || room.settings.watch ? `<button class="btn btn--orange btn--lg" data-cmd="start">${icon("play")}${room.settings.watch ? "Run it back" : "Rematch"}</button>` : `<span class="muted">Waiting for the host to deal again…</span>`}
      <button class="btn btn--stock btn--lg" data-cmd="close-overlay">See the table</button>
      <a class="btn btn--stock btn--lg" href="#/">Leave</a>
    </div></div></div>`;
  if (youWon) setTimeout(() => confetti($("#over-sheet .trophy")), 200);
}

function showInvite() {
  const { room } = S.state;
  const link = `${location.origin}/#/room/${room.id}`;
  const local = /^(localhost|127\.|0\.0\.0\.0)/.test(location.hostname);
  const lanLink = S.lan ? `http://${S.lan}:${location.port || 80}/#/room/${room.id}` : null;
  $("#overlay").innerHTML = `<div class="scrim" id="invite-sheet"><div class="sheet">
    ${ribbon(`Table ${esc(room.id)}`, "ribbon--mustard")}
    <button class="btn btn--stock btn--xs btn--icon x" data-cmd="close-overlay" aria-label="Close">${icon("x")}</button>
    <h2>Invite friends</h2>
    <p class="sub">Friends can watch any time, or take a seat between games.</p>
    <div class="linkbox"><code>${esc(link)}</code><button class="btn btn--sm" data-copy="${esc(link)}">${icon("copy")}Copy</button></div>
    ${local && lanLink ? `<div class="linkbox"><code>${esc(lanLink)}</code><button class="btn btn--teal btn--sm" data-copy="${esc(lanLink)}">${icon("copy")}Wi-Fi link</button></div><span class="note">The first link only works on this computer. Friends on your Wi-Fi use the second.</span>` : ""}
  </div></div>`;
}

function toggleMenu() {
  S.menu = !S.menu;
  $(".menu")?.remove();
  renderTools();
  if (!S.menu) return;
  const { room } = S.state;
  const m = document.createElement("div");
  m.className = "menu";
  m.innerHTML = `
    <span class="label">Table options</span>
    <label class="toggle"><input type="checkbox" data-ui="odds" ${S.odds ? "checked" : ""}> Show bust odds on seats</label>
    <label class="toggle"><input type="checkbox" data-ui="sound" ${Sound.on ? "checked" : ""}> Sound effects</label>
    ${room.host && !room.settings.watch ? `<label class="toggle"><input type="checkbox" data-setting="coach" ${room.settings.coach ? "checked" : ""}> Coach for everyone</label>
      <label class="field"><span class="label">Bot pace · ${room.speed.toFixed(1)}s per move</span><input type="range" min="0.1" max="3" step="0.1" value="${room.speed}" data-input="speed"></label>` : ""}
    ${room.settings.watch || LOCAL ? "" : `<button class="btn btn--stock btn--sm" data-cmd="invite">${icon("link")}Invite friends</button>`}
    ${room.host && room.mode === "playing" && !room.settings.watch ? `<button class="btn btn--stock btn--sm" data-cmd="stop">${icon("flag")}End game, back to lobby</button>` : ""}
    <a class="btn btn--stock btn--sm" href="#/">${icon("leave")}Leave the table</a>`;
  document.body.appendChild(m);
}

// ------------------------------------------------------------------ input
function press(btn) {
  if (!btn) return;
  btn.classList.add("is-pressed");
  setTimeout(() => btn.classList.remove("is-pressed"), 120);
}

document.addEventListener("click", (e) => {
  if (S.menu && !e.target.closest(".menu") && !e.target.closest('[data-cmd="menu"]')) { S.menu = false; $(".menu")?.remove(); renderTools(); }
  const copyEl = e.target.closest("[data-copy]");
  if (copyEl) { copy(copyEl.dataset.copy, "Link"); return; }
  const actEl = e.target.closest("[data-a]");
  if (actEl && S.state && app.contains(actEl) && !actEl.dataset.cmd) { send({ type: "act", action: +actEl.dataset.a, seq: S.state.game?.seq }); return; }
  const tab = e.target.closest("[data-tab]");
  if (tab) { setTab(tab.dataset.tab); return; }
  const cmdEl = e.target.closest("[data-cmd]");
  if (!cmdEl) return;
  const room = S.state?.room;
  switch (cmdEl.dataset.cmd) {
    case "sit": askName().then(() => send({ type: "take_seat", seat: +cmdEl.dataset.seat })); break;
    case "leave": send({ type: "leave_seat" }); break;
    case "add-open": send({ type: "add_seat", kind: "open" }); break;
    case "add-bot": send({ type: "add_seat", kind: "bot", bot_id: bestBot() }); break;
    case "start": $("#overlay").innerHTML = ""; send({ type: "start" }); break;
    case "pause": send({ type: "pause", value: !room.paused }); break;
    case "step": send({ type: "step" }); break;
    case "stop": S.menu = false; $(".menu")?.remove(); send({ type: "stop" }); break;
    case "close-overlay": $("#overlay").innerHTML = ""; break;
    case "side": setSide(!S.side.open); break;
    case "toggle-chat": S.chatCollapsed = !S.chatCollapsed; $("#chat-panel")?.classList.toggle("collapsed", S.chatCollapsed); markChatSeen(); break;
    case "replay": showReplay(+cmdEl.dataset.i); break;
    case "replay-pick": showReplay(+cmdEl.dataset.i, +cmdEl.dataset.a); break;
    case "replay-close": $("#replay")?.remove(); break;
    case "substitute": send({ type: "substitute", seat: +cmdEl.dataset.seat }); break;
    case "reclaim": send({ type: "reclaim" }); break;
    case "sound": Sound.on = !Sound.on; localStorage.setItem("flip7_sound", Sound.on ? "1" : "0"); Sound.ensure(); renderTools(); break;
    case "invite": S.menu = false; $(".menu")?.remove(); showInvite(); break;
    case "menu": toggleMenu(); break;
  }
});

document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.dataset.seat !== undefined && t.tagName === "SELECT") {
    const v = t.value;
    if (v === "open") send({ type: "set_seat", seat: +t.dataset.seat, kind: "open" });
    else if (v === "remove") send({ type: "set_seat", seat: +t.dataset.seat, kind: "remove" });
    else send({ type: "set_seat", seat: +t.dataset.seat, kind: "bot", bot_id: v.slice(4) });
  } else if (t.dataset.setting) {
    send({ type: "settings", [t.dataset.setting]: t.type === "checkbox" ? t.checked : +t.value });
  } else if (t.dataset.ui === "sound") {
    Sound.on = t.checked;
    localStorage.setItem("flip7_sound", Sound.on ? "1" : "0");
    Sound.ensure();
    renderTools();
  } else if (t.dataset.ui === "odds") {
    S.odds = t.checked;
    localStorage.setItem("flip7_odds", t.checked ? "1" : "0");
    if (S.view === "table") renderSeats();
  } else if (t.dataset.input === "speed") {
    send({ type: "speed", value: +t.value });
  }
});

document.addEventListener("submit", (e) => {
  if (e.target.matches("[data-chat]")) {
    e.preventDefault();
    const input = e.target.querySelector("input");
    if (input.value.trim()) send({ type: "chat", text: input.value });
    input.value = "";
  }
});

document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.metaKey || e.ctrlKey) return;
  if ((e.key === "Enter" || e.key === " ") && e.target.matches?.(".card.pickable[data-a]")) {
    e.preventDefault();
    send({ type: "act", action: +e.target.dataset.a, seq: S.state?.game?.seq });
    return;
  }
  if (e.key === "Escape") { $("#overlay").innerHTML = ""; if (S.menu) toggleMenu(); if (S.side.open) setSide(false); return; }
  const st = S.state;
  const d = st?.game?.decision;
  if (!d || d.player !== st.room.you || st.room.mode !== "playing") return;
  const seq = st.game.seq;
  const has = (a) => d.options.some((o) => o.a === a);
  if (d.kind === "hit_stay" || d.kind === "pay") {
    if ((e.key === "h" || e.key === " ") && has(1)) { e.preventDefault(); press($('#dock [data-a="1"]')); send({ type: "act", action: 1, seq }); }
    if (e.key === "s" && has(0)) { press($('#dock [data-a="0"]')); send({ type: "act", action: 0, seq }); }
  } else if (/^[1-9]$/.test(e.key)) {
    const btn = $(`#dock [data-key="${e.key}"]`) || $(`#board .card.pickable[data-key="${e.key}"]`);
    if (btn) { press(btn); send({ type: "act", action: +btn.dataset.a, seq }); }
  }
});

window.addEventListener("resize", () => { if (S.view === "table" && S.state) { renderTools(); markChatSeen(); } });

for (const [type, on] of [["mouseover", true], ["focusin", true], ["mouseout", false], ["focusout", false]]) {
  document.addEventListener(type, (e) => {
    const card = e.target.closest?.(".card.pickable[data-a]");
    const out = $("#pick-preview");
    if (!card || !out) return;
    out.innerHTML = on ? pickPreview(+card.dataset.a) || "&nbsp;" : "<b>Click a glowing card</b>, or press its number.";
  });
}

// Tick the "away" timers once a second while someone is disconnected.
setInterval(() => {
  if (S.view !== "table" || !S.state || S.state.room.mode !== "playing") return;
  if (S.state.room.seats.some((s) => s.away != null && !s.sub)) { renderSeats(); renderDock(); }
}, 1000);

// ------------------------------------------------------------------ rules page
function renderRules() {
  setTools("");
  const rc = (cards, text) => `<div class="rule-card">${cards.map((c) => cardHTML(c)).join("")}<p>${text}</p></div>`;
  app.innerHTML = `<div class="page"><div class="prose">
    <div class="pagehead"><h1>How to play</h1><p>A push-your-luck race to <b>200 points</b>. On your turn, <b>Hit</b> (take a card) or <b>Stay</b> (bank your points for the round). Draw a number you already hold and you <b>bust</b>: nothing this round. Collect <b>seven different numbers</b> and you <b>Flip 7</b>: the round ends at once and you get a 15-point bonus.</p></div>
    <div class="panel">
    <div class="card-row">${[1, 4, 7, 9, 12, 14].map((c) => cardHTML(c)).join("")}</div>
    <p>There's one 1, two 2s, three 3s … up to fourteen 14s, so big numbers bust you more often. The deck (138 cards) isn't reshuffled between rounds, so counting cards pays off. The bots count every card.</p>
    <h2>Special numbers</h2>
    <div class="rule-cards">
      ${rc([0], "<b>The Zero.</b> Your round score is 0 unless you Flip 7, and you can't stay voluntarily while you hold it.")}
      ${rc([U7], "<b>Unlucky Frozen 7.</b> When it arrives, every other card in your line is discarded and you freeze: you stay at once and can't take cards from the deck again this round. It can't bust you, but a 7 swapped in later will.")}
      ${rc([L14], "<b>Lucky 14.</b> While you hold it you may have two 14s. A third one busts you.")}
    </div>
    <h2>Action cards</h2>
    <p>You must use an action card if anyone can be targeted. Unless a card says otherwise, targets are anyone who hasn't busted, including you and players who stayed. A frozen player can't be made to take cards.</p>
    <div class="rule-cards">
      ${rc([JOM], "<b>Just One More!</b> The target takes one more card, then has to stay.")}
      ${rc([FLIP4], "<b>Flip Four!</b> The target takes the next four cards, stopping on a bust or Flip 7. Actions drawn this way resolve afterwards.")}
      ${rc([SWAP], "<b>Swap.</b> Trade two face-up cards between two different players. It can bust both. There are four of these.")}
      ${rc([STEAL], "<b>Steal.</b> Take any face-up card from another player's line. A duplicate busts you.")}
      ${rc([DISCARD], "<b>Discard.</b> Throw away any card in anyone's line, your own included.")}
      ${rc([DELIVERY], "<b>Special Delivery.</b> Flip the next card face up and choose who gets it: a number can bust them, a modifier lands on them, an action is theirs to play.")}
      ${rc([BOUNTY], "<b>Bounty.</b> Put it on a rival. If anyone's card busts them this round, that player banks +10 on the spot. Busting on their own hit pays nobody.")}
      ${rc([DARE], "<b>Double Dare.</b> Pick a rival who's still drawing: on their next two turns they must hit.")}
      ${rc([SHAKEDOWN], "<b>Shakedown.</b> Pick a rival: they pay you 10 points, or take a card right now instead.")}
      ${rc([ROBIN], "<b>Robin Hood.</b> 10 points move from the highest total to the lowest. Nobody chooses.")}
    </div>
    <h2>Keepers</h2>
    <p>Keepers sit in your line like a modifier: they can be swapped, stolen or discarded, they never bust you and they don't count towards Flip 7.</p>
    <div class="rule-cards">
      ${rc([TAX], "<b>Tax Collector.</b> When the round is scored, if you haven't busted, every player ahead of you in the game pays you 5.")}
      ${rc([SPITE], "<b>Spite.</b> If you bust while holding it, pick a player: they lose 10 points this round.")}
    </div>
    <h2>Modifiers: handed to your rivals</h2>
    <div class="card-row">${[17, 18, 19, 20, 21, 22].map((c) => cardHTML(c)).join("")}</div>
    <p>When you draw a modifier you give it to a player. ÷2 halves their number total (rounded down), and the minus cards come off their score. Modifiers never bust anyone and don't count towards Flip 7.</p>
    <h2>Brutal Mode</h2>
    <ul>
      <li>Round scores can go <b>below zero</b>.</li>
      <li>Modifiers can be given to <b>busted</b> players too, so a busted player can end the round at −10.</li>
      <li>When you Flip 7 you choose: <b>+15 for yourself</b> or <b>−15 for someone else</b>.</li>
    </ul>
    <h2>Scoring a round</h2>
    <p>Add your numbers → halve if you hold ÷2 → subtract minus cards and Spite → +15 for a Flip 7, then the Tax Collectors collect. The game ends after a round in which someone reaches 200, and the highest total wins.</p>
    <p class="muted">The full rules, including the edge cases, are in <a href="${REPO}/blob/main/RULES.md" target="_blank" rel="noopener">RULES.md</a> in the project.</p>
    <p class="muted">Bust or Bank is an unofficial fan variant of Flip 7: With a Vengeance, not affiliated with or endorsed by its publisher, The Op Games. The card designs and rules text here are this project's own. Get the real cards to play at the table.</p>
    </div>
  </div></div>`;
}

// ------------------------------------------------------------------ insights page (charts in insights.js)
async function renderInsights() {
  setTools("");
  app.innerHTML = `<div class="page"><div class="pagehead"><h1>Loading insights…</h1></div></div>`;
  const mod = await import("./insights.js");
  const page = document.createElement("div");
  page.className = "page";
  app.innerHTML = "";
  app.appendChild(page);
  mod.render(page, { cardHTML, cardName, esc });
}

// ------------------------------------------------------------------ boot
updateMeChip();
api("/api/info").then((i) => (S.lan = i.lan[0] || null)).catch(() => {});
api("/api/bots").then((b) => { S.bots = b; route(); }).catch(() => route());
