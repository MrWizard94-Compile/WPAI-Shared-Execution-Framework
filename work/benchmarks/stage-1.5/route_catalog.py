"""Versioned facts and plans from the Stage 1.5 read-only assessment."""

BASELINE = "3a6784ab7b7969361288a484542e18e6b6577a50"
CONSTITUTION = "0adf5ecee5f7f96ce3749944dc097a003731a6e9"
CODEX_REF = "6ff1e1ca3b30fc8b914720681fcf5fe62e95f856"
FROZEN_PLAN_SHA = "2655c6732c919abdd7624d36cd12296234f20443e09b78f5f354e5bf29003224"
UNKNOWN = "UNKNOWN"
OBSERVATIONS = (
    "provider_termination", "server_termination", "descendant_inventory", "job_accounting",
    "process_creation_identity", "actual_exit_codes", "client_to_server_pipe",
    "server_to_client_pipe", "genuine_eof", "observer_survival",
)


def layer(identity, kind, role, parent, launch, job, descendants, escape, identity_method, exits, stdio, eof, closer, receipt):
    return dict(id=identity, kind=kind, role=role, parent=parent, launch_owner=launch, job=job,
                descendants=descendants, escape=escape, identity=identity_method, exit=exits, stdio=stdio,
                eof=eof, pipe_closer=closer, receipt_risk=receipt)


HANDLE = "Compare retained process handle PID and creation FILETIME."
EXIT = "Wait for handle signal before reading the OS exit code."
OBSERVER = layer(
    "observer", "observer", "proposed", None, "Director-approved run controller would start the independent witness.",
    "Outside every job under test.", "Starts only the owned controller.", "No intentional breakaway.",
    HANDLE, EXIT, "Separate witness ledger. No private provider pipes by inheritance.",
    "Requires a recorded actor read plus its causal close.", "Controlled endpoint owners only.",
    "Final ledger is independent of any in-band receipt.")
OWNER = layer(
    "owner", "external_owner", "proposed", "observer", "Witness starts a separate controller with minimal job rights.",
    "Outside the provider job. Use separate server job for the split design.", "Starts the verified provider root and any independent server owner.",
    "Abort if containment or handle retention fails.", HANDLE, EXIT, "Owns only the explicitly created control endpoints.",
    "Can close an owned writer and wait for a trusted read event.", "A separately authorized force controller can terminate only its intended job.",
    "Loss of owner or witness must fail closed.")


def observations(*pairs):
    return {name: {"class": category, "limit": limit} for name, (category, limit) in zip(OBSERVATIONS, pairs, strict=True)}


def versions(number, stage0, binary, algorithm, digest, artifact, matched, current):
    return dict(stage0=stage0, stage_1_2=number, installed=number, executable=binary,
                identity_method="official_artifact_bytes", digest_algorithm=algorithm, digest=digest,
                artifact=artifact, matched_source=matched, rolling_docs_limit=current)


def protocol(version, acp=None):
    return {"mcp": version, "acp": acp}


def trials(number, mode, normal, forced, normal_evidence, forced_evidence):
    return [
        {"id": "normal", "client_version": number, "mode": mode, "sessions": 1,
         "subscription_usage": "expected_if_authorized", "fixture": "repo_health_v1",
         "expected": normal, "required_evidence": normal_evidence},
        {"id": "external_termination", "client_version": number, "mode": mode, "sessions": 1,
         "subscription_usage": "expected_if_authorized", "fixture": "repo_health_v1",
         "expected": forced, "required_evidence": forced_evidence},
    ]


CLEAN = [
    "Pin binary, synthetic package, protocol and exact tool allowlist.",
    "Observe exact verified synthetic reply and normal provider root completion.",
    "Record actor read EOF, actual output terminal read, retained-handle exit codes and independent job accounting.",
    "Require the witness to survive, finish and verify its ledger.",
]
FORCED = [
    "Observe one fixed synthetic reply before the separate owner records and issues the force request.",
    "Retain and wait on each subject handle; obtain actual exit codes and scope job accounting to the selected job.",
    "Attribute the observed closure, record inaccessible endpoints, and confirm observer finalization and receipt state.",
    "Classify the forced lifecycle as failure; a confirmed forced case can still qualify as a test.",
]


