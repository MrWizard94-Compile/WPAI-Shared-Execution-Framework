"""Static, public-only evidence for the three pinned Windows routes."""

BASE = "948d7692d4787a6f04e853177e5ff3f11c7c7efb"
CONSTITUTION = "0adf5ecee5f7f96ce3749944dc097a003731a6e9"
CODEX_SHA = "6ff1e1ca3b30fc8b914720681fcf5fe62e95f856"
GROK_MIRROR = "2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8"
GROK_UPSTREAM = "559751fdcec02d413e4c57c8832ab275e4f44980"
GROK_BUILD = "b06756fd6256"
RUNNER = "work/benchmarks/stage-1.2/agent_trials.py"
HISTORICAL_ROUTES = "outputs/stage-1.5/route-matrix.json"
WIN_CRED = "https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credreadw"
AGY_AUTH = "https://antigravity.google/docs/cli/install/"
AGY_SETTINGS = "https://antigravity.google/docs/settings"
GROK_ENTERPRISE = "https://docs.x.ai/build/enterprise"
GROK_MCP = "https://docs.x.ai/build/features/mcp-servers"

EXACT = "VERSION_MATCHED_SOURCE"
EXACT_DOC = "VERSION_MATCHED_OFFICIAL_DOC"
CURRENT = "OFFICIAL_DOC_CURRENT_ONLY"
HISTORY = "HISTORICAL_REPOSITORY_EVIDENCE"
INFERENCE = "INFERENCE"
UNKNOWN = "UNKNOWN"
LABELS = (EXACT, EXACT_DOC, CURRENT, HISTORY, INFERENCE, UNKNOWN)
VERSIONS = {"codex": "0.166.0", "antigravity": "1.5.18", "grok": "1.0.92"}
APPLICABILITY = {EXACT: "exact_version", EXACT_DOC: "exact_version", CURRENT: "unpinned",
                 HISTORY: "archived_route_only", INFERENCE: "conditional", UNKNOWN: "unestablished"}
TOPICS = frozenset(("state_root", "filesystem_state", "configuration_precedence", "environment", "trust",
                    "subscription", "api_key", "file_auth", "keyring", "ephemeral", "oauth_refresh",
                    "mcp_oauth", "account_registration", "managed_policy", "tool_sources", "auto_update",
                    "background", "ordinary_reuse"))


def claim(identity, label, topics, statement, path, section, limitation, revision=None):
    return {
        "id": identity, "class": label, "topics": topics.split(), "claim": statement,
        "source": {"location": path, "revision": revision, "locator": section,
                   "applicability": APPLICABILITY[label], "limitation": limitation},
    }


def source(identity, topics, statement, file, lines, symbol, limitation):
    base = f"https://github.com/openai/codex/blob/{CODEX_SHA}/codex-rs/"
    return claim(identity, EXACT, topics, statement, base + file + "#" + lines, file + " / " + symbol,
                 limitation, CODEX_SHA)


def historical(identity, topics, statement, path, section, limitation):
    return claim(identity, HISTORY, topics, statement, path, section, limitation, BASE)


def current(identity, topics, statement, url, section, limitation):
    return claim(identity, CURRENT, topics, statement, url, section, limitation)


def gap(identity, topics, statement, path, section, limitation):
    return claim(identity, UNKNOWN, topics, statement, path, section, limitation)


