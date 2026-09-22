# Changes since the first inspection

**Security**
- JWT secret was a public placeholder: anyone could forge a login. Services now refuse to start
  with a missing/placeholder/short secret; `scripts/setup_env.py` generates a shared one.

**Bugs fixed** (each has a regression test that failed before the fix)
- Gateway: `/expenses` answered 307 redirects; upstream timeouts/protocol errors became raw 500s.
- Budgets: "All categories" form returned 422; duplicate "all categories" budgets were allowed.
- Reports: default month/year were frozen when the service started.

**Features**
- Budget alerts: expense -> budget -> notification, best-effort and de-duplicated.
- Gateway: request IDs and request logging (no tokens, bodies or query strings logged).
- Notification create is idempotent.

**Tests**: 7 -> 95 (gateway, config guard, user, budget, report, notification, integration).

**Repo hygiene**: fixed `.gitignore` typo, added `.gitattributes` (LF), README rewrite.
