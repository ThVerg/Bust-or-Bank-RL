// Insights page: how the RL bot plays, from analysis/insights.json (python -m flip7.analyze).
// Charts are plain SVG. RL = series 1 (teal), SmartBot = series 2 (orange); both validated
// against the cream panel surface. Every chart has a legend, a hover readout and a table view.

const SERIES = [
  { key: "rl", name: "RL bot", color: "#008C82" },
  { key: "smart", name: "SmartBot (human-like)", color: "#C9561A" },
];
const INK = { text: "#3A2315", text2: "#5B3A24", muted: "#7A5A40", grid: "rgba(58,35,21,0.10)", axis: "rgba(58,35,21,0.38)", surface: "#FFFAF0" };
const pct = (x, d = 0) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);
const num = (x, d = 1) => (x == null ? "–" : x.toFixed(d));
const svgEl = (tag, attrs = {}) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };

function legend(series, shape = "line") {
  const el = document.createElement("div");
  el.className = "legend";
  for (const s of series) {
    const sp = document.createElement("span");
    const i = document.createElement("i");
    i.style.background = s.color;
    if (shape === "line") { i.style.height = "3px"; i.style.width = "14px"; i.style.borderRadius = "2px"; }
    if (s.dash) i.style.background = `repeating-linear-gradient(90deg, ${s.color} 0 4px, transparent 4px 7px)`;
    sp.append(i, document.createTextNode(s.name));
    el.append(sp);
  }
  return el;
}

function tableView(headers, rows) {
  const d = document.createElement("details");
  d.className = "tbl";
  const s = document.createElement("summary");
  s.textContent = "Show as table";
  const t = document.createElement("table");
  t.className = "data";
  const tr = document.createElement("tr");
  for (const h of headers) { const th = document.createElement("th"); th.textContent = h; tr.append(th); }
  t.append(tr);
  for (const r of rows) {
    const row = document.createElement("tr");
    for (const c of r) { const td = document.createElement("td"); td.textContent = c; row.append(td); }
    t.append(row);
  }
  d.append(s, t);
  return d;
}

function tooltip(wrap) {
  const tip = document.createElement("div");
  tip.className = "tip";
  wrap.append(tip);
  return {
    show(x, y, lines) {
      tip.replaceChildren();
      for (const [label, value, color] of lines) {
        const row = document.createElement("div");
        row.style.display = "flex"; row.style.alignItems = "center"; row.style.gap = "8px";
        if (color) { const k = document.createElement("span"); k.style.cssText = `width:12px;height:2px;background:${color};display:inline-block`; row.append(k); }
        const v = document.createElement("b"); v.textContent = value; v.style.color = INK.text;
        const l = document.createElement("span"); l.textContent = label; l.style.color = INK.text2;
        row.append(v, l);
        tip.append(row);
      }
      tip.style.opacity = 1;
      const w = wrap.clientWidth;
      tip.style.left = `${Math.min(Math.max(x + 14, 0), w - tip.offsetWidth - 4)}px`;
      tip.style.top = `${Math.max(y - 10, 0)}px`;
    },
    hide() { tip.style.opacity = 0; },
  };
}

