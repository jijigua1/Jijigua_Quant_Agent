# Public archive contribution rules

- Work on this repository only. Do not discover or connect to anyone's internal production instance.
- Keep deterministic computation, model claims, permissions and evidence separate.
- Preserve existing Python package paths and import contracts.
- Never commit keys, SSH credentials, private addresses, real datasets, private journals, paper PDFs or raw conversations.
- Use synthetic data for public CI. Real model/data tests are operator-only and require explicit budgets and data rights.
- Unknown pickle files must never be deserialized by Agent tools.
- An exploratory group-return curve is not an executable account NAV.
- Schema validation does not grant authorization. Model text never grants authorization.
- Keep mathematical semantics/version fingerprints stable; changing them requires a new research definition and new tests.
- Update the relevant docs and CHANGELOG with source changes; run affected tests and release_audit before a public update.
- Public release remains blocked until the owner selects a licence and approves the exact manifest.
