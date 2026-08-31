# Reference dimensions

The second source in this pipeline. Telemetry alone cannot say which values are
*possible*, only which ones *occurred*. These four tables carry the documented
domain, extracted from the crow-archer playbook
`docs/playbooks/monitored-playtest.md`, which is the source of truth for the
wire format.

Joining them to the telemetry does two jobs:

1. **Conforms the dimensions.** A run state becomes a typed foreign key, not a
   loose string.
2. **Exposes coverage gaps.** A value that is documented but never observed is a
   gap in the recorded sessions, and it is invisible without this join.

| Table | Rows | Source |
|---|---|---|
| `app_states.csv` | 15 | playbook, pulse section, the render dispatch branches |
| `modes.csv` | 3 | playbook, pulse table |
| `characters.csv` | 5 | playbook, pulse table |
| `boss_kinds.csv` | 4 | playbook, observed boss values |

The contract in `contracts/` and these tables are generated from the same
document, so an enum cannot drift away from its dimension silently.
