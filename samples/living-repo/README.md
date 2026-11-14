# Living repo

A small shop service with a web storefront, used as Graveyard's false-positive test data.

Every function and import in here is live or legitimately ambiguous. Each file exists to
exercise one pattern from the spec (framework routes, reflection, re-exports, barrels, ...).
`expected.json` lists the only items Graveyard may report, all as `revive` or `unsure` with
`low` confidence. A `bury` verdict or `high` confidence anywhere is a failure of the accuracy gate.

`history.json` is replayed into a git repository with backdated commits, all over 400 days old.