def codex_claims():
    return [
        source("cx-home", "state_root environment",
               "CODEX_HOME selects an existing directory that the resolver canonicalizes. Without that selector the OS user home supplies the .codex default.",
               "utils/home-dir/src/lib.rs", "L5-L62", "find_codex_home",
               "A canonicalized path can resolve an alias back to its original directory. The resolver only establishes this root."),
        source("cx-skip", "state_root configuration_precedence ordinary_reuse",
               "Ignoring the user config empties its layer and leaves the resolved home and auth backend independently selected. The exec ephemeral flag controls thread settings.",
               "exec/src/lib.rs", "L609-L627", "ConfigOverrides for exec",
               "Read with cx-config and cx-ephemeral. Neither exec flag constitutes a scoped subscription grant."),
        source("cx-config", "configuration_precedence state_root trust",
               "The Windows ordinary stack overlays packaged defaults, system defaults, cloud config fragments, user and selected profile, trusted project layers, then session overrides. The loader can also insert thread-specific layers and evaluates project trust. Its ignore-user-config path builds an empty user layer.",
               "config/src/loader/mod.rs", "L123-L535", "load_config_layers_state and load_user_config_layer",
               "Project ordering is represented as a grouped layer. Enforcement by managed requirements is separate from the preference merge."),
        source("cx-merge", "configuration_precedence tool_sources",
               "Configuration tables merge by key. An empty upper server map alone cannot establish removal of lower-layer servers.",
               "config/src/merge.rs", "L57-L128", "merge_toml_values",
               "Special fields have additional merge behavior. Source review cannot identify the effective policy on a particular host."),
        source("cx-system", "managed_policy configuration_precedence",
               "Windows system defaults use the ProgramData known-folder OpenAI/Codex config. The machine policy RequirementsPath selector can redirect requirements from the default colocated requirements.toml.",
               "config/src/loader/mod.rs", "L807-L838", "windows_codex_system_dir and system requirements resolution",
               "The selector and paths are public source symbols. No machine registry or policy file was queried."),
        source("cx-enforcement", "managed_policy configuration_precedence subscription ordinary_reuse",
               "Managed requirements can pin CLI credential storage and the ChatGPT base URL at auth bootstrap, and supply login and workspace restrictions.",
               "core/src/config/auth_keyring.rs", "L39-L78", "bootstrap_auth_config",
               "Managed policy remains authoritative. System/cloud requirements and cloud-sourced preferences must be evaluated independently of a private root."),
        source("cx-tool-policy", "managed_policy tool_sources auto_update",
               "Requirements can constrain MCP server identity, plugins, web search and startup update checking. The effective MCP catalog can include plugin registrations and host-owned app tools.",
               "config/src/config_requirements.rs", "L164-L205", "ConfigRequirements",
               "Managed requirements and server/tool catalog need separate checks. A permitted server name or a disabled web search setting alone is insufficient."),
        source("cx-runtime-tools", "tool_sources background",
               "Auth-gated MCP materialization uses the catalog, including previously added compatibility built-ins and extension overlays. Host-owned app tools have an additional gate.",
               "codex-mcp/src/mcp/mod.rs", "L404-L449", "effective_mcp_servers_from_configured",
               "The archived synthetic local stdio entry does not prove the absence of independently configured sources on another host."),
        source("cx-file", "subscription file_auth oauth_refresh",
               "The default file-backed CLI account store is auth.json under the resolved CODEX_HOME. Its schema holds authentication modes, OAuth token data and refresh metadata. File saves can truncate and rewrite the selected file.",
               "login/src/auth/storage.rs", "L47-L73", "AuthDotJson, also FileAuthStorage at lines 242–276",
               "The file backend is directory-scoped by resolution. A link into an ordinary store would expose that ordinary store to reads and writes."),
        source("cx-keyring", "keyring file_auth",
               "The direct account keyring backend uses a service entry scoped by a digest of the canonical Codex home. The keyring feature selects the native Windows backend.",
               "login/src/auth/storage.rs", "L285-L388", "compute_store_key and DirectKeyringAuthStorage",
               "Read with cx-windows-keyring. This is entry naming within a Windows credential set, not a separate Windows account boundary."),
        source("cx-windows-keyring", "keyring",
               "The pinned keyring crate enables the Windows-native facility on Windows.",
               "keyring-store/Cargo.toml", "L22-L23", "windows target features",
               "Windows logon scope comes from Microsoft platform documentation. This does not identify an ordinary user entry or its persistence mode."),
        claim("cx-os-scope", INFERENCE, "keyring ordinary_reuse",
              "Changing Codex home changes the native account entry key, not the current Windows token's credential set. The scratch entry cannot supply the existing ordinary account data without an independently authorized source.",
              WIN_CRED, "CredReadW description, read with cx-keyring and cx-windows-keyring",
              "The Windows API describes logon-token credential sets, not the actual machine's entries or the pinned client's selected backend."),
        source("cx-secret-keyring", "keyring file_auth",
               "The encrypted account backend uses a per-home encrypted file under secrets/codex_auth.age and an OS-keyring-held encryption key. The secret-auth-storage backend feature defaults on for Windows. The separate CLI storage mode still defaults to file.",
               "secrets/src/local.rs", "L40-L65", "LocalSecretsNamespace, path construction at lines 171–188 and key access at lines 260–289",
               "Read with cx-store-modes and the pinned features/src/lib.rs lines 1140–1145. This feature is consulted only when a keyring-capable mode is selected."),
        source("cx-store-modes", "file_auth keyring ephemeral",
               "The CLI storage modes are file, keyring, auto and ephemeral. Plain keyring does not use a file fallback. Auto load can fall back after a miss or error, and saves can fall back after a keyring error.",
               "login/src/auth/storage.rs", "L528-L588", "AutoAuthStorage and the backend selection at lines 647–694",
               "Read with config/src/types.rs lines 135–148, which marks file as default. The separate account-grant read path falls back on a miss and propagates keyring errors."),
        source("cx-ephemeral", "ephemeral ordinary_reuse subscription api_key environment",
               "The auth resolver checks an enabled and permitted CODEX_API_KEY input, then process-memory external auth, then permitted external access-token input, then the persistent backend. Explicit ephemeral storage stops before persistent lookup.",
               "login/src/auth/manager.rs", "L1536-L1623", "load_auth",
               "Ephemeral memory is populated within a process and is empty in a fresh CLI without supplied auth. A supplied API key or access token is not a handoff of an existing ordinary sign-in under the requirement."),
        source("cx-ephemeral-entry", "ephemeral background subscription",
               "Ephemeral auth is a process-global memory map keyed by the resolved home. The embedded app-server is part of the archived exec process. A separately managed client can supply app-server auth and handle delegated refresh.",
               "login/src/auth/storage.rs", "L604-L644", "EPHEMERAL_AUTH_STORE and EphemeralAuthStorage",
               "Separate app-server external_auth.rs lines 24–80 describe a different control route. It requires a credential owner and does not import a cached ordinary subscription into a fresh exec."),
        source("cx-refresh", "oauth_refresh account_registration ordinary_reuse",
               "ChatGPT OAuth refresh calls the auth service and can replace token fields and refresh metadata in the active storage backend.",
               "login/src/auth/manager.rs", "L1657-L1755", "persist_tokens and request_chatgpt_token_refresh",
               "Memory-only persistence does not establish no provider-side token rotation, session creation or effects on an existing login."),
        source("cx-device", "account_registration subscription",
               "Device login obtains a provider-side grant and exchanges it for authentication material before writes through the selected local backend.",
               "login/src/device_code_auth.rs", "L165-L232", "request_device_code and complete_device_code_login",
               "The source shows an authorization exchange, but does not prove whether the service adds or replaces account or device registrations."),
        source("cx-mcp-oauth", "mcp_oauth keyring file_auth",
               "MCP OAuth is a separate credential domain. File fallback uses .credentials.json under CODEX_HOME. Ordinary direct-keyring MCP entries use server identity and may be shared across homes; encrypted and enterprise variants have separate namespace rules.",
               "rmcp-client/src/oauth/credential_store.rs", "L334-L354", "shared ordinary direct-keyring entries",
               "Read with rmcp-client/src/oauth.rs lines 857 and 1056–1084 and secrets/src/local.rs lines 41–44. The archived local stdio server did not validate remote MCP OAuth isolation."),
        source("cx-logs", "filesystem_state state_root environment",
               "Log files default to CODEX_HOME/log. SQLite resolves effective config before CODEX_SQLITE_HOME before the selected home, with managed constraints. The embedded exec initializes state DB before starting its in-process client.",
               "core/src/config/mod.rs", "L4314-L4344", "SQLite and log resolution",
               "Read with exec/src/lib.rs lines 714–741. Thread ephemerality does not imply no other local writes or equivalent isolation under managed settings."),
        source("cx-history", "filesystem_state",
               "History is a distinct history.jsonl store. Rollout data has sessions and archived_sessions locations, and memories have a root under Codex home.",
               "message-history/src/lib.rs", "L49-L128", "history path and append machinery",
               "Read with rollout/src/lib.rs lines 86–87 and memories/read/src/lib.rs lines 10–17. Durability depends on the settings and invoked path."),
        source("cx-cache", "filesystem_state state_root tool_sources",
               "The Windows primary runtime plugin marketplace may resolve from the ordinary Windows profile cache outside CODEX_HOME. The regular plugin cache and models_cache.json are separate local state.",
               "core-plugins/src/marketplace_policy.rs", "L557-L573", "primary_runtime_marketplace_root",
               "Read with models-manager/src/manager.rs line 42 and core-plugins/src/script_attribution.rs line 109. This establishes discovery paths, not that each path was used in Stage 1.2."),
        source("cx-mcp-env", "environment background tool_sources",
               "The local MCP launcher composes default Windows env inputs, named variables and literal overrides with non-inheritable exclusions. The embedded exec may resolve executor state from the selected home or process environment.",
               "rmcp-client/src/utils.rs", "L16-L58", "create_env_for_mcp_server",
               "Read with exec/src/lib.rs lines 722–741. Server process and cwd are separate boundaries; a home selector does not sanitize the host or the effective process environment."),
        source("cx-update", "auto_update",
               "The pinned source implements update checks behind the startup setting in its TUI path; the setting defaults to true.",
               "tui/src/updates.rs", "L26-L42", "startup update check",
               "The archived route is exec with embedded app-server. This TUI evidence does not establish a complete no-update guarantee for all helper or extension paths."),
        historical("cx-archive", "state_root subscription file_auth ordinary_reuse trust tool_sources",
                   "Stage 1.2 recorded an existing ChatGPT subscription and used a disposable config with a reference to the ordinary file-backed authentication state. Its synthetic MCP entry and disabled features were limited to that fixture.",
                   RUNNER, "codex, lines 148–223 and outputs/stage-1.2/runs/codex-treatment.json",
                   "The ordinary-file before/after digest did not prove that reads, refresh or provider-side effects were absent. The archived credential reference is outside the allowed route."),
        current("cx-doc-auth", "ephemeral subscription api_key keyring",
                "The rolling authentication guide distinguishes ChatGPT sign-in from API-key auth and documents file, keyring, auto and process-memory caches.",
                "https://learn.chatgpt.com/docs/auth", "Authentication methods and Credential storage",
                "Pinned availability and behavior are proved by the source records. Current descriptions do not attest the archived account's state."),
        gap("cx-account-gap", "ordinary_reuse account_registration background",
            "No matched evidence establishes a stand-alone pinned exec route that retains the existing subscription without ordinary credential access and guarantees no provider-side session or device changes.",
            HISTORICAL_ROUTES, "routes.codex.isolation plus cx-ephemeral and cx-device",
            "Read-only source evidence covers client flows. Provider-side session replacement and effective host policy are unresolved."),
    ]


