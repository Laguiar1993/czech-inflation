# Refactor queue after the 7 September cleanup

Completed mechanically: shared wedge, shared compound trailing-year helper,
redundant cold-error slices, unused CFG import, shared loaders separated from
research drivers, two unused root duplicate modules, import-safe scoreboard,
portable DB/X13 paths and offline acceptance tests. See CLEANUP_REVIEW_2026-09-07.md.

The original queue is preserved in docs/history/REFACTOR_QUEUE_original.md.
Two entries there were not safe no-ops: changing the alcohol seed can change
weights, and standardization must remain in ridge as well as the warm forest.
Neither was changed. SQL unification and wider research-script migration are
optional later cleanups, not necessary to run the operating pair.

Next priority is the separately versioned correctness work in
docs/LIVE_READINESS.md. Any numerical change needs its own declared rationale,
all affected-origin differences and edge/availability tests. Historical
bit-identity alone cannot detect a live-edge bug.
