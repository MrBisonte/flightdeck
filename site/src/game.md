---
title: The game
sql:
  game_summary: ./data/curated/game_summary.parquet
  character_usage: ./data/curated/character_usage.parquet
  boss_encounters_by_kind: ./data/curated/boss_encounters_by_kind.parquet
  run_outcomes: ./data/curated/run_outcomes.parquet
  fact_run: ./data/curated/fact_run.parquet
---

# The game

The other pages ask whether the data is sound. This page asks what happened in
the game. Same Parquet, different grain.

Every number here is the result of a query, and its SQL syntax sits above its
result for transparency. There are no hardcoded values typed into the text.

## 1. A run is not a page load

A page load opens when the browser loads the game and closes when it unloads.
A run starts when the player enters gameplay and ends when they leave it. One
page load can hold several runs, so the two grains give different answers to
the same question.

```sql echo id=summary
SELECT runs::INTEGER              AS runs,
       characters_played::INTEGER AS characters,
       maps_played::INTEGER       AS maps,
       total_sim_s,
       avg_run_wall_s,
       avg_run_sim_s,
       max_run_wall_s,
       min_kills::INTEGER         AS min_kills,
       max_kills::INTEGER         AS max_kills,
       avg_kills
FROM game_summary
```

```js
const g = summary.get(0);
display(html`<div class="grid grid-cols-3">
  <div class="card"><h2>Runs recorded</h2><span class="big">${g.runs}</span></div>
  <div class="card"><h2>Characters played</h2><span class="big">${g.characters}</span></div>
  <div class="card"><h2>Maps visited</h2><span class="big">${g.maps}</span></div>
</div>`);
```

## 2. How long is a run?

Two clocks again, and they disagree on purpose. Wall time counts every second
of the run. Play time counts only the states where the simulation advances, so
it excludes the talent tree, the pause overlay and the stage transitions.
`app_states.csv` decides which states are which, not the pipeline.

```js
display(html`<div class="grid grid-cols-3">
  <div class="card"><h2>Average run, wall</h2><span class="big">${g.avg_run_wall_s}s</span></div>
  <div class="card"><h2>Average run, playing</h2><span class="big">${g.avg_run_sim_s}s</span></div>
  <div class="card"><h2>Longest run</h2><span class="big">${g.max_run_wall_s}s</span></div>
</div>`);
```

```sql echo id=runs
SELECT run_id,
       character_key   AS character,
       first_map,
       maps_visited::INTEGER AS maps,
       duration_s      AS wall_s,
       sim_active_s    AS playing_s,
       kills::INTEGER  AS kills,
       outcome
FROM fact_run
ORDER BY started_srv
```

```js
display(Plot.plot({
  height: 220,
  marginLeft: 200,
  x: {label: "seconds", grid: true},
  y: {label: null},
  marks: [
    Plot.barX(runs, {y: "run_id", x: "wall_s", fill: "#d0d7de", sort: {y: "x"}}),
    Plot.barX(runs, {y: "run_id", x: "playing_s", fill: "#0969da"}),
    Plot.ruleX([0])
  ]
}));
```

The pale bar is wall time. The solid bar is time with the clock running. The
gap between them is menus, pauses and cutscenes.

```js
display(Inputs.table(runs, {rows: 12}));
```

## 3. Which characters get played?

The table lists every documented character, including the ones nobody chose.
That is a left join from the reference data, so an unplayed character shows as
a zero rather than vanishing.

```sql echo id=chars
SELECT character_key AS character,
       description,
       runs::INTEGER AS runs,
       sim_active_s  AS playing_s,
       best_kills::INTEGER AS best_kills,
       avg_kills
FROM character_usage
```

```js
display(Plot.plot({
  height: 200,
  marginLeft: 90,
  x: {label: "seconds played", grid: true},
  y: {label: null},
  marks: [
    Plot.barX(chars, {y: "character", x: "playing_s", fill: "#0969da", sort: {y: "-x"}}),
    Plot.ruleX([0])
  ]
}));
```

```js
display(Inputs.table(chars));
```

## 4. How do the boss fights end?

No column here claims a boss died at the player hands. The recorder emits
no defeat event, and the `win` state never occurs in this sample. So the pipeline reports the state
that followed each fight, and calls a reward screen `progressed`. That is the
closest available proxy for a defeat, and it is a proxy rather than evidence.

```sql echo id=bosses
SELECT boss_key AS boss,
       description,
       encounters::INTEGER AS encounters,
       progressed::INTEGER AS progressed,
       died::INTEGER       AS died,
       won::INTEGER        AS won,
       unresolved::INTEGER AS unresolved
FROM boss_encounters_by_kind
```

```js
display(Inputs.table(bosses));
```

```js
const totals = bosses.toArray?.() ?? Array.from(bosses);
const sum = (k) => totals.reduce((a, r) => a + Number(r[k] ?? 0), 0);
display(html`<div class="grid grid-cols-3">
  <div class="card"><h2>Boss fights</h2><span class="big">${sum("encounters")}</span></div>
  <div class="card"><h2>Reached a reward screen</h2><span class="big">${sum("progressed")}</span></div>
  <div class="card"><h2>Ended in death</h2><span class="big">${sum("died")}</span></div>
</div>`);
```

Those three cards add up the column above them. They introduce no number the
query did not already return.

## 5. How do runs end?

```sql echo id=outcomes
SELECT outcome,
       runs::INTEGER AS runs,
       avg_wall_s,
       avg_sim_s,
       best_kills::INTEGER AS best_kills
FROM run_outcomes
```

```js
display(Inputs.table(outcomes));
```

An unresolved run is one where the page load ended before the player left
gameplay. The run was real. Its ending was never recorded, so the pipeline
declines to guess one.

## What this page cannot tell you

The sample is six runs from three sessions of real play. Read the shapes, not
the averages.

Two limits come from the wire format rather than the sample size. There is no
boss defeat event, so `progressed` is the strongest word available. There is no
stage grain, so a run that walks three maps reports the span it covered and not
a row per map.
