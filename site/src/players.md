---
title: Players
sql:
  run_scorecard: ./data/curated/run_scorecard.parquet
  run_pulse: ./data/curated/run_pulse.parquet
  kill_bursts: ./data/curated/kill_bursts.parquet
  kill_streaks: ./data/curated/kill_streaks.parquet
  kill_reconciliation: ./data/curated/kill_reconciliation.parquet
  run_funnel: ./data/curated/run_funnel.parquet
  character_combat: ./data/curated/character_combat.parquet
  fact_run: ./data/curated/fact_run.parquet
  fact_boss_encounter: ./data/curated/fact_boss_encounter.parquet
---

# Players

The other pages ask whether the data is sound. This page asks what a player
would ask: who scored most, how fast, how many at once, how far did the run
get. The event ring answers four of the six, and nothing published had read it
before.

<div class="only-engineering">

Every number here is the result of a query, and its SQL syntax sits above its
result for transparency. There are no hardcoded values typed into the text.

</div>
<div class="only-dashboard">

Every number here is the result of a query. The queries are hidden in this view.
Switch to Engineering, top right, to read the SQL above each result.

</div>

```js
// One label for a run, used by every section below. run_id is
// "<session>#<page load>/<run>", and a reader needs the day and the time to
// tell two runs apart. The separator is a middle dot, never a comma, because a
// comma inside a label reads as a column break in a table beside it.
function runLabel(runId) {
  const [session, rest] = String(runId).split("#");
  const [load, seq] = rest.split("/");
  const day = session.slice(5, 10);
  const time = session.slice(11, 16).replace("-", ":");
  return `${day} ${time} · load ${load} · run ${seq}`;
}

// Framework hands a query result back as an Arrow table. Every section reads
// rows the same way.
const rows = (t) => t.toArray?.() ?? Array.from(t);
```

## 1. Who scored most, and how fast?

`run_scorecard` is one row per run with every figure a leaderboard needs. It
ranks on the HUD counter, which is the number printed beside it. Section 4
puts that counter against the event ring.

```sql echo id=board
SELECT rank_by_kills,
       run_id,
       character_key,
       outcome,
       maps_visited::INTEGER AS maps,
       kills::INTEGER        AS kills,
       kill_events           AS kill_events,
       kills_per_min,
       sim_active_s,
       duration_s,
       t_first_kill_s,
       t_50_kills_s
FROM run_scorecard
ORDER BY rank_by_kills
```

```js
const board_rows = rows(board);
const bestBy = (key, dir = "desc") =>
  board_rows
    .filter((r) => r[key] !== null && r[key] !== undefined)
    .sort((a, b) => (dir === "desc" ? b[key] - a[key] : a[key] - b[key]))[0];

const top = bestBy("kills");
const fastest50 = bestBy("t_50_kills_s", "asc");
const bestRate = bestBy("kills_per_min");
const longest = bestBy("duration_s");

display(html`<div class="grid grid-cols-4">
  <div class="card">
    <h2>Most kills</h2><span class="big">${top.kills}</span>
    <p>${top.character_key} · ${top.sim_active_s} s playing</p>
  </div>
  <div class="card">
    <h2>Fastest to 50 kills</h2><span class="big">${fastest50.t_50_kills_s} s</span>
    <p>${fastest50.character_key} · first kill at ${fastest50.t_first_kill_s} s</p>
  </div>
  <div class="card">
    <h2>Best rate</h2><span class="big">${bestRate.kills_per_min}</span>
    <p>kills per minute · ${bestRate.character_key} · ${bestRate.kills} kills in ${bestRate.sim_active_s} s</p>
  </div>
  <div class="card">
    <h2>Longest run</h2><span class="big">${longest.duration_s} s</span>
    <p>${longest.character_key} · ${longest.outcome}</p>
  </div>
</div>`);
```

```js
display(Plot.plot({
  height: 240,
  marginLeft: 210,
  x: {label: "kills on the HUD counter", grid: true},
  y: {label: null},
  marks: [
    Plot.barX(board_rows, {
      y: (r) => `${r.rank_by_kills} · ${r.character_key} · ${runLabel(r.run_id)}`,
      x: "kills",
      fill: "var(--amber)",
      sort: {y: "-x"}
    }),
    Plot.text(board_rows, {
      y: (r) => `${r.rank_by_kills} · ${r.character_key} · ${runLabel(r.run_id)}`,
      x: "kills",
      text: (r) => `${r.kills} · ${r.kills_per_min} per min · ${r.outcome}`,
      dx: 6,
      textAnchor: "start"
    }),
    Plot.ruleX([0])
  ]
}));
```

Eight rows is eight rows. The sample is what it is, and the bar chart says so
without a caption.

## 2. What did the run look like, second by second?

