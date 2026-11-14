# Haunted repo

A small inventory service with a web storefront, used as Graveyard's demo and as test data.

The dead code in here is deliberate. Do not clean it up, lint it or format it: `expected.json`
lists every item Graveyard must find, with the verdict and confidence it must give, and the
accuracy gate fails if the result differs.

`history.json` scripts the commit history. At startup Graveyard replays it into a real git
repository with backdated commits, so the ages shown for this sample are illustrative.
