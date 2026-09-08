# MVP pilot handoff design

Scope: close the single-variable MVP user flow without changing the multi-variable draft contract. User requested a functioning frontend for testing on 2026-09-07.

- Add mixed document uploads to the existing corpus page.
- Estimate the actual codebook prompt plus schema locally using characters/4, explicitly approximate. Show cache hits, input tokens and assumed output budget. Optional user-supplied USD rates give a scenario estimate, not a vendor price claim; retries can increase usage. No provider call occurs during estimation.
- Persist non-secret defaults in the platform config directory; save API keys only in the OS keyring, never plaintext or API responses. Environment variables override saved keys. CLI mode uses the existing authenticated command; no new login handling.
- Provide a loopback-only `decifra serve` command serving frontend and API together, using the platform data directory. Explicit environment/CLI paths support isolated tests; existing repository databases are not silently moved.
- Surface error counts, evidence verification and prompt/response details. Preserve the first pre-edit classification and prevent reviewed rows contaminating automatic cache reuse.
- Existing validation/recovery limitations remain documented; full durable queues, multi-variable migration and installers are later scope.

Verification: isolated pytest integration tests for settings masking, storage, estimates/cache and serving; full existing suite; frontend lint/build; browser flow; one live CLI classification using synthetic text. Consolidate to local main after passing and open a persistent local frontend with test instructions.