`run_pulse` is one row per second of every run. It has existed since the gold
layer landed and nothing on the site drew it. One panel per run that scored a
kill, kills on a 0 to 100 scale every panel shares, hp on 0 to 9 beneath it.
The time scale is per run, so a 337 second run and an 84 second run each fill
their own width.

```sql echo id=replay
SELECT p.run_id,
       p.state,
       p.kills::INTEGER AS kills,
       p.hp::INTEGER    AS hp,
       round((p.srv - f.started_srv) / 1000.0, 1) AS t_s
FROM run_pulse p
JOIN fact_run f USING (run_id)
WHERE f.kills > 0
ORDER BY p.run_id, p.srv
```

```sql echo id=replay_runs
SELECT run_id,
       character_key,
       kills::INTEGER        AS kills,
       maps_visited::INTEGER AS maps,
       duration_s,
       outcome
FROM fact_run
WHERE kills > 0
ORDER BY kills DESC, sim_active_s
```

```js
// Which states get a shaded band. The reference dimension decides what the
// states are called; this only groups them into two bands a reader can see.
const BOSS = new Set(["boss_entrance", "boss_fight"]);
const PAUSE = new Set(["talents", "chooser", "stage_intro", "paused", "inventory"]);

// A run of consecutive pulses sharing a band becomes one rectangle. Drawn from
// the pulses themselves, so a band can never claim a second the data does not.
function bands(pulses) {
  const out = [];
  for (const p of pulses) {
    const kind = BOSS.has(p.state) ? "boss" : PAUSE.has(p.state) ? "pause" : null;
    const last = out[out.length - 1];
    if (kind === null) continue;
    if (last && last.kind === kind && last.x2 >= p.t_s - 2) last.x2 = p.t_s;
    else out.push({kind, x1: p.t_s, x2: p.t_s});
  }
  return out;
}

const replay_rows = rows(replay);
const byRun = new Map();
for (const r of replay_rows) {
  if (!byRun.has(r.run_id)) byRun.set(r.run_id, []);
  byRun.get(r.run_id).push(r);
}

const bandFill = {boss: "var(--amber-soft)", pause: "var(--line-soft)"};

// The same bands are drawn on both plots of a panel, so the shading lines up
// under the kills line and the hp line. The top of the rectangle follows the
// plot's own y domain, which is why it is a parameter.
const shadeMarks = (bandRows, top) => bandRows.map((b) =>
  Plot.rect([b], {x1: "x1", x2: "x2", y1: 0, y2: top, fill: bandFill[b.kind]}));

display(html`<div class="grid grid-cols-2">${rows(replay_runs).map((run) => {
  const pulses = byRun.get(run.run_id) ?? [];
  const span = [0, Math.max(1, ...pulses.map((p) => p.t_s))];
  const bandRows = bands(pulses);
  return html`<div class="card">
    <h2>${run.character_key} · ${run.kills} kills · ${run.duration_s} s${
      run.maps > 1 ? ` · ${run.maps} maps` : ""} · ${run.outcome.split(",")[0]}</h2>
    <p>${runLabel(run.run_id)}</p>
    ${Plot.plot({
      height: 130,
      marginLeft: 34,
      marginBottom: 18,
      x: {domain: span, label: null, ticks: 4},
      y: {domain: [0, 100], label: "kills", grid: true},
      marks: [...shadeMarks(bandRows, 100),
        Plot.lineY(pulses, {x: "t_s", y: "kills", stroke: "var(--amber)", strokeWidth: 1.5})]
    })}
    ${Plot.plot({
      height: 64,
      marginLeft: 34,
      marginBottom: 22,
      x: {domain: span, label: "seconds into the run", ticks: 4},
      y: {domain: [0, 9], label: "hp", ticks: 3},
      marks: [...shadeMarks(bandRows, 9),
        Plot.lineY(pulses, {x: "t_s", y: "hp", stroke: "var(--mark-public)", strokeWidth: 1.5, curve: "step-after"})]
    })}
  </div>`;
})}</div>`);
```

```js
display(html`<p class="legend">
  <span class="key" style="background: var(--amber)"></span> kills · 0 to 100 on every panel
  <span class="key" style="background: var(--mark-public)"></span> hp · 0 to 9
  <span class="key" style="background: var(--amber-soft)"></span> boss entrance and fight
  <span class="key" style="background: var(--line-soft)"></span> talents · chooser · stage intro · pause
</p>`);
```

The two runs that reached 99 made most of those kills inside the boss fight.
That is the shaded band on the right of the first two panels. hp drains in
steps rather than a slide, because a hit costs a whole point.

## 3. How many at once?

A burst is kills that land within 50 ms of each other, which is one hit. A
streak chains kills within a second. Both come out of one window over the same
stream, and the gap is the only thing that differs.