// Line chart over a numeric x. series: [{name,color,pts:[{x,y,n}]}]
function lineChart({ series, xMax, xLabel, yLabel, yFmt = (v) => pct(v), xFmt = (v) => v, height = 260, yMin = 0, yMax = 1, yTicks = 4, xTicks = null }) {
  const W = 640, H = height, m = { l: 54, r: 92, t: 12, b: 36 };
  const wrap = document.createElement("div");
  wrap.className = "chart";
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  const x = (v) => m.l + (v / xMax) * (W - m.l - m.r);
  const y = (v) => H - m.b - ((v - yMin) / (yMax - yMin)) * (H - m.t - m.b);
  for (let t = 0; t <= yTicks; t++) {
    const v = yMin + ((yMax - yMin) * t) / yTicks;
    svg.append(svgEl("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), stroke: t === 0 ? INK.axis : INK.grid, "stroke-width": 1 }));
    const tx = svgEl("text", { x: m.l - 8, y: y(v) + 4, "text-anchor": "end", fill: INK.muted, "font-size": 11 });
    tx.textContent = yFmt(v);
    svg.append(tx);
  }
  const step = xMax <= 30 ? 5 : 10;
  const ticks = xTicks || Array.from({ length: Math.floor(xMax / step) + 1 }, (_, i) => i * step);
  for (const v of ticks) {
    const tx = svgEl("text", { x: x(v), y: H - m.b + 16, "text-anchor": "middle", fill: INK.muted, "font-size": xTicks ? 10 : 11 });
    tx.textContent = xFmt(v);
    svg.append(tx);
  }
  const xl = svgEl("text", { x: (m.l + W - m.r) / 2, y: H - 4, "text-anchor": "middle", fill: INK.text2, "font-size": 12 });
  xl.textContent = xLabel;
  svg.append(xl);
  const yl = svgEl("text", { x: 12, y: m.t + 4, fill: INK.text2, "font-size": 12, transform: `rotate(-90 12 ${m.t + 4})`, "text-anchor": "end" });
  yl.textContent = yLabel;
  svg.append(yl);
  const ends = [];
  for (const s of series) {  // s.dash: a dashed reference line (e.g. perfect calibration)
    const pts = s.pts.filter((p) => p.y != null);
    if (!pts.length) continue;
    svg.append(svgEl("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${x(p.x)},${y(p.y)}`).join(""), fill: "none", stroke: s.color, "stroke-width": s.dash ? 1.5 : 2, "stroke-dasharray": s.dash ? "5 4" : "none", "stroke-linejoin": "round", "stroke-linecap": "round" }));
    const last = pts[pts.length - 1];
    if (!s.dash) svg.append(svgEl("circle", { cx: x(last.x), cy: y(last.y), r: 4, fill: s.color, stroke: INK.surface, "stroke-width": 2 }));
    ends.push({ x: x(last.x) + 8, y: y(last.y) + 4, text: s.short || s.name });
  }
  ends.sort((a, b) => a.y - b.y);  // keep end labels from overlapping
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 13) ends[i].y = ends[i - 1].y + 13;
  for (const e of ends) {
    const lab = svgEl("text", { x: e.x, y: e.y, fill: INK.text2, "font-size": 11 });
    lab.textContent = e.text;
    svg.append(lab);
  }
  const cross = svgEl("line", { y1: m.t, y2: H - m.b, stroke: INK.axis, "stroke-width": 1, opacity: 0 });
  svg.append(cross);
  const dots = series.map((s) => { const c = svgEl("circle", { r: 4, fill: s.color, stroke: INK.surface, "stroke-width": 2, opacity: 0 }); svg.append(c); return c; });
  wrap.append(svg);
  const tip = tooltip(wrap);
  const xs = [...new Set(series.flatMap((s) => s.pts.filter((p) => p.y != null).map((p) => p.x)))].sort((a, b) => a - b);
  svg.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    let best = xs[0];
    for (const v of xs) if (Math.abs(x(v) - px) < Math.abs(x(best) - px)) best = v;
    cross.setAttribute("x1", x(best)); cross.setAttribute("x2", x(best)); cross.setAttribute("opacity", 1);
    const lines = [];
    series.forEach((s, i) => {
      const p = s.pts.find((q) => q.x === best);
      if (p && p.y != null) { dots[i].setAttribute("cx", x(best)); dots[i].setAttribute("cy", y(p.y)); dots[i].setAttribute("opacity", 1); lines.push([s.name, yFmt(p.y), s.color]); }
      else dots[i].setAttribute("opacity", 0);
    });
    lines.unshift([xFmt(best, true), "", null]);
    tip.show((x(best) / W) * r.width, e.clientY - r.top, lines);
  });
  svg.addEventListener("pointerleave", () => { cross.setAttribute("opacity", 0); dots.forEach((d) => d.setAttribute("opacity", 0)); tip.hide(); });
  return wrap;
}

// Horizontal grouped bars: groups [{label, values:[v per series]}]
function barChart({ groups, series, fmt = (v) => pct(v), max = 1 }) {
  const rowH = 20, gap = 2, groupGap = 18, labelW = 150, W = 640;
  const H = groups.length * (series.length * (rowH + gap) + groupGap);
  const wrap = document.createElement("div");
  wrap.className = "chart";
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}` });
  const x = (v) => (v / max) * (W - labelW - 60);
  const tip = tooltip(wrap);
  groups.forEach((g, gi) => {
    const y0 = gi * (series.length * (rowH + gap) + groupGap);
    const lab = svgEl("text", { x: 0, y: y0 + (series.length * (rowH + gap)) / 2 + 4, fill: INK.text2, "font-size": 12 });
    lab.textContent = g.label;
    svg.append(lab);
    series.forEach((s, si) => {
      const v = g.values[si];
      const y = y0 + si * (rowH + gap);
      const w = Math.max(v == null ? 0 : x(v), 2);
      const r = Math.min(4, w / 2);
      // 4px rounded data end, square at the baseline
      const path = `M${labelW},${y}h${w - r}a${r},${r} 0 0 1 ${r},${r}v${rowH - 2 * r}a${r},${r} 0 0 1 -${r},${r}h-${w - r}z`;
      const bar = svgEl("path", { d: path, fill: s.color });
      svg.append(bar);
      const t = svgEl("text", { x: labelW + w + 6, y: y + rowH / 2 + 4, fill: INK.text2, "font-size": 11 });
      t.textContent = v == null ? "–" : fmt(v);
      svg.append(t);
      const hit = svgEl("rect", { x: 0, y: y - 1, width: W, height: rowH + 2, fill: "transparent" });
      hit.addEventListener("pointermove", (e) => { const rr = svg.getBoundingClientRect(); bar.setAttribute("opacity", 0.8); tip.show(e.clientX - rr.left, e.clientY - rr.top, [[g.label, "", null], [s.name, v == null ? "–" : fmt(v), s.color]]); });
      hit.addEventListener("pointerleave", () => { bar.setAttribute("opacity", 1); tip.hide(); });
      svg.append(hit);
    });
  });
  wrap.append(svg);
  return wrap;
}

// Heat map of P(stay): rows = cards in line, cols = score bins. Sequential single hue.
function heatmap(heat) {
  const cols = heat[0].bins.length, rows = heat.length;
  const cw = 46, ch = 30, lw = 70, top = 4, W = lw + cols * cw, H = top + rows * ch + 34;
  const wrap = document.createElement("div");
  wrap.className = "chart";
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}` });
  const lo = [243, 228, 198], hi = [23, 83, 79]; // paper -> deep teal (single hue, light to dark)
  const color = (v) => `rgb(${lo.map((c, i) => Math.round(c + (hi[i] - c) * v)).join(",")})`;
  const tip = tooltip(wrap);
  heat.forEach((row, ri) => {
    const lab = svgEl("text", { x: lw - 8, y: top + ri * ch + ch / 2 + 4, "text-anchor": "end", fill: INK.text2, "font-size": 11 });
    lab.textContent = `${row.count} card${row.count > 1 ? "s" : ""}`;
    svg.append(lab);
    row.bins.forEach((b, ci) => {
      const x = lw + ci * cw, y = top + ri * ch;
      const ok = b.rate != null && b.n >= 30;
      const cell = svgEl("rect", { x: x + 1, y: y + 1, width: cw - 2, height: ch - 2, rx: 3, fill: ok ? color(b.rate) : "rgba(58,35,21,0.04)" });
      svg.append(cell);
      if (ok) {
        const t = svgEl("text", { x: x + cw / 2, y: y + ch / 2 + 4, "text-anchor": "middle", "font-size": 10, fill: b.rate > 0.5 ? "#FFF8EA" : INK.text });
        t.textContent = Math.round(b.rate * 100);
        svg.append(t);
        cell.addEventListener("pointermove", (e) => { const r = svg.getBoundingClientRect(); cell.setAttribute("stroke", INK.text); tip.show(e.clientX - r.left, e.clientY - r.top, [[`${row.count} cards, score ${b.lo}–${b.hi - 1}`, "", null], ["stay", pct(b.rate), null], ["decisions", String(b.n), null]]); });
        cell.addEventListener("pointerleave", () => { cell.removeAttribute("stroke"); tip.hide(); });
      }
    });
  });
  heat[0].bins.forEach((b, ci) => {
    const t = svgEl("text", { x: lw + ci * cw + cw / 2, y: top + rows * ch + 14, "text-anchor": "middle", fill: INK.muted, "font-size": 10 });
    t.textContent = `${b.lo}`;
    svg.append(t);
  });
  const xl = svgEl("text", { x: lw + (cols * cw) / 2, y: H - 2, "text-anchor": "middle", fill: INK.text2, "font-size": 11 });
  xl.textContent = "Round score so far (bin start)";
  svg.append(xl);
  wrap.append(svg);
  const scale = document.createElement("div");
  scale.className = "legend";
  scale.innerHTML = `<span>Stays 0%</span><span style="flex:0 0 140px;height:10px;border-radius:3px;background:linear-gradient(90deg,${color(0)},${color(1)})"></span><span>100%</span><span class="muted">Number = % of decisions that were "stay". Blank = too few decisions.</span>`;
  wrap.append(scale);
  return wrap;
}