def antigravity_claims():
    return [
        historical("ag-archive-state", "state_root filesystem_state configuration_precedence environment",
                   "The archived Python ACP driver selected a relative app-data name and a disposable ACP log. It separately checked the usual Gemini and CLI settings locations.",
                   RUNNER, "antigravity, lines 242–265 and 366–374",
                   "A selector accepted by the archived runner and equal before/after hashes do not establish complete relocation, startup read avoidance or credential isolation."),
        historical("ag-archive-route", "subscription tool_sources background trust",
                   "The pinned run recorded an existing signed-in Google session. It used a Python driver and one session-scoped stdio MCP registration, disabled default customizations in the request path, and used allow-once handling for the selected tool.",
                   RUNNER, "antigravity, lines 301–350 and outputs/stage-1.2/runs/antigravity-treatment.json",
                   "The driver was not an editor. Worker identity, global exclusions and authentication backend were not measured."),
        current("ag-auth-doc", "subscription keyring api_key environment oauth_refresh",
                "Google's current CLI guide describes silent lookup of saved profiles through Windows Credential Manager. Personal Google OAuth and Gemini API-key mode are separate paths. The current API-key mode requires a matching provider setting and environment input.",
                AGY_AUTH, "Authenticate / Antigravity CLI / Local silent keyring sign-in and Using a Gemini API key",
                "These sections do not identify a 1.5.18 target name, persistence or token-refresh destination. ADC and enterprise routes are different from the archived subscription."),
        current("ag-shared-doc", "subscription keyring background ordinary_reuse",
                "The current documentation says local sign-in is shared across App, CLI, IDEs and SDK, and that ACP uses the CLI's sign-in and settings.",
                "https://antigravity.google/docs/cli/acp", "Overview and Quick start, read with Authenticate overview",
                "Cross-surface sharing is a current product description, not a pinned Windows storage or worker contract."),
        claim("ag-os-scope", INFERENCE, "keyring ordinary_reuse",
              "If 1.5.18 uses the documented Windows facility, its credential set follows the current logon token. Moving a data directory alone cannot establish a separate Windows account or prove a distinct credential entry.",
              WIN_CRED, "CredReadW credential set and current token",
              "Google's exact keyring namespace, lookup behavior and storage persistence are unverified."),
        current("ag-settings-doc", "configuration_precedence filesystem_state trust tool_sources environment",
                "The rolling settings guide lists CLI preferences under .gemini/antigravity-cli, global MCP/hooks/plugins under .gemini/config and workspace counterparts under .agents. CLI flags override supported preferences for a session. Startup can normalize and rewrite the settings file.",
                AGY_SETTINGS, "Antigravity CLI / Configuration file location, Other configuration files, and Command-line overrides",
                "Duplicate server names may leave an already running server in place. This is no proof of exact merge order, immutable startup or worker isolation on 1.5.18."),
        current("ag-worker-doc", "state_root background tool_sources",
                "The current ACP IDE guide describes optional per-session workers, with a worker required for editor-configured HTTP MCP.",
                "https://antigravity.google/docs/ide/extensions/acp", "ACP startup flag table / process-per-session",
                "The archived stdio route did not opt into per-session workers. Current documentation supplies no binding between worker separation and credential scope."),
        current("ag-logs-doc", "filesystem_state state_root",
                "The current hooks guide describes per-conversation transcript and artifact paths under an app-data root. It lists different default roots for CLI, App and IDE.",
                "https://antigravity.google/docs/hooks", "Input and output contract / Common input fields and transcriptPath",
                "The default documented CLI data root does not establish what the 1.5.18 app-data selector relocates, or where account and worker state live."),
        current("ag-tools-doc", "managed_policy tool_sources mcp_oauth",
                "Current MCP guidance documents global and workspace servers, exact-tool or wildcard permission matches, and OAuth for some external servers. Traced policy and credential cases for separate ACP distributions do not establish the CLI route's implementation.",
                "https://antigravity.google/docs/cli/mcp/", "Global and workspace server configs, MCP permissions and OAuth",
                "The archived local stdio route did not test external MCP OAuth, wildcard suppression, managed precedence or exclusion of other tool sources."),
        gap("ag-build-gap", "file_auth ephemeral keyring oauth_refresh mcp_oauth account_registration ordinary_reuse",
            "No matched implementation or release-tag evidence establishes 1.5.18 token files, in-memory support, keyring target and fallback, credential refresh writeback, or secondary session and device effects.",
            "https://antigravity.google/docs/changelog/", "Antigravity CLI release list and recorded Stage 1.5 Windows installer manifest identity",
            "The reviewed CLI changelog did not expose a 1.5.18 entry. A public binary digest authenticates the identity recorded by Stage 1.5, not the storage behavior."),
        gap("ag-state-gap", "state_root filesystem_state configuration_precedence managed_policy tool_sources auto_update trust environment background",
            "Exact Windows cache, history, session, memory, plugin and update roots and managed precedence are unverified. It is unknown whether a worker can reuse ordinary settings, trust, tools or auth outside the selected data name.",
            HISTORICAL_ROUTES, "routes.antigravity.version and isolation",
            "Current docs and the archived harness do not establish a complete exclusion gate for global/workspace/managed tool and state sources."),
    ]