```sql echo id=bursts
SELECT run_id, character_key, kills::INTEGER AS kills,
       span_ms::INTEGER AS span_ms, started_ts
FROM kill_bursts
ORDER BY kills DESC, span_ms
```

```sql echo id=streaks
SELECT run_id, character_key, kills::INTEGER AS kills,
       span_ms::INTEGER AS span_ms
FROM kill_streaks
ORDER BY kills DESC
```

```js
const burst_rows = rows(bursts);
const streak_rows = rows(streaks);
const total_kills = burst_rows.reduce((n, r) => n + r.kills, 0);
const multi = burst_rows.filter((r) => r.kills >= 2);
const multi_kills = multi.reduce((n, r) => n + r.kills, 0);
const long_streaks = streak_rows.filter((r) => r.kills >= 2);
const streak_kills = long_streaks.reduce((n, r) => n + r.kills, 0);
const pct = (n, d) => Math.round((n / d) * 100);
const biggest = burst_rows[0];

display(html`<div class="grid grid-cols-4">
  <div class="card">
    <h2>Biggest burst</h2><span class="big">${biggest.kills} kills</span>
    <p>${biggest.character_key} · in ${biggest.span_ms} ms · one cast</p>
  </div>
  <div class="card">
    <h2>Multi-kill bursts</h2><span class="big">${multi.length}</span>
    <p>of ${burst_rows.length} bursts hit two or more</p>
  </div>
  <div class="card">
    <h2>Kills from bursts of 2+</h2><span class="big">${pct(multi_kills, total_kills)}%</span>
    <p>${multi_kills} of ${total_kills} kill events</p>
  </div>
  <div class="card">
    <h2>Kills inside 1 s streaks</h2><span class="big">${pct(streak_kills, total_kills)}%</span>
    <p>${streak_kills} kills in ${long_streaks.length} streaks</p>
  </div>
</div>`);
```

```js
const bySize = new Map();
for (const r of burst_rows) bySize.set(r.kills, (bySize.get(r.kills) ?? 0) + r.kills);
const size_rows = [...bySize].map(([size, kills]) => ({size, kills})).sort((a, b) => a.size - b.size);

display(Plot.plot({
  height: 220,
  x: {label: "kills in one burst within 50 ms", tickFormat: (d) => String(d)},
  y: {label: "kill events contributed", grid: true},
  marks: [
    Plot.barY(size_rows, {x: "size", y: "kills", fill: "var(--amber)"}),
    Plot.ruleY([0])
  ]
}));
```

Single kills are the tallest column and still a minority of all kills. The
columns on the right are single casts.

```js
display(Inputs.table(
  burst_rows.slice(0, 8).map((r) => ({
    character: r.character_key,
    "kills in burst": r.kills,
    "span ms": r.span_ms,
    run: runLabel(r.run_id)
  })),
  {rows: 8}
));
```

```js
const byChar = new Map();
for (const r of burst_rows) {
  const c = byChar.get(r.character_key) ?? {bursts: 0, multi: 0, biggest: 0, kills: 0};
  c.bursts += 1;
  c.multi += r.kills >= 2 ? 1 : 0;
  c.biggest = Math.max(c.biggest, r.kills);
  c.kills += r.kills;
  byChar.set(r.character_key, c);
}

display(Inputs.table(
  [...byChar].sort().map(([character, c]) => ({
    character,
    bursts: c.bursts,
    multi: c.multi,
    biggest: c.biggest,
    "avg kills": Math.round((c.kills / c.bursts) * 100) / 100
  })),
  {rows: 5}
));
```

The wizard averages the most kills per hit and the archer the fewest, which is
the character design showing up in the telemetry.

## 4. Do the counter and the events agree?

Two claims about the same fact meet the moment a leaderboard exists. The HUD
counter rides on every pulse. The kill events ride on the event ring. They
agree on six runs and disagree on two, and the two are the only runs that
walked into a second map.

```sql echo id=recon
SELECT run_id,
       character_key,
       maps_visited::INTEGER AS maps,
       counter_kills::INTEGER        AS counter_kills,
       event_kills,
       events_minus_counter::INTEGER AS events_minus_counter,
       agrees
FROM kill_reconciliation
ORDER BY event_kills DESC
```

```js
display(html`<div class="grid grid-cols-2">${rows(recon).map((r) => html`<div class="card ${
  r.agrees ? "good" : "bad"}">
  <h2>${r.character_key} · ${r.maps} map${r.maps > 1 ? "s" : ""}</h2>
  <span class="big">${r.counter_kills} → ${r.event_kills}</span>
  <p>${runLabel(r.run_id)} · ${r.agrees ? "agree" : `+${r.events_minus_counter} events`}</p>
</div>`)}</div>`);
```

