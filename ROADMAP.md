# Roadmap

Work that nobody has built or decided yet. A built feature lives in the README
and `docs/`, not here.

## Experiments

These features run today, but nothing depends on them yet. Each one carries a
comment that names this section. On the decision date, keep it, finish it, or
cut it.

| Experiment | Kind | Where | Decide by |
|---|---|---|---|
| Type 2 reference dimensions | Lab | `pipeline/22_gold.sql`, ADR 0002 to 0004 | 2027-01-31 |
| Engineering and Dashboard views | Lab | `site/src/components/presentation.js` and `presentation.css` | 2027-01-31 |
| PostgreSQL fallback target | Lab | `pipeline/30_load_postgres.py` | 2027-01-31 |
| `session_context` | Prep | `pipeline/20_curated.sql` | 2027-01-31 |

A lab feature tests an idea. A prep feature waits for a consumer that does not
exist yet.

## Cleanup

### Urgent

Nothing open.

### When there is time

- `scripts/sanitize_flightlog.py` reads `origins.csv` twice. Two of its
  functions only pass through to `keep_only`, and it prints problems in two
  places.
- CI runs the pipeline twice in one job. The site loader runs `./demo.sh build`
  again after the build step. Build the site first, and let the checks read
  what that build wrote.
- `site/src/players.md` totals and groups kills in JS. The pipeline rule says a
  page may not total a business number. Move the totals to gold views, or relax
  the rule.
- The `docs/qa` evidence CSVs predate the full PostgreSQL load and the removal
  of `dim_mode`. Regenerate them with a live load.
- `docs/runbook-export.md` gives stale record counts. The exporter prints 22
  CloudEvents records, not 21, and 6664 trace spans, not 4666.

### Nice to have

- Keep one glossary and one topology diagram. `docs/hlad.md` and
  `docs/architecture.md` each carry both.
- If the two views stay, `html:root` can replace the selector pair in
  `presentation.css` that matches every `html` element.
- Read `docs/hlad.md`, `docs/architecture.md`, `docs/defect-log.md` and five
  site pages line by line for the same cleanup.
