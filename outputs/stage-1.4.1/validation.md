# Validation decision

## Defect

The Stage 1.4 lifecycle classifier could return `observed_failure` based on the presence of a force request even when the record could not prove its named experiment. A rechained `external_tree` ledger could omit the owner acknowledgment or receipt check. The receipt could also report `true`. A rechained `wrapper_only` ledger could omit the surviving-server observation or the after-wrapper job count. A rechained `local_pipe_close` ledger could omit the terminal read-side closure event. The original classifier already noticed some missing descendant evidence, but it did not enforce the complete after-wrapper checkpoint and cleanup order.

## Decision

Qualify the named scenario from the serialized ledger. Reuse the frozen v1 reader and lifecycle interpretation for canonical encoding, event-chain integrity, process and creation-identity uniqueness, and observer finalization consistency. Apply scenario-specific presence, value and partial-order checks directly to the verified events. This preserves Windows scheduling flexibility for unrelated observations while requiring the causal evidence each scenario was designed to collect. The new verdict has its own schema. The v1 ledger format remains in use.

A qualified external kill still reports `observed_failure`. Missing owner acknowledgment or receipt evidence yields `qualification: unavailable`. A present receipt, wrong boundary or contradictory ordering rejects the scenario. The wrapper's external peer closure is required after the force request. The inner server's pipe state stays unobserved. The deliberate observer crash yields `qualification: incomplete`. The guard process independently verifies the crash sentinel and cleanup as a test of that rejection.

The previously accepted Stage 1.4 workflow digest covers the workflow before this milestone. The compatibility runner reverses just the declared Stage 1.4 dispatch change and excludes the appended Stage 1.4.1 step. It verifies the recovered workflow against the unchanged manifest and runs the unchanged Stage 1.4 verifier on an isolated snapshot. Earlier tests remain in the workflow. The Stage 1.4.1 manifest covers the new deliverables and can remain stable when future CI steps are added. The shared workflow is checked at the Git candidate boundary.

The event chain validates integrity and ordering. A party able to replace a closed file can recalculate the chain. The strict gate validates the scenario contract within the existing trusted synthetic observer boundary. Native route qualification and any inference budget still require separate authorization.