```js
const off = rows(recon).filter((r) => !r.agrees).sort((a, b) => b.events_minus_counter - a.events_minus_counter);
const worst = off[0];
const other = off[1];

display(html`<div class="note">
  <b>Finding.</b> The HUD kill counter stops counting after the first stage. In
  the ${worst.maps} map run the counter read ${worst.counter_kills} at the end
  while the ring recorded ${worst.event_kills} kill events, a difference of
  ${worst.events_minus_counter}. The ${other.maps} map run shows the same shape:
  the counter read ${other.counter_kills} and ${other.events_minus_counter} more
  events fired after the stage changed. Every single map run agrees exactly.
  This is a defect in the game rather than in the pipeline. It is recorded in
  docs/defect-log.md and belongs to the crow-archer issue tracker.
</div>`);
```

The counter stays published as a claim. `fact_run` carries `kill_events` beside
it and `character_combat` counts events. The leaderboard above still ranks the
counter, so the rank and the number next to it come from one source.

## 5. How far do runs get?

A funnel over states the reference dimension documents. A renamed state would
show up in `reference_history` before it broke this chart.

```sql echo id=funnel
SELECT step, step_seq, runs
FROM run_funnel
ORDER BY step_seq
```

```js
const funnel_rows = rows(funnel);
const started = funnel_rows[0].runs;

display(Plot.plot({
  height: 210,
  marginLeft: 190,
  x: {domain: [0, started], label: "runs", grid: true},
  y: {label: null, domain: funnel_rows.map((r) => r.step)},
  marks: [
    Plot.barX(funnel_rows, {y: "step", x: "runs", fill: "var(--amber)"}),
    Plot.text(funnel_rows, {
      y: "step",
      x: "runs",
      text: (r) => `${r.runs} · ${Math.round((r.runs / started) * 100)}%`,
      dx: 6,
      textAnchor: "start"
    }),
    Plot.ruleX([0])
  ]
}));
```

`win` is a documented state nobody has reached. The zero is the honest end of
the funnel, and the funnel is the right place to show it.

```sql echo id=fights
SELECT e.run_id,
       e.character_key,
       e.kills_during::INTEGER AS kills_in_fight,
       f.kills::INTEGER        AS run_kills,
       e.sim_active_s          AS fight_s,
       e.outcome
FROM fact_boss_encounter e
JOIN fact_run f USING (run_id)
WHERE e.boss_key = 'crowking'
ORDER BY e.kills_during DESC
```

```js
display(Inputs.table(
  rows(fights).map((r) => ({
    character: r.character_key,
    run: runLabel(r.run_id),
    "kills in fight": r.kills_in_fight,
    "run kills": r.run_kills,
    share: `${Math.round((r.kills_in_fight / r.run_kills) * 100)}%`,
    "fight s": r.fight_s,
    then: r.outcome
  })),
  {rows: 8}
));
```

Most of a run's kills happen inside the Crow King fight. `then` is the state
that followed the fight, not a result. The recorder emits no defeat event, so
no column here claims a defeat.

## 6. How does each character fight?

Shots fired, arrows missed, hits taken and pickups, all from the event ring and
all per second with the clock running. `kills` here counts events, which is the
rule section 4 exists to justify.

```sql echo id=combat
SELECT character_key,
       runs,
       sim_s,
       shots,
       misses,
       kills,
       kills_per_shot,
       kills_per_min,
       hits_taken_per_min,
       pickups,
       boss_hits
FROM character_combat
ORDER BY character_key
```

```js
display(Inputs.table(
  rows(combat).map((r) => ({
    character: r.character_key,
    runs: r.runs,
    "playing s": r.sim_s,
    "kills per shot": r.kills_per_shot,
    "kills per min": r.kills_per_min,
    "hits taken per min": r.hits_taken_per_min,
    "arrows missed": r.shots > 0 && r.misses > 0
      ? `${Math.round((r.misses / r.shots) * 1000) / 10}%`
      : "no miss event for casts",
    pickups: r.pickups
  })),
  {rows: 5}
));
```

```js
const combat_rows = rows(combat);
display(Plot.plot({
  height: 200,
  marginLeft: 90,
  x: {label: "kills per shot", grid: true},
  y: {label: null},
  marks: [
    Plot.barX(combat_rows, {y: "character_key", x: "kills_per_shot", fill: "var(--amber)", sort: {y: "-x"}}),
    Plot.text(combat_rows, {
      y: "character_key",
      x: "kills_per_shot",
      text: (r) => `${r.kills_per_shot} · ${r.kills} kills from ${r.shots} shots`,
      dx: 6,
      textAnchor: "start"
    }),
    Plot.ruleX([0])
  ]
}));
```

A cast has no miss event in the wire format, so kills per shot is not
comparable across all three characters without saying so. Three characters and
eight runs is a shape, not a verdict.
