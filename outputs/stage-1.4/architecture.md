# Architecture decision record

## Decision

Give an observer outside the target Job Object direct custody of the ledger, a job query handle and limited wait/query process handles. Gate each controlled process at startup until the observer assigns it to the job and checks its PID and creation FILETIME against the original creation handle. For a child of the unchanged wrapper, wait for the fixture initialization reply, then query only that target job. Require exactly the known wrapper and one candidate, a live retained candidate handle, consistent membership, a creation time at or after the wrapper, and an unchanged expected total process count. The bounded job inventory rejects additional or replacement processes. This removes any need for administrator privileges, system-wide enumeration or job breakaway. [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) · [Job queries](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject) · [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes)

The external owner is a separate synthetic process with one inheritable duplicate limited to `JOB_OBJECT_TERMINATE`. The target wrapper and server are both in the terminated domain. The observer and owner are outside it. The observer retains its job query handle, waits on wrapper and server handles, and terminates the owner only after obtaining its control acknowledgment. A parent guard in the crash test independently verifies that the observer and its children disappear when the witness itself crashes. External owner inheritance is explicit. The observer ledger is opened exclusively with a noninheritable writer. The target receives no ledger handle or path. [Pipe handle inheritance](https://learn.microsoft.com/en-us/windows/win32/ipc/pipe-handle-inheritance)

## What each observation proves

| Observation | Direct evidence | Scope |
|---|---|---|
| Process signaled | `WaitForSingleObject` on the retained process handle | The process object terminated. |
| Exit code | `GetExitCodeProcess` after the wait returns signaled | The process exit status, including an actual code set by the termination API. |
| Kernel end of pipe | Bounded `ReadFile` after `PeekNamedPipe` checks bytes or peer closure | No writer or further read data on that observed endpoint. Windows can return `ERROR_BROKEN_PIPE` after normal writer closure or process death. |
| Graceful synthetic EOF | Observed writer close, trusted fixture's empty stdin read and output-completion markers, and an actual terminal stdout read | Evidence for the specific synthetic connection. Separate fields retain stdin and stdout evidence. |
| Forced or failed closure | Recorded force request with later kernel peer closure, local reader closure without a read, or a distinct Win32 read failure | The observer can report the actual endpoint result and order. The endpoint result alone cannot establish who closed it. |
| Job empty | Zero active members from `QueryInformationJobObject` | End of the monitored domain. Individually retained handles still supply root and descendant exit status. |
| Observer finalized | Identity and job boundary rechecked and a terminal chained event synced after bounded cleanup | The independent record was completed. A partial record cannot pass. |

[WaitForSingleObject](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject) · [GetExitCodeProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getexitcodeprocess) · [PeekNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-peeknamedpipe) · [ReadFile](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-readfile)

## Alternatives and limits

An observer inside the wrapper's Job Object can lose its ledger before finalization. A PID poll forfeits creation identity and the process exit code once the process object is lost. The independent witness avoids both problems for a controlled job. If a future launcher cannot retain or safely identify a server handle, leave its exit evidence unavailable. A separately launched owner with a capability-scoped local relay is a possible route-specific alternative when the launcher owns all descendant handles. It still needs a verified lifecycle test and a trusted EOF channel.

The prototype uses bounded reads of created anonymous pipes with one reader per endpoint. The control messages come from trusted synthetic actors and do not model an untrusted provider. The chain detects corruption, truncation and unexpected record contents. It does not authenticate a substituted file after closure against another same-user process. The observer is independent of this target Job Object, while a wider external job containing the observer could also terminate it. These boundaries leave native provider qualification open. Stage 1.4 produces its own witness schema and leaves the Stage 1.3.1 v2 receipt and comparison gates separate.
