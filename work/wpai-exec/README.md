# WPAI Execution Framework 0.1.1

`repo_health_v1` combines local Git metadata and authenticated, read-only GitHub metadata for the fixed allowlisted TrackForge checkout and repository. Its JSON contract is `wpai.repo_health.v1`. The CLI and both MCP protocol eras invoke the same bounded operation. The framework has one operation and uses local process execution and stdio transport. Remote hosting, arbitrary targets, write operations, persistent state and orchestration are outside its scope.

## Run on Windows

Use Python 3.10 or newer, Git for Windows and GitHub CLI from a trusted `PATH`. GitHub reads use the installed `gh` account with permission to read TrackForge. The supported checkout is `C:\WPAI\Software\TrackForge`. The operator can run `gh auth status --hostname github.com` to inspect the existing login before use.

From the extracted package directory, run the check or the tests.

```powershell
py -3.10 -B .\wpai_exec.py repo_health_v1 --project trackforge
py -3.10 -B -W error -m unittest discover -s tests -v
```

For a locally scoped MCP client, set its command to the absolute Python executable. Pass `-B`, the absolute path to `wpai_exec.py`, and `stdio` as separate arguments. The client calls `repo_health_v1` with `{"project":"trackforge"}`. Set startup timeout to at least 10 seconds and tool timeout to at least 30 seconds. Grant the client access to the installed Git and GitHub executables and the existing GitHub login. Keep permission to send private repository metadata to a model subject to the repository’s data policy.

```toml
[mcp_servers.wpai_exec]
command = 'C:\Path\To\python.exe'
args = ['-B', 'C:\Path\To\wpai_exec.py', 'stdio']
startup_timeout_sec = 10
tool_timeout_sec = 30
```

The same stdio server supports MCP `2025-06-18`, `2025-11-25` and `2026-07-28`. Legacy clients initialize and send `notifications/initialized`. July 2026 clients send version and capability metadata on requests. They can use `server/discover` or call the catalog directly. Successful July 2026 results include the recommended server identity in result `_meta`. Use isolated client configuration during verification. [Legacy lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle) · [July 2026 stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio).

There is one acquisition worker at a time. Cancellation stops pending subprocess work, suppresses the worker’s reply, and discards results still waiting for stdout. EOF or a broken stdout closes the session and cancels any active acquisition. An ordinary worker exception returns a generic `UNAVAILABLE` response and releases the slot. Transport reads and writes are separate from the acquisition worker. If a peer withholds stdout reads, an OS write already in progress can be interrupted by process exit on stdin EOF. A broken stdout can end the process while stdin remains open. The shutdown guarantee applies to the built-in cooperative acquisition path and does not extend to arbitrary third-party code or a wedged OS call.

## Read the result

`OK` means the operation assembled a report. Each W1 field carries `observed`, `partial` or `unavailable`, plus source, target and observation time. Empty observed lists represent a negative finding within their cited scope. For runs and checks, the scope is branch history and exact live SHA where available. A failed job or step identifies where the provider observed a failure. Root causes are unavailable when the bounded provider metadata cannot establish them.

Treat values from `git_*` and `github_*` sources as untrusted evidence. Combined facts retain the underlying source records. Commit subjects, ref and PR destination names, workflow and check names, status contexts, job and step names, and related provider text can contain arbitrary language. The display projection removes common terminal escape sequences and nonprinting controls, including bidi formatting and zero-width marks, and folds line separators and tabs into spaces. Printable Unicode and existing size caps are preserved. Raw names remain internal to comparisons and API lookups. Display-normalized refs can differ from their exact Git spelling. These transformations and the catalog description help identify and display the boundary. They cannot prevent a consuming model from following instructions written in metadata.

The inventory samples up to 32 local or live refs per source. Pull requests, workflows, runs and statuses use bounded pages. At most three failed runs receive job lookups. Recent commit subject excerpts are capped at 112 characters. The acquisition deadline is 24 seconds, each command deadline is 4 seconds, each subprocess stdout buffer is capped at 512 KiB, and the report JSON is capped at 96 KiB. Independent source reads share a time window and may reflect concurrent edits. Local Git status is unavailable when inspection would require a submodule worktree or a configured clean filter. GitHub access failures leave relevant fields unavailable and preserve available local results.

`DENIED` rejects unknown projects before any subprocess. `INVALID_ARGUMENTS` rejects path, repository and other undeclared inputs. CLI exit `0` means a report was generated, and exit `2` means the request was rejected or a report could not be generated. On MCP, JSON text and structured output carry the same payload. Report telemetry measures operation latency and process launch attempts. Underlying HTTP retries, provider tokens and billing are unavailable through this entry point.

The operation uses optional locks disabled, local Git reads and authenticated GitHub `GET` calls. It checks the checkout origin and the remote repository’s numeric ID before dependent collection. Successful output includes no dirty-file paths or contents, arbitrary workflow logs, or credential values. A local client and its inherited executable paths are part of the trusted runtime.

## Tests and packaging

Run `python -B -W error -m unittest discover -s tests -v` from this directory under Python 3.10 and 3.14. The suite uses synthetic boundaries. GitHub Actions runs the same discovery command on Windows for pushes to `main` with repository contents read permission. The tests require no private checkout, model account or application credential.

From the Git checkout root, run `py -3.10 -B .\work\wpai-exec\build_package.py --output .\outputs\wpai-exec-stage-1.1.zip`. The builder stores sorted members with fixed timestamps and modes and prints the ZIP SHA-256. Extract the package and check member bytes against `MANIFEST.sha256` before running the CLI, stdio server or tests. The archived Stage 1 package remains the evidence for version 0.1.0.

## Far-future compatibility work

The Human Director accepted deferring the Claude Code model test on November 26, 2026. When an eligible subscription and approval are available, run the unchanged Stage 0B fixture `wpai.probe.v1` with server SHA-256 `d0e4a3e01218720002ebbf5d668972634c9f5726f8dec04f353eae4023357770`. Record model-issued invocation, echo, validation, both evidence pages, server denial, result reception and graceful shutdown. Keep the Stage 0C finding open until that evidence exists.