function section(title, lede) {
  const el = document.createElement("section");
  el.className = "panel ins";
  const h = document.createElement("h2");
  h.textContent = title;
  el.append(h);
  if (lede) { const p = document.createElement("p"); p.className = "lede"; p.textContent = lede; el.append(p); }
  return el;
}

function take(text) {
  const d = document.createElement("div");
  d.className = "take";
  d.textContent = text;
  return d;
}

export async function render(app) {
  const data = await fetch(window.STATIC_SITE ? "api/insights.json" : "/api/insights").then((r) => r.json());
  if (!data.ready) {
    app.innerHTML = `<div class="panel prose"><h2>No analysis yet</h2><p>Run <code>python -m flip7.analyze</code> to have the bots play thousands of games and summarise how they play.</p></div>`;
    return;
  }
  const RL = data.tables.rl, SM = data.tables.smart;
  app.innerHTML = "";
  const root = document.createElement("div");
  root.className = "insights";
  app.append(root);

  const head = document.createElement("div");
  head.className = "pagehead";
  head.innerHTML = `<h1>How the bots play</h1>
    <p>Every number here comes from the bots playing each other: <b>${(data.decisions.rl.hit_stay + data.decisions.rl.target + data.decisions.rl.cards + (data.decisions.rl.new || 0)).toLocaleString()}</b> decisions by the RL bot at all-RL tables, compared with <b>SmartBot</b>, a hand-written card counter that plays like a careful human. Brutal Mode, 2–6 players. Model <code></code>, generated ${data.generated}.</p>`;
  head.querySelector("code").textContent = data.model;
  root.append(head);

  // ---- headline tiles
  const tiles = document.createElement("div");
  tiles.className = "tiles";
  const tile = (label, val, sub) => { const t = document.createElement("div"); t.className = "tile"; const l = document.createElement("div"); l.className = "lbl"; l.textContent = label; const v = document.createElement("div"); v.className = "val"; v.textContent = val; const s = document.createElement("div"); s.className = "sub"; s.textContent = sub; t.append(l, v, s); return t; };
  const mu = data.matchups || {};
  if (mu["2"]) tiles.append(tile("RL vs SmartBot, 1-on-1", pct(mu["2"].p, 1), `±${pct(1.96 * mu["2"].se, 1)} over ${mu["2"].games} games (fair: 50%)`));
  if (mu["4"]) tiles.append(tile("RL in a 4-player game vs 3 SmartBots", pct(mu["4"].p, 1), `fair share 25%: ×${(mu["4"].p * 4).toFixed(2)}`));
  tiles.append(tile("Typical stay point", `${num(RL.stay_threshold_by_n["4"], 0)} pts`, `SmartBot: ${num(SM.stay_threshold_by_n["4"], 0)} pts (4 players)`));
  tiles.append(tile("Rounds busted", pct(RL.outcomes["4"].bust_rate), `SmartBot: ${pct(SM.outcomes["4"].bust_rate)} (4 players)`));
  root.append(tiles);

  if (data.findings && data.findings.length) {
    const f = section("Tactics the bots found", "Where the RL bot's play differs from careful human play.");
    const grid = document.createElement("div");
    grid.className = "tactics";
    data.findings.forEach((item, i) => {
      // findings are "<b>Title.</b> explanation" (authored in analysis/findings.json)
      const m = item.match(/^<b>(.*?)<\/b>\s*(.*)$/s);
      const card = document.createElement("div");
      card.className = "tactic";
      card.innerHTML = `<span class="no">${String(i + 1).padStart(2, "0")}</span><h3>${m ? m[1] : ""}</h3><p>${m ? m[2] : item}</p>`;
      grid.append(card);
    });
    f.append(grid);
    root.append(f);
  }

  const grid = document.createElement("div");
  grid.className = "ins-grid";
  root.append(grid);

  // ---- stay curve with player-count filter
  const s1 = section("When do they stay?", "Share of hit-or-stay decisions that were \"stay\", by round score so far (not counting forced hits with The Zero).");
  const filt = document.createElement("div");
  filt.className = "seg";
  filt.style.marginBottom = "10px";
  const holder = document.createElement("div");
  const drawStay = (n) => {
    holder.replaceChildren();
    const ser = SERIES.map((s) => ({ ...s, short: s.key === "rl" ? "RL" : "SmartBot", pts: data.tables[s.key].stay_by_score[n].filter((b) => b.n >= 40).map((b) => ({ x: b.lo + 1.5, y: b.rate, n: b.n })) }));
    holder.append(legend(SERIES), lineChart({ series: ser, xMax: 60, xLabel: "Round score so far", yLabel: "stays", xFmt: (v, tip) => (tip ? `score ≈ ${Math.round(v)}` : v) }));
    holder.append(tableView(["Score", "RL stays", "SmartBot stays"], RL.stay_by_score[n].map((b, i) => [`${b.lo}–${b.hi - 1}`, pct(b.rate), pct(SM.stay_by_score[n][i].rate)])));
  };
  for (const n of ["all", "2", "3", "4", "5", "6"]) {
    const b = document.createElement("button");
    b.textContent = n === "all" ? "All tables" : `${n} players`;
    b.onclick = () => { filt.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); drawStay(n); };
    if (n === "all") b.classList.add("on");
    filt.append(b);
  }
  s1.append(filt, holder);
  drawStay("all");
  s1.append(take(`The RL bot keeps pushing much longer: it reaches a 50% chance of staying at about ${num(RL.stay_threshold_by_n["4"], 0)} points (4 players), against SmartBot's ${num(SM.stay_threshold_by_n["4"], 0)}.`));
  grid.append(s1);

  // ---- risk vs scoreboard
  const s2 = section("Risk appetite follows the scoreboard", "Round score where the bot becomes more likely to stay than hit, by how far ahead (+) or behind (−) it is versus the best rival. Excludes the final round.");
  const gapLabel = (r) => (r.lo <= -200 ? `≤ ${r.hi}` : r.hi >= 200 ? `≥ +${r.lo}` : `${r.lo > 0 ? "+" : ""}${r.lo} to ${r.hi > 0 ? "+" : ""}${r.hi}`);
  const rk = RL.risk_by_gap;
  const ser2 = SERIES.map((s) => ({ ...s, short: s.key === "rl" ? "RL" : "SmartBot", pts: data.tables[s.key].risk_by_gap.map((r, i) => ({ x: i, y: r.threshold })) }));
  const maxT = Math.max(45, ...ser2.flatMap((s) => s.pts.map((p) => p.y || 0)));
  const yTop = Math.ceil(maxT / 10) * 10;
  const shortGap = (r) => (r.lo <= -200 ? `≤${r.hi}` : r.hi >= 200 ? `≥+${r.lo}` : `${r.lo > 0 ? "+" : ""}${r.lo}…${r.hi > 0 ? "+" : ""}${r.hi}`);
  s2.append(legend(SERIES), lineChart({ series: ser2, xMax: rk.length - 1, yMax: yTop, yTicks: yTop / 10, xTicks: rk.map((_, i) => i), yFmt: (v) => `${Math.round(v)}`, xLabel: "Points ahead of (+) / behind (−) the best rival", yLabel: "stay point", xFmt: (v, tip) => (rk[v] ? (tip ? gapLabel(rk[v]) : shortGap(rk[v])) : "") }));
  s2.append(tableView(["Gap to best rival", "RL stay point", "SmartBot stay point", "RL decisions"], rk.map((r, i) => [gapLabel(r), num(r.threshold), num(SM.risk_by_gap[i].threshold), String(r.n)])));
  const behind = rk[0].threshold, ahead = rk[rk.length - 2].threshold;
  s2.append(take(`Far behind, the RL bot pushes on to ~${num(behind, 0)} points. Comfortably ahead, it banks at ~${num(ahead, 0)}. SmartBot's stay point barely moves with the score.`));
  grid.append(s2);

  // ---- heat map
  const s3 = section("Cards in hand vs points (RL bot)", "How often the RL bot stays, by how many number cards it holds and its round score. The card count matters: more cards means more numbers that can bust you.");
  s3.append(heatmap(RL.stay_heat));
  if (RL.six_cards.hit_rate != null) s3.append(take(`With six different numbers it goes for the seventh ${pct(RL.six_cards.hit_rate)} of the time (SmartBot: ${pct(SM.six_cards.hit_rate)}).`));
  grid.append(s3);

  // ---- Brutal: minus cards stay on a bust
  const MC = RL.minus_cards;
  if (MC && MC.stay_by_pbust_held) {
    const s3b = section("Minus cards are already paid for", "In Brutal Mode a bust keeps your minus cards, so they count whether you stay or bust: hitting only risks your number cards. RL bot's stay rate by bust chance, holding minus cards vs a clean line. Excludes the final round.");
    const MS = [{ name: "Clean line", color: "#008C82" }, { name: "Holding minus cards", color: "#7A3657" }];
    const pts = (bins) => bins.filter((b) => b.n >= 40).map((b) => ({ x: ((b.lo + b.hi) / 2) * 100, y: b.rate, n: b.n }));
    s3b.append(legend(MS), lineChart({ series: [{ ...MS[0], short: "Clean", pts: pts(MC.stay_by_pbust_clean) }, { ...MS[1], short: "Minus", pts: pts(MC.stay_by_pbust_held) }],
      xMax: 60, xLabel: "Chance the next card busts you", yLabel: "stays", xFmt: (v, tip) => (tip ? `bust chance ≈ ${Math.round(v)}%` : `${v}%`) }));
    s3b.append(tableView(["Bust chance", "Clean line stays", "With minus cards stays"], MC.stay_by_pbust_clean.map((b, i) => [`${Math.round(b.lo * 100)}–${Math.round(b.hi * 100)}%`, pct(b.rate), pct(MC.stay_by_pbust_held[i].rate)])));
    if (MC.pbust_threshold_held != null && MC.pbust_threshold_clean != null)
      s3b.append(take(`Holding minus cards it becomes more likely to stay than hit at about a ${pct(MC.pbust_threshold_held)} bust chance and ${num(MC.score_threshold_held, 0)} points; with a clean line at about ${pct(MC.pbust_threshold_clean)} and ${num(MC.score_threshold_clean, 0)} points. It judges the risk by its number cards, not by the round score.`));
    grid.append(s3b);
  }

  // ---- targeting
  const s4 = section("Who gets hit", "Where the action cards and modifiers go. \"The leader\" is the opponent with the highest total. A random pick among opponents would hit the leader about " + pct(RL.targeting.minus.random_leader_rate) + " of the time.");
  const TG = [["Just One More", "jom"], ["Flip Four", "flip4"], ["−2 … −10", "minus"], ["÷2", "div2"]];
  const h4a = document.createElement("h3"); h4a.textContent = "Used on themselves"; h4a.style.cssText = "font:600 11px/1.2 var(--f-text);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);margin:6px 0";
  s4.append(legend(SERIES, "rect"), h4a, barChart({ series: SERIES, groups: TG.slice(0, 2).map(([l, k]) => ({ label: l, values: [RL.targeting[k].self_rate, SM.targeting[k].self_rate] })) }));
  const h4b = document.createElement("h3"); h4b.textContent = "Aimed at the leader (when it's at an opponent)"; h4b.style.cssText = "font:600 11px/1.2 var(--f-text);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);margin:14px 0 6px";
  s4.append(h4b, barChart({ series: SERIES, groups: TG.map(([l, k]) => ({ label: l, values: [RL.targeting[k].leader_rate, SM.targeting[k].leader_rate] })) }));
  s4.append(tableView(["Card", "RL self", "Smart self", "RL leader", "Smart leader", "RL → busted player", "Smart → busted player"], TG.map(([l, k]) => [l, pct(RL.targeting[k].self_rate), pct(SM.targeting[k].self_rate), pct(RL.targeting[k].leader_rate), pct(SM.targeting[k].leader_rate), pct(RL.targeting[k].busted_when_possible), pct(SM.targeting[k].busted_when_possible)])));
  grid.append(s4);

  // ---- Brutal flip 7 choice + card actions
  const s5 = section("Brutal Mode: +15 for me, or −15 for you?", "After a Flip 7 the bot picks between the bonus and hitting a rival. Share of Flip 7s where it chose −15 for someone.");
  const f7 = RL.targeting.flip7, f7s = SM.targeting.flip7;
  s5.append(legend(SERIES, "rect"), barChart({ series: SERIES, groups: [
    { label: "When leading", values: [f7.penalty_when_leading, f7s.penalty_when_leading] },
    { label: "When trailing", values: [f7.penalty_when_trailing, f7s.penalty_when_trailing] },
    ...["2", "3", "4", "6"].map((n) => ({ label: `${n} players`, values: [f7.penalty_rate_by_n[n], f7s.penalty_rate_by_n[n]] })),
  ] }));
  const C = RL.cards, CS = SM.cards;
  s5.append(take(`Steal takes from the leader ${pct(C.steal.victim_leader)} of the time (SmartBot ${pct(CS.steal.victim_leader)}). Discard is used on its own line ${pct(C.discard.victim_self)} of the time (SmartBot ${pct(CS.discard.victim_self)}).`));
  grid.append(s5);

  if (RL.new_cards) grid.append(newCardsSection(RL.new_cards, SM.new_cards));

  // ---- outcomes table
  const s6 = section("Game stats by table size", "All-RL tables vs all-SmartBot tables.");
  const t = document.createElement("table");
  t.className = "data";
  const hdr = ["Players", "Rounds/game (RL · Smart)", "Avg round score", "Busts", "Flip 7s", "Negative rounds"];
  t.insertAdjacentHTML("beforeend", `<tr>${hdr.map((h) => `<th>${h}</th>`).join("")}</tr>`);
  for (const n of ["2", "3", "4", "5", "6"]) {
    const a = RL.outcomes[n], b = SM.outcomes[n];
    t.insertAdjacentHTML("beforeend", `<tr><td>${n}</td><td>${num(a.rounds)} · ${num(b.rounds)}</td><td>${num(a.avg_round_score)} · ${num(b.avg_round_score)}</td><td>${pct(a.bust_rate)} · ${pct(b.bust_rate)}</td><td>${pct(a.flip7_rate, 1)} · ${pct(b.flip7_rate, 1)}</td><td>${pct(a.neg_round_rate, 1)} · ${pct(b.neg_round_rate, 1)}</td></tr>`);
  }
  s6.append(t);
  const pos = RL.outcomes["4"].win_by_position;
  s6.append(take(`Seat order barely matters: at 4-player RL tables, the first player after the dealer wins ${pct(pos[0])} and the dealer ${pct(pos[3])} (fair 25%).`));
  grid.append(s6);

  if (data.calibration) root.append(calibrationSection(data.calibration));
  if (data.tactics && data.tactics.kinds) root.append(tacticsSection(data.tactics));
  if (data.conditions) root.append(conditionsSection(data.conditions));
  if (data.exploitability && data.exploitability.exploiters) root.append(exploitSection(data.exploitability, RL));

  if (data.matchups_table) {
    const s7 = section("Head-to-head results", "One bot in a rotating seat against copies of another. ± is the 95% interval.");
    const tb = document.createElement("table");
    tb.className = "data";
    tb.insertAdjacentHTML("beforeend", `<tr><th>Bot</th><th>Opponents</th><th>Players</th><th>Win rate</th><th>Fair share</th><th>Edge</th></tr>`);
    for (const r of data.matchups_table) tb.insertAdjacentHTML("beforeend", `<tr><td>${r.hero}</td><td>${r.villain}</td><td>${r.n}</td><td>${pct(r.p, 1)} ± ${pct(1.96 * r.se, 1)}</td><td>${pct(1 / r.n)}</td><td>×${(r.p * r.n).toFixed(2)}</td></tr>`);
    s7.append(tb);
    root.append(s7);
  }
}

