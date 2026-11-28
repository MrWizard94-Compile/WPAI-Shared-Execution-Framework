"""Start a fresh two-process control boundary, inject a real fault, and validate evidence."""

from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from boundary import (CASES, CONTROLLER_MASKS, INJECTED_EXIT, JOBS, OBSERVE_PROCESS, RUN_SECONDS,
                      WITNESS_MASKS, launch, receive, wait_until, win)
from contract import prepare, require
from journal import validate
from witness import rows


def own(stack, handle):
    stack.callback(handle.close)
    return handle


def pipe(stack):
    return tuple(own(stack, handle) for handle in win.pipe())


def retain(stack, child):
    observed = win.Process(child.pid, expected=win.identity(child.process.value))
    stack.callback(observed.close)
    return observed


def start(case, scratch, stack):
    telemetry, sender = pipe(stack)
    inbox, ack = pipe(stack)
    status, result = pipe(stack)
    with ExitStack() as masters:
        jobs = {name: masters.enter_context(win.Job(limit))
                for name, limit in zip(JOBS, (2, 1, 5), strict=True)}
        controller_grants = [own(stack, win.copy_handle(jobs[name].handle, mask))
                             for name, mask in CONTROLLER_MASKS.items()]
        controller = launch("controller", case, [sender, inbox, *controller_grants], scratch)
        stack.callback(controller.close)
        jobs["guard"].assign(controller.pid)
        win.lower_integrity(controller.process.value)
        for handle in (sender, inbox, *controller_grants):
            handle.close()
        controller_observation = own(stack, win.copy_handle(controller.process.value, OBSERVE_PROCESS))
        witness_grants = [own(stack, win.copy_handle(jobs[name].handle, mask))
                          for name, mask in WITNESS_MASKS.items()]
        witness = launch("independent", case, [controller_observation, telemetry, ack, result, *witness_grants], scratch)
        stack.callback(witness.close)
        for handle in (controller_observation, telemetry, ack, result, *witness_grants):
            handle.close()
    # Every full-access bootstrap job handle has now closed, before either actor can run.
    return controller, witness, win.Reader(status.value)


def run_case(case, *, unexpected_loss=False):
    require(case in CASES and (not unexpected_loss or case == "normal"), "Unknown synthetic fault case")
    with TemporaryDirectory(prefix="wpai-independent-") as fresh, ExitStack() as stack:
        scratch = Path(fresh)
        prepare(scratch / "fixture")
        journal = scratch / "journal"
        journal.mkdir()
        win.protect_scratch(journal)
        (journal / "write-canary").write_bytes(b"Stage 1.8 synthetic write-isolation canary\n")
        path = journal / "witness.jsonl"
        controller, witness, channel = start(case, scratch, stack)
        controller_handle, witness_handle = retain(stack, controller), retain(stack, witness)
        require(controller_handle.identity != witness_handle.identity, "Controller and witness identity are equal")
        end = time.monotonic() + RUN_SECONDS + 8
        witness.start()
        try:
            require(receive(channel, end) == {"kind": "ready"}, "Witness did not establish startup boundary")
            if unexpected_loss:
                controller.kill(INJECTED_EXIT)
                outcome = "unavailable"
            else:
                controller.start()
                outcome = "observed_success" if case == "normal" else "incomplete"
            if case != "normal":
                require(receive(channel, end) == {"kind": "inject", "case": case},
                        "Independent witness did not arm the fault checkpoint")
                require(not controller_handle.signaled() and not witness_handle.signaled(),
                        "Controller or witness exited before the fault")
                controller.kill(INJECTED_EXIT)
            message = receive(channel, end)
            if message != {"kind": "validated", "outcome": outcome}:
                # Surface only fixed event and reason labels while recovering the failed test.
                if path.is_file():
                    history, _ = rows(path.read_bytes())
                    state = [(record.get("event"), record.get("reason")) for record, _ in history[-4:]]
                    raise ValueError(f"{case}: witness returned {message}, last records {state}")
                raise ValueError(f"{case}: witness did not open the journal")
            wait_until(witness_handle.signaled, end)
            require(witness_handle.exit_code() == 0 and controller_handle.signaled(), "Unexpected final process status")
            require(controller_handle.exit_code() == (0 if outcome == "observed_success" else INJECTED_EXIT),
                    "Driver's retained controller code disagrees")
            data = path.read_bytes()
            result = validate(data)
            require(result["valid"] and result["outcome"] == outcome, "Driver rejected the witness journal")
            return data, result
        finally:
            # If the test driver encounters an error, let the witness resolve the owned tree.
            if not controller_handle.signaled():
                controller.kill(INJECTED_EXIT)
            if not witness_handle.signaled():
                wait_until(witness_handle.signaled, end)