def grok_claims():
    return [
        historical("gr-archive-auth", "subscription file_auth ordinary_reuse state_root",
                   "Stage 1.2 headless streaming JSON reported an existing xAI OAuth subscription. The harness used GROK_HOME and referenced ordinary .grok/auth.json from its scratch home.",
                   RUNNER, "grok, lines 375–415 and outputs/stage-1.2/runs/grok-treatment.json",
                   "Before/after file equality covers content at two points. It cannot show absence of reads, attempted refresh or server-side changes."),
        historical("gr-archive-config", "configuration_precedence tool_sources auto_update trust environment filesystem_state",
                   "The archived setup used scratch config and workspace trust, set import exclusions and auto-updater controls, and observed one MCP registration with no active hooks or enabled plugins. The control trace still recorded an unapproved search tool event.",
                   "outputs/stage-1.2/runs/grok-control.json",
                   "isolation, out_of_scope_tool_events and lifecycle, read with runner lines 375–439",
                   "A single treatment fixture can be scoped while a control remains unqualified. These facts do not prove source-wide precedence or updater exclusion."),
        current("gr-config-doc", "state_root configuration_precedence filesystem_state tool_sources trust environment",
                "Current settings describe GROK_HOME, user and project config, and separate managed defaults and requirement pins. Project config can add MCP, plugins and permission rules.",
                "https://docs.x.ai/build/settings", "Scopes and environment variables",
                "The published Unix examples are not proof of the pinned Windows system configuration location or effective contents."),
        current("gr-policy-doc", "configuration_precedence managed_policy tool_sources",
                "Current enterprise docs place user and system requirements above preferences and describe imported managed compatibility policy. Managed pins can constrain tools, sandbox and login.",
                GROK_ENTERPRISE, "Configuration and System-level policy",
                "This is a rolling precedence model including non-Windows path examples. It does not establish the Windows 1.0.92 precedence."),
        current("gr-auth-doc", "subscription api_key oauth_refresh file_auth environment account_registration",
                "Current docs distinguish refreshable browser/device and external OAuth paths from API-key use, describe per-model selection, and warn that enforced account policy can clear a noncompliant saved session.",
                GROK_ENTERPRISE, "Authentication and Restricting login methods",
                "Current credential ordering and refreshable modes do not establish 1.0.92 local writeback or account effects. An alternate token source or API key is not an ordinary subscription handoff."),
        current("gr-mcp-doc", "mcp_oauth tool_sources filesystem_state configuration_precedence environment",
                "Current MCP docs describe project replacement of same-name user entries, compatibility imports below native config, variable expansion, MCP OAuth in mcp_credentials.json and MCP stderr logs.",
                GROK_MCP, "Project scope, Compatibility, TOML environment expansion and Troubleshooting",
                "Current docs are not a pin to 1.0.92 and additional plugin or tool sources can be independent of the named MCP server."),
        current("gr-session-doc", "filesystem_state background",
                "Current sessions documentation describes local history, resumed sessions and optional sync. Enterprise documentation also identifies local session state under the Grok directory.",
                "https://docs.x.ai/build/features/sessions", "Sessions and session persistence",
                "Exact cache, memory, log, history, plugin, upgrade and leader state locations that may remain outside GROK_HOME are unverified for the pinned build."),
        claim("gr-mirror", INFERENCE, "state_root background mcp_oauth file_auth",
              "The inspected public snapshot describes a Grok home resolver, on-disk MCP credential storage and leader-mode code. Its own upstream marker differs from the archived Windows build marker. No correspondence is established.",
              f"https://github.com/xai-org/grok-build/blob/{GROK_MIRROR}/SOURCE_REV",
              f"SOURCE_REV identifies {GROK_UPSTREAM}. Compare archived build {GROK_BUILD}.",
              "Mirror behavior is useful context only. No storage or process conclusion from it is assigned to 1.0.92.", GROK_MIRROR),
        gap("gr-credential-gap", "ordinary_reuse keyring file_auth ephemeral mcp_oauth oauth_refresh account_registration",
            "Exact Windows keyring participation, MCP OAuth storage, refresh locking or replacement, memory-only options and server-side device or session effects are unresolved.",
            HISTORICAL_ROUTES, "routes.grok.version and isolation",
            "The file reference proves exposure in the archived harness, not exclusive credential lookup in the executable."),
        gap("gr-config-gap", "state_root configuration_precedence managed_policy tool_sources auto_update trust environment background filesystem_state",
            "No version-matched inventory proves all active configuration, import, plugin, search, trust, update or shared process paths stay within the selected boundary.",
            HISTORICAL_ROUTES, "routes.grok.version, isolation and observation limits",
            "The out-of-scope search in the historical control is a concrete reason to require independent effective-catalog proof."),
    ]