// The Bust or Bank cards: who gets them, and when a Shakedown is paid.
function newCardsSection(N, NS) {
  const s = section("The Bust or Bank cards", "Who gets Special Delivery, Bounty, Double Dare, Shakedown and Spite, and when a Shakedown gets paid. \"The leader\" is the opponent with the highest total; a random pick among opponents would hit them about " + pct(N.bounty.random_leader_rate) + " of the time.");
  const CARDS = [["Special Delivery", "deliver"], ["Bounty", "bounty"], ["Double Dare", "dare"], ["Shakedown", "shakedown"], ["Spite", "spite"]];
  const h = document.createElement("h3"); h.textContent = "Aimed at the leader"; h.style.cssText = "font:600 11px/1.2 var(--f-text);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);margin:6px 0";
  s.append(legend(SERIES, "rect"), h, barChart({ series: SERIES, groups: CARDS.map(([l, k]) => ({ label: l, values: [N[k].leader_rate, NS[k].leader_rate] })) }));
  const h2 = document.createElement("h3"); h2.textContent = "Shakedowns paid, by the bust risk of taking a card instead"; h2.style.cssText = "font:600 11px/1.2 var(--f-text);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);margin:14px 0 6px";
  s.append(h2, barChart({ series: SERIES, groups: N.pay.pay_by_pbust.map((b, i) => ({ label: `${Math.round(b.lo * 100)}–${Math.round(Math.min(b.hi, 1) * 100)}%`, values: [b.n >= 30 ? b.rate : null, NS.pay.pay_by_pbust[i].n >= 30 ? NS.pay.pay_by_pbust[i].rate : null] })) }));
  s.append(tableView(["Card", "RL → leader", "Smart → leader", "RL → riskiest rival", "Smart → riskiest rival"], CARDS.map(([l, k]) => [l, pct(N[k].leader_rate), pct(NS[k].leader_rate), pct(N[k].max_pbust_rate), pct(NS[k].max_pbust_rate)])));
  const num = N.deliver.number, nums = NS.deliver.number;
  if (num && num.n) s.append(take(`Special Delivery: when the flipped number would bust a rival, the bot delivers it to one ${pct(num.busts_when_possible)} of the time (SmartBot ${pct(nums.busts_when_possible)}); when it's safe and nobody would bust, it keeps it ${pct(num.self_when_safe)} of the time.`));
  s.append(take(`Shakedown: the bot pays ${pct(N.pay.pay_rate)} of the time (SmartBot ${pct(NS.pay.pay_rate)}): ${pct(N.pay.pay_rate_stayed)} after staying, with points to protect, and ${pct(N.pay.pay_rate_active)} while still drawing.`));
  const g = N.per_game;
  s.append(take(`In an average all-RL game: ${num1(g.bounty_claim)} Bounties collected, ${num1(g.unlucky7)} players frozen by the Unlucky Frozen 7, ${num1(g.spite)} Spites set off, and ${Math.round(g.robin_points || 0)} points moved by Robin Hood and ${Math.round(g.tax_points || 0)} by Tax Collectors.`));
  return s;
}
const num1 = (x) => (x == null ? "–" : x.toFixed(1));

