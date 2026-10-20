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