CATALOG = {"codex": codex_claims, "antigravity": antigravity_claims, "grok": grok_claims}


PREFERENCE_EDGES = (
    ("packaged", "system_defaults", "cx-config"), ("system_defaults", "cloud_defaults", "cx-config"),
    ("cloud_defaults", "user", "cx-config"), ("user", "profile", "cx-config"),
    ("profile", "trusted_project", "cx-config"), ("trusted_project", "runtime", "cx-config"),
    ("runtime", "enforced_requirements", "cx-enforcement"),
)


DECISIONS = {
    "codex": {
        "classification": "PARTIAL_ISOLATION",
        "blocked_by": "Private config and process-memory storage exist, but a fresh pinned exec cannot retain the ordinary subscription through those mechanisms without supplying or reading credential material. Managed state and provider-side effects also need proof.",
        "future": "Use the synthetic route. For a different future route, obtain a version-matched, provider-supported account handoff with an independent scope and documented session effects before requesting separate director approval.",
        "essential_gates": {"provenance": ("established", ("cx-home",)), "ordinary_subscription": ("contradicted", ("cx-ephemeral", "cx-archive")),
                            "account_nonmutation": ("unknown", ("cx-account-gap",)), "configuration_policy": ("partial", ("cx-system", "cx-tool-policy"))},
    },
    "antigravity": {
        "classification": "UNKNOWN",
        "blocked_by": "The 1.5.18 Windows credential namespace, token writeback, ordinary settings and worker sharing are unresolved. A directory selector does not settle Windows Credential Manager scope.",
        "future": "Obtain 1.5.18-specific storage and worker documentation. A separately approved Windows account or vendor-provided isolation mechanism could be evaluated only after subscription and account-side effects are documented.",
        "essential_gates": {"provenance": ("unknown", ("ag-build-gap",)), "ordinary_subscription": ("unknown", ("ag-build-gap", "ag-os-scope")),
                            "account_nonmutation": ("unknown", ("ag-build-gap",)), "configuration_policy": ("unknown", ("ag-state-gap",))},
    },
    "grok": {
        "classification": "PARTIAL_ISOLATION",
        "blocked_by": "The archive shows a scratch configuration and trust scope but relies on an ordinary auth reference. Pinned storage and policy precedence are unknown, and the historical control recorded an additional tool.",
        "future": "Require vendor proof for build b06756fd6256 covering credential scope, refresh and effective tool exclusions. Continue with the synthetic owner and relay while the pinned native route is blocked.",
        "essential_gates": {"provenance": ("unknown", ("gr-credential-gap", "gr-mirror")), "ordinary_subscription": ("unknown", ("gr-archive-auth", "gr-credential-gap")),
                            "account_nonmutation": ("unknown", ("gr-credential-gap",)), "configuration_policy": ("partial", ("gr-archive-config", "gr-config-gap"))},
    },
}