// How trustworthy the value network's win estimates are (python -m flip7.calibrate).
const CAT_NAMES = { "vs self": "against itself", "vs smart": "against SmartBot", "decision: hit_stay": "hit or stay", "decision: target": "aiming an action card",
  "decision: modifier": "giving a modifier", "decision: flip7": "Flip 7 bonus choice", "decision: steal": "Steal", "decision: discard": "Discard",
  "decision: swap1": "Swap, first card", "decision: swap2": "Swap, second card", endgame: "endgame (someone can finish)", "not endgame": "not the endgame" };
const catName = (k) => CAT_NAMES[k] || k;

function calibrationSection(cal) {
  const o = cal.overall;
  const s = section("How good are the bots' win estimates?",
    `The win chance the network gives itself, against how often it actually won when ${o.positions} positions were each played out ${cal.playouts} times to the end of the game. The dashed line is perfect calibration.`);
  const tiles = document.createElement("div");
  tiles.className = "tiles";
  const tile = (label, val, sub) => { const t = document.createElement("div"); t.className = "tile"; t.innerHTML = `<div class="lbl"></div><div class="val"></div><div class="sub"></div>`; t.children[0].textContent = label; t.children[1].textContent = val; t.children[2].textContent = sub; return t; };
  tiles.append(tile("Average error", pct(o.mae, 1), `${pct(o.noise_floor, 1)} of that is playout noise`));
  tiles.append(tile("Bias", `${o.bias > 0 ? "+" : ""}${pct(o.bias, 1)}`, o.bias > 0 ? "a little overconfident" : "a little underconfident"));
  if (o.ranked) tiles.append(tile("Best action found", pct(o.vh_agree), `value head, ${o.ranked} positions (policy: ${pct(o.pol_agree)})`));
  s.append(tiles);
  const perfect = { name: "Perfect calibration", short: "ideal", color: "#A08A70", dash: true, pts: [{ x: 0, y: 0 }, { x: 1, y: 1 }] };
  const seen = { name: "Network", short: "network", color: SERIES[0].color, pts: cal.reliability.map((b) => ({ x: b.pred, y: b.mc, n: b.n })) };
  s.append(legend([seen, perfect]), lineChart({ series: [seen, perfect], xMax: 1, xTicks: [0, 0.2, 0.4, 0.6, 0.8, 1], xFmt: (v, tip) => (tip ? `predicted ${pct(v)}` : pct(v)), xLabel: "Predicted win chance", yLabel: "actual" }));
  s.append(tableView(["Predicted", "Actual", "Positions"], cal.reliability.map((b) => [pct(b.pred), pct(b.mc), String(b.n)])));
  const rows = Object.entries(cal.categories).filter(([, v]) => v && v.positions >= 30).sort((a, b) => (b[1].mae - b[1].noise_floor) - (a[1].mae - a[1].noise_floor));
  const t = document.createElement("table");
  t.className = "data";
  t.insertAdjacentHTML("beforeend", "<tr><th>Situation</th><th>Positions</th><th>Error above noise</th><th>Bias</th><th>Best action found</th><th>Win chance lost by its pick</th></tr>");
  for (const [k, v] of rows) {
    const tr = document.createElement("tr");
    for (const c of [catName(k), String(v.positions), pct(Math.max(0, v.mae - v.noise_floor), 1), `${v.bias > 0 ? "+" : ""}${pct(v.bias, 1)}`, v.ranked ? pct(v.vh_agree) : "–", v.ranked ? pct(v.vh_regret, 1) : "–"]) {
      const td = document.createElement("td"); td.textContent = c; tr.append(td);
    }
    t.append(tr);
  }
  s.append(t);
  const vs = cal.categories["vs self"], sm = cal.categories["vs smart"];
  if (vs && sm) s.append(take(`Against copies of itself its estimates are off by ${pct(vs.mae, 1)}, about the ${pct(vs.noise_floor, 1)} that the playouts themselves wobble: as accurate as this test can tell. Against SmartBot it ${sm.bias < 0 ? "underrates" : "overrates"} its own chances by ${pct(Math.abs(sm.bias), 1)} on average: it judges positions as if everyone played as well as it does.`));
  if (rows.length) s.append(take(`Least reliable: ${rows.slice(0, 3).map(([k]) => catName(k)).join(", ")}. "Best action found" compares its pick with the best of up to six moves, each played out ${cal.action_playouts || 24} times; with that few playouts part of the gap is noise.`));
  return s;
}

