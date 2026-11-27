# Stage 0B MCP probe

This fixture is disposable. Extract it into a fresh working directory outside every production repository. On Windows, run the commands from that directory.

    py -3.14 -B verify_boundaries.py
    py -3.14 -B run_probe.py direct-legacy direct-modern
    py -3.14 -B run_probe.py sdk-legacy
    py -3.14 -B run_probe.py codex-legacy codex-modern
    py -3.14 -B run_probe.py grok claude claude-modern gemini agy

`probe.py` is the same single stdio artifact used by all clients. It requires only Python’s standard library. `launch_probe.py` supplies a minimal child environment, captures diagnostics in the fixture, and limits runtime to 60 seconds. `run_probe.py` generates separate temporary client homes and explicit client registration. No test needs a provider inference request. The optional `sdk-legacy` control needs the already installed Python MCP SDK. The Gemini replay uses the normal npm bundle installed under the Windows user prefix. The Antigravity replay looks for Google’s default per-user install.

Each run creates a unique `runs` subdirectory and writes JSON case results and filtered server-side event traces. The main report distinguishes a connected server, a discovered catalog and an actual call. The catalog lists five operations, and `probe_echo` expects an exact round trip of:

    {"value":{"label":"WPAI","count":7,"enabled":true}}

The other operations return probe identity, an integer validation result, two pages of synthetic data or an intentional denial. A validation value must be an actual integer from 0 through 9. Boolean, numeric-string, out-of-range and unexpected-property inputs fail at the server. Cursors are process-local and expire twenty seconds after issuance. A denied call reports zero protected actions. The fixture exposes no shell, arbitrary I/O or listener.

`run_agy_live.py` is a separate optional test. It uses a Google sign-in you have already made and can consume your existing plan quota. It supplies MCP registration over ACP for a disposable workspace, creates separately named Antigravity app data, and will refuse to proceed if other user-level MCP servers are configured. It never signs in. Use it only if the account owner authorizes a real synthetic model turn.

    py -3.14 -B run_agy_live.py

Check the delivered files with SHA-256 against `SHA256SUMS.txt`. The records capture the audit observations. Replay creates new process IDs, cursors and session identifiers.