def routes():
    codex_mode = "noninteractive ephemeral execution with embedded app-server"
    agy_mode = "one headless driver with one stdio ACP session and session-scoped stdio MCP"
    grok_mode = "headless streaming JSON with a separately owned MCP fixture"
    return {
        "codex": {
            "product": "Codex CLI", "version": versions(
                "0.166.0", "0.166.0 in Stage 0A and Stage 0B", "codex.exe", "sha256",
                "9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42",
                "https://github.com/openai/codex/releases/tag/rust-v0.166.0", CODEX_REF,
                "Rolling flags were checked against the pinned Rust release. Ephemeral execution and skipping user config do not detach auth storage."),
            "historical_mode": codex_mode, "protocol": protocol("2025-06-18"),
            "native_qualified": False, "readiness": "NO-GO", "authorized_sessions": 0,
            "reason": "No verified nonmutating subscription isolation. The pinned local MCP termination path can kill before EOF.",
            "layers": [
                OBSERVER, OWNER,
                layer("client", "provider_client", "historically_observed", "owner",
                      "Stage 1.2 runner launched the terminal binary. The proposed independent controller would own launch.",
                      UNKNOWN, "The archived configuration selects directly launched local MCP. Other configurations can select executors.", UNKNOWN, HANDLE, EXIT,
                      "Root JSONL stdout when explicitly captured.", "Root pipe EOF is client output only.",
                      "Root or controller can close its endpoint.", "Client exit cannot supply a server receipt."),
                layer("app_runtime", "control_runtime", "matched_in_process", "client",
                      "Pinned execution entry point starts the app-server client in-process.",
                      "Shares the client process and any job assigned to it.", "Runtime can request a local or executor-backed MCP launch.",
                      "No independent process for the embedded runtime.", "Same identity as client.", "Same OS exit as client.",
                      "Internal channel, no separate OS stdio for this layer.", "Unavailable as a separate pipe.",
                      "Runtime teardown closes its internal transport.", "Process termination can interrupt internal shutdown."),
                layer("launcher", "mcp_launcher", "matched_source_branch", "app_runtime",
                      "Archived config omits environment ID. Pinned source defaults to local and starts the configured command directly.",
                      "Local Windows code attempts a no-breakaway job and can fall back to a process handle.",
                      "Configured child can create descendants within applicable limits.",
                      "Local job disallows breakaway when assigned; actual Stage 1.2 assignment or process-handle fallback is UNKNOWN.",
                      "Retain registered child handle before shutdown; actual containment must be witnessed.",
                      "Actual case code UNKNOWN.", "Owned by Codex on direct route.", "Inner read endpoints unavailable to current witness.",
                      "Local transport can terminate the MCP process before closing protocol pipes.",
                      "Provider can kill a registered in-band wrapper before receipt."),
                layer("server", "synthetic_mcp_server", "historically_observed", "launcher",
                      "Stage 1.2 named the pinned Python fixture as the configured command.", UNKNOWN, "Current fixture has no unrelated acquisition subprocesses.",
                      UNKNOWN, "Confirm exact child identity and job before the tool request.", "Stage 1.2 fixture OS exit code UNKNOWN.",
                      "MCP bytes are private to the launched stdio pair on the direct route.", "Historical receipt absent; clean server EOF UNKNOWN.",
                      "Codex launcher or external controller when separately authorized.", "Possible receipt loss on forced teardown."),
            ],
            "observations": observations(
                ("direct", "Future owned root launch exposes the terminal process handle."),
                ("independently_owned_launcher", "Controlled fixture launch can retain the server handle before provider teardown."),
                ("not_established", "Source selects local stdio for the archived config. Full historical native descendants are unverified."),
                ("not_established", "Outer job can be measured after containment succeeds; inner job access is unknown."),
                ("direct", "Owned root has creation identity. Child registration must also bind identity before teardown."),
                ("independently_owned_launcher", "Acquire distinct root, relay and server codes; no inference from PID loss."),
                ("proxy", "Byte-transparent relay can log the two segments separately."),
                ("proxy", "Return path stays separate from the client JSONL stream."),
                ("independently_owned_launcher", "Observe explicit writer close and a true server read EOF independently."),
                ("direct", "Place the witness outside the test jobs; verify role and terminal record."),
            ),
            "isolation": {"status": "configuration_only",
                          "historical": "Disposable Codex home restricted MCP and tools, with a reference to existing auth material.",
                          "future": "Use a blank workspace, private state root and version-matched inline configuration or scratch home. Preserve managed policy.",
                          "blocker": "Skipping the user config still uses Codex home for authentication. The file auth backend can write in place. A reference to ordinary auth is unsafe for this plan."},
            "recovery": "Close only owned endpoints and drain the controlled job; remove only the newly created scratch state after independent finalization.",
            "stops": ["Auth reuse or state mutation cannot be excluded", "Unexpected server, executable or executor branch",
                      "Identity, ownership, EOF or witness evidence missing", "Provider permission or quota boundary reached"],
            "trials": trials("0.166.0", codex_mode,
                             "A split route would test server EOF after relay closure. Direct provider-managed shutdown can end as a witnessed failure.",
                             "Explicitly forced target outcome, observed independently without substituting the relay exit.",
                             CLEAN + ["Prove which local launcher branch ran and label split-route results."],
                             FORCED + ["Record provider job exit separately from the independently owned server job."]),
        },
        "antigravity": {
            "product": "Google Antigravity CLI", "version": versions(
                "1.5.18", "1.5.18 in Stage 0B", "agy.exe", "sha512",
                "53605db7013dfed51e8c416d51e0c17a3b5ad0750c13da5669954ba4a281318746be0cf8cde2b256cfdb4bfbdade4badad1a0503931f8458416184549afa06b6",
                "https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/windows_amd64.json",
                UNKNOWN, "Rolling editor docs list opt-in process-per-session, including HTTP MCP needs. That option was absent from the tested stdio invocation."),
            "historical_mode": agy_mode, "protocol": protocol("2026-07-28", 1),
            "native_qualified": False, "readiness": "NO-GO", "authorized_sessions": 0,
            "reason": "Per-session MCP and scratch state were observed historically, but exclusive settings isolation, safe auth reuse and actual worker ownership are unverified.",
            "layers": [
                OBSERVER, OWNER,
                layer("acp_driver", "control_client", "historically_observed", "owner",
                      "The benchmark harness acted as the ACP client. An editor was not in the historical launch.",
                      "Controller boundary is separate from the agent job in the proposed design.",
                      "Launches the ACP-serving executable.", "No intentional breakaway in proposed harness.", HANDLE, EXIT,
                      "ACP JSON-RPC over driver-owned stdio.", "Driver EOF is evidence for ACP only.",
                      "Driver or serving process can close ACP.", "An ACP response cannot supply a server receipt."),
                layer("client", "provider_client", "historically_observed", "acp_driver",
                      "Headless ACP driver directly spawned agy.exe.", UNKNOWN,
                      "An optional session worker is documented in rolling editor guidance.", UNKNOWN, HANDLE, EXIT,
                      "Driver can capture the ACP transport.", "ACP channel closure does not expose inner MCP EOF.",
                      "Driver or serving process.", "Exit may precede private server receipt."),
                layer("acp_worker", "acp_session", "not_established", UNKNOWN,
                      "Session creation observed. Separate worker creation and launcher PID UNKNOWN in the pinned route.",
                      UNKNOWN, UNKNOWN, UNKNOWN, "Identify a newly created worker by retained handle if present.", UNKNOWN,
                      UNKNOWN, UNKNOWN, UNKNOWN, "Do not assume per-session containment or receipt survivability."),
                layer("launcher", "mcp_launcher", "not_established", UNKNOWN,
                      "ACP new-session request supplied a single stdio server command. Owning process UNKNOWN.",
                      UNKNOWN, UNKNOWN, UNKNOWN, "Bind actual owner to a job and retained process observation.", UNKNOWN,
                      "Private MCP descriptors lie below the ACP transport.", UNKNOWN, UNKNOWN, "In-band receipt exposure UNKNOWN."),
                layer("server", "synthetic_mcp_server", "historically_observed", "launcher",
                      "Pinned fixture came from the session-scoped stdio registration.", UNKNOWN, "Fixed fixture only.",
                      UNKNOWN, "Retain actual server handle and check creation identity.",
                      "Historical fixture application stop code zero; independent OS exit code UNKNOWN.",
                      "Inner MCP streams were not exposed by the ACP transport.",
                      "Stage 1.2 reported clean EOF; its stop event does not identify the cause independently.",
                      UNKNOWN, "Retain independent observations even if receipt is absent."),
            ],
            "observations": observations(
                ("direct", "Own the ACP-serving executable launch separately from client driver."),
                ("not_established", "Attach only after exact worker-to-server binding and creation checks."),
                ("not_established", "Session worker, reuse and escape behavior are unknown for the tested Windows route."),
                ("not_established", "Need observed membership and owned job scope before relying on counts."),
                ("direct", "Owned ACP root has creation identity; potential worker and server still require proof."),
                ("not_established", "ACP exit and historical server application exit do not supply the OS server code."),
                ("proxy", "Observe raw MCP direction separately from ACP messages."),
                ("proxy", "Separate MCP result transport from ACP display events; result bytes were unavailable historically."),
                ("independently_owned_launcher", "Require a trusted actual server read and corroborating writer closure."),
                ("direct", "Move the witness and records outside the controlled agent and server jobs."),
            ),
            "isolation": {"status": "partial_historical",
                          "historical": "Session-local stdio registration and disposable relative state, but the historical runner checked ordinary settings.",
                          "future": "Use a disposable driver, synthetic workspace, one per-session server, exact allow-once scope, no default customization and narrowly scoped host methods.",
                          "blocker": "No documented version-matched guarantee that the relative state option excludes ordinary settings or keeps cached sign-in unmodified."},
            "recovery": "End only the owned session and close the driver pipes. After retained handles and job accounting settle, remove only the recorded temporary state.",
            "stops": ["Unknown worker or inherited ordinary MCP settings", "Unexpected auth request, host method or permission expansion",
                      "Missing retained identity or actual EOF", "Unapproved state or quota change"],
            "trials": trials("1.5.18", agy_mode, "Direct-route clean closure must prove ACP completion and separate server EOF and exit.",
                             "Known force boundary, with ACP closure and MCP closure independently attributed.",
                             CLEAN + ["Record whether a separate session worker exists and distinguish ACP EOF and MCP EOF."],
                             FORCED + ["Capture the exact worker and server membership or report the case unavailable."]),
        },
        "grok": {
            "product": "Grok Build", "version": versions(
                "1.0.92", "1.0.92 stable, build b06756fd6256, in Stages 0A, 0B and 0C", "grok.exe", "sha256",
                "060e51f93743b540e59c5cf9c81c0ce7b48b61c263f09235d981a6ababb1c9d7",
                "https://x.ai/cli/grok-1.0.92-windows-x86_64.exe", UNKNOWN,
                "Public mirror revision differs from b06756fd6256. Its stdio spawn and shared pool are context only; rolling docs also cover modes absent from the pilot."),
            "historical_mode": "headless streaming JSON, no TUI or ACP session for Stage 1.2",
            "protocol": protocol("2025-11-25"), "native_qualified": False, "readiness": "NO-GO", "authorized_sessions": 0,
            "reason": "Archived native headless probe exited nonzero without EOF. The supervised split route is promising, but isolation and approved auth reuse are unresolved and extra tool activity is disqualifying.",
            "layers": [
                OBSERVER, OWNER,
                layer("client", "provider_client", "historically_observed", "owner",
                      "Stage 1.2 harness started the headless terminal executable.", UNKNOWN,
                      "HEAD source has shared MCP pools; leader and background processes for the pinned headless route UNKNOWN.",
                      UNKNOWN, HANDLE, EXIT, "Root emits streaming JSON events.", "Root output closure is not server EOF.",
                      "Root or launch controller.", "Root completion does not establish receipt or cleanup."),
                layer("acp_alternative", "alternate_route", "excluded_historical_route", None,
                      "Separate ACP launcher was tested as Stage 0C control-plane evidence only.", UNKNOWN, UNKNOWN, UNKNOWN,
                      "Distinct root identity if used in a later route.", "Stage 0C ACP root exit zero and probe exit one were distinct.",
                      "ACP JSON-RPC is separate from MCP stdio.", "Stage 0C native probe observed no EOF.",
                      "ACP session close terminated the test probe in Stage 0C.", "Unverified for the Stage 1.2 headless route."),
                layer("launcher", "mcp_launcher", "historically_observed", UNKNOWN,
                      "Qualified headless calls reached the configured server. Exact historical OS launcher hierarchy UNKNOWN.",
                      UNKNOWN, UNKNOWN, UNKNOWN, "Retain and bind direct child or relay handle through known ownership.",
                      "Stage 0C native probe process exit one observed through a retained handle.",
                      "Native MCP pipes belong to the launch path.",
                      "Earlier supervised route closed server stdin. Server read EOF was observed separately from relay disconnect.",
                      "Historical native route could end the probe before read EOF.", "Early termination can lose in-band proof."),
                layer("server", "synthetic_mcp_server", "historically_observed", "launcher",
                      "Pinned fixture was configured as one exact allowlisted local server.", UNKNOWN, "Fixed fixture only.",
                      UNKNOWN, "Use known server create handle outside provider job in split route.", "Stage 1.2 fixture OS exit code UNKNOWN.",
                      "Stage 0C disjoint owner retained both server stdio ends.", "Independent EOF only established on the Stage 0C supervised probe.",
                      "Native launcher or separate owner, depending on the route.", "Keep relay and server receipts distinct."),
            ],
            "observations": observations(
                ("direct", "Future owned headless root launch can retain its handle."),
                ("independently_owned_launcher", "Stage 0C separate owner is a precedent; qualify current fixture separately."),
                ("not_established", "Exact headless leader, workers and breakaway behavior have no matched source proof."),
                ("not_established", "Record provider and independent fixture jobs separately; no descendant assumptions."),
                ("direct", "Retain headless root identity; separate owner can retain its own server identity."),
                ("independently_owned_launcher", "Real server code comes from its own retained handle; relay exit is separate."),
                ("proxy", "Stage 0C local relay precedent observed disconnect, then the owner closed the server writer."),
                ("proxy", "Use byte-transparent relay and track provider-facing and fixture-facing terminals."),
                ("independently_owned_launcher", "Require actual synthetic server read EOF and explicit relay/owner boundary."),
                ("direct", "Observer is outside the provider and server jobs; verify its terminal record."),
            ),
            "isolation": {"status": "configuration_only",
                          "historical": "Disposable Grok home and workspace trust scope, exact qualified tool, disabled imports, with an auth reference.",
                          "future": "A fresh isolated home and workspace must exclude imported MCP, hooks, plugins, background agents and every tool outside the exact allowlist.",
                          "blocker": "No verified nonmutating auth reuse in the isolated home. Normal profile changes and inherited tool routes are disallowed."},
            "recovery": "Close the relay and its one-time local capability; reap independently owned jobs before deleting only the scratch home and workspace.",
            "stops": ["Built-in lookup or unexpected provider action", "Missing pinned permission support or safe auth",
                      "Relay leakage, unknown descendant or unobservable pipe outcome", "Unapproved quota or state mutation"],
            "trials": trials("1.0.92", grok_mode, "Supervised route can test normal owner-driven server EOF; the direct route remains unqualified.",
                             "Separate forced provider boundary and underlying server outcome with both ledgers retained.",
                             CLEAN + ["Use the exact named tool; abort on the historical out-of-scope lookup behavior."],
                             FORCED + ["Distinguish forced relay closure from deliberate independent server cleanup."]),
        },
    }