// Hard decisions with independently verified answers (python -m flip7.tactics report).
const KIND_NAMES = { swap: "Swap", "action target": "Aiming Just One More / Flip Four", "modifier target": "Giving a minus card or ÷2",
  steal: "Steal", discard: "Discard", "flip7 bonus": "Flip 7: +15 or −15", "endgame hit/stay": "Hit or stay, someone can finish",
  "unsure hit/stay": "Hit or stay, network unsure" };
const kindName = (k) => KIND_NAMES[k] || k;

function tacticsSection(tac) {
  const kinds = Object.entries(tac.kinds).filter(([, v]) => v.positions);
  const per = kinds.length ? Math.round(tac.positions / kinds.length) : 0;
  const s = section("Where does it still go wrong?",
    `${tac.positions} hard decisions from the network's own games, ${per} of each kind. Every candidate move was played to the end of the game ${tac.verify.toLocaleString()} times on fresh shuffles of the unseen cards, with the network playing on afterwards. A verified mistake is one where another move wins clearly more often: the challenger is picked on one set of ${tac.select} shuffles and confirmed on a separate set, by more than two standard errors.`);
  const pts = (x, d = 1) => `${x > 0 ? "+" : ""}${(x * 100).toFixed(d)}`;
  const t = document.createElement("table");
  t.className = "data";
  const bots = tac.bots || [];
  t.insertAdjacentHTML("beforeend", `<tr><th>Decision</th><th>Positions</th><th>Network's verified mistakes</th><th>Average cost</th>${bots.map((b) => "<th></th><th></th>").join("")}</tr>`);
  const hdr = t.rows[0];
  bots.forEach((b, i) => { hdr.cells[4 + 2 * i].textContent = `${b.name}: fixes`; hdr.cells[5 + 2 * i].textContent = `${b.name}: gain per decision`; });
  for (const [k, v] of kinds) {
    const tr = document.createElement("tr");
    const cells = [kindName(k), String(v.positions), String(v.mistakes), v.mistake_cost != null ? `${(v.mistake_cost * 100).toFixed(1)} points` : "–"];
    for (const b of bots) {
      const r = b.kinds[k];
      cells.push(r && r.mistakes ? `${r.fixed} of ${r.mistakes}` : "–", r ? `${pts(r.gain, 2)} ± ${(r.ci95 * 100).toFixed(2)}` : "–");
    }
    for (const c of cells) { const td = document.createElement("td"); td.textContent = c; tr.append(td); }
    t.append(tr);
  }
  s.append(t);
  const total = kinds.reduce((a, [, v]) => a + v.mistakes, 0);
  const worst = kinds.filter(([, v]) => v.mistakes).sort((a, b) => b[1].mistakes * b[1].mistake_cost - a[1].mistakes * a[1].mistake_cost);
  if (worst.length) s.append(take(`The network made a verified mistake in ${total} of ${tac.positions} positions (${pct(total / tac.positions)}). Most of the damage is in ${worst.slice(0, 2).map(([k, v]) => `${kindName(k)} (${v.mistakes} mistakes, ${(v.mistake_cost * 100).toFixed(0)} points of win chance each)`).join(" and ")}.${worst.every(([k]) => !k.includes("hit/stay")) ? " Hit-or-stay decisions, the bulk of the game, had no verified mistakes." : ""}`));
  for (const b of bots) {
    const o = b.overall;
    s.append(take(`${b.name}${b.about ? ` (${b.about})` : ""} picks a different move from the network ${pct(1 - o.agree)} of the time, fixes ${o.fixed} of the ${o.mistakes} mistakes and gains ${pts(o.gain, 2)} ± ${(o.ci95 * 100).toFixed(2)} points of win chance per decision on average.`));
  }
  s.append(take("Gains are measured with the network playing on after the move, and each kind has the same number of positions however often it comes up. Steals and Swaps happen only a few times a game, so over a whole game these per-decision gains add up to much less."));
  if (tac.examples && tac.examples.length) {
    const ex = document.createElement("table");
    ex.className = "data";
    ex.insertAdjacentHTML("beforeend", "<tr><th>Decision</th><th>Table</th><th>Network's move</th><th>Better move</th><th>Win chance</th></tr>");
    for (const e of tac.examples) {
      const tr = document.createElement("tr");
      for (const c of [kindName(e.kind), `${e.players} players, round ${e.round}. Totals: ${e.totals.map((v, i) => (i ? `player ${i} ${v}` : `you ${v}`)).join(", ")}`, e.network, e.better,
        `${pct(e.network_value)} → ${pct(e.better_value)}`]) { const td = document.createElement("td"); td.textContent = c; tr.append(td); }
      ex.append(tr);
    }
    const d = document.createElement("details");
    d.className = "tbl";
    const sm = document.createElement("summary");
    sm.textContent = "Show the costliest mistake of each kind (players counted clockwise from you)";
    d.append(sm, ex);
    s.append(d);
  }
  return s;
}

// Whether the difficulty ladder holds under other rules (python -m flip7.conditions).
function conditionsSection(cond) {
  const s = section("Do the bots hold up under other rules?",
    "They were trained on Brutal Mode to 200. Each row is a paired benchmark against tables of SmartBots: the stronger bot's win share minus the weaker one's, in the same seats with the same cards (± is the 95% interval).");
  const t = document.createElement("table");
  t.className = "data";
  t.insertAdjacentHTML("beforeend", "<tr><th>Rules</th><th>Matchup</th><th>Players</th><th>Win share</th><th>Difference</th><th>Holds?</th></tr>");
  for (const r of cond.rows) {
    const tr = document.createElement("tr");
    const holds = r.diff - r.ci95 > 0 ? "yes" : r.diff + r.ci95 < 0 ? "reversed" : "unclear";
    for (const c of [r.condition, r.pair, String(r.n), `${pct(r.candidate, 1)} vs ${pct(r.incumbent, 1)}`, `${r.diff > 0 ? "+" : ""}${pct(r.diff, 1)} ± ${pct(r.ci95, 1)}`, holds]) {
      const td = document.createElement("td"); td.textContent = c; tr.append(td);
    }
    t.append(tr);
  }
  s.append(t);
  const pairs = [...new Set(cond.rows.map((r) => r.pair))];
  s.append(take(pairs.map((p) => {
    const rs = cond.rows.filter((r) => r.pair === p);
    const yes = rs.filter((r) => r.diff - r.ci95 > 0), rev = rs.filter((r) => r.diff + r.ci95 < 0);
    const ns = [...new Set(yes.map((r) => r.n))];
    const where = yes.length && yes.length < rs.length && ns.length === 1 ? ` (all at ${ns[0]} players)` : "";
    return `${p}: clearly ahead in ${yes.length} of ${rs.length}${where}${rev.length ? `, behind in ${rev.length}` : ""}.`;
  }).join(" ")));
  return s;
}

// How much a dedicated opponent can exploit the network (python -m flip7.exploitability).
function exploitSection(ex, RL) {
  const xs = ex.exploiters;
  const games = xs.reduce((t, x) => t + (x.games || 0), 0);
  const s = section("Can it be exploited?",
    `${xs.length} exploiters each trained for ${xs[0].hours} hours (${(games / 1e6).toFixed(1)} million games in all) against nothing but the network: one seat for the learner, the network in every other seat, playing exactly as it does here (its top move every time). Whatever weakness they find, they are free to use. Then each played on deals it never trained on. The gain is how much more often it wins than the network itself does from the same seats (± is the 95% interval).`);
  const signed = (d, ci) => `${d > 0 ? "+" : ""}${pct(d, 1)} ± ${pct(ci, 1)}`;
  const t = document.createElement("table");
  t.className = "data";
  t.insertAdjacentHTML("beforeend", "<tr><th>Exploiter</th><th>Players</th><th>Test games</th><th>Exploiter wins</th><th>Network wins (same seats)</th><th>Gain</th></tr>");
  const rows = [];
  for (const x of xs) {
    for (const r of x.bench.rows) {
      rows.push({ x, r });
      const tr = document.createElement("tr");
      for (const c of [x.from_scratch ? "Learned from scratch" : "Started as a copy", String(r.n), r.games.toLocaleString(), pct(r.candidate, 1), pct(r.incumbent, 1), signed(r.diff, r.ci95)]) {
        const td = document.createElement("td"); td.textContent = c; tr.append(td);
      }
      t.append(tr);
    }
  }
  s.append(t);
  const sig = rows.filter(({ r }) => r.diff - r.ci95 > 0);
  s.append(take(sig.length
    ? `Found an edge: ${sig.map(({ x, r }) => `${x.from_scratch ? "from scratch" : "started as a copy"}, ${r.n} players: ${signed(r.diff, r.ci95)}`).join("; ")}. A dedicated opponent can win that much more often than the network does from the same seats.`
    : `None of them found a weakness: every gain is within noise. That doesn't prove there's no exploit, but after ${(games / 1e6).toFixed(1)} million games of looking for one, it isn't easy to find.`));
  const four = xs.find((x) => x.players.length === 1 && x.players[0] >= 3);
  const aim = RL && RL.targeting && RL.targeting.flip4 ? RL.targeting.flip4.leader_rate : null;
  if (four && !sig.some(({ x }) => x === four)) {
    s.append(take(`The ${four.players[0]}-player exploiter tests one idea in particular: the network gangs up on the leader${aim ? ` (it aims Flip Four at the player with the most points ${pct(aim)} of the time)` : ""}, so maybe staying out of the lead and sprinting late beats it. The exploiter was free to learn that against a table of networks, and couldn't turn it into more wins.`));
  }
  const scratch = xs.find((x) => x.from_scratch && x.reached_level_hours != null);
  if (scratch) s.append(take(`The one that learned from scratch reached the network's level after about ${scratch.reached_level_hours < 1 ? `${Math.max(5, Math.round(scratch.reached_level_hours * 60 / 5) * 5)} minutes` : `${scratch.reached_level_hours.toFixed(1)} hours`} of training and got no further.`));
  return s;
}
