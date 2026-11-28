"""Executable Stage 1.8 journal schema and independent terminal validator."""

from boundary import (ACTORS, CASES, CONTROLLER_MASKS, INJECTED_EXIT, JOBS, MEMBERSHIP, OBSERVE_PROCESS,
                      RECOVERED_EXIT, RECOVERY_MS, WITNESS_MASKS)
from contract import REQUEST, observation, require
from witness import Contract as Stage16Contract, Ledger, READERS, REQUEST_HOPS, RESPONSE_HOPS, rows, token


SCHEMA = "wpai.benchmark.independent-controller-witness.v1"
PIPE_ROLES = tuple(name for name in READERS if name != "owner_control")
TERMINAL_STATUS = lambda value: type(value) is int and value in (0, 38, 109)
VALID_EXIT = lambda value: type(value) is int and 0 <= value <= 0xffffffff


def expected_roles(case):
    return ("controller",) if case == "before_launch" else ("controller", *ACTORS)


def totals(case):
    return {"subject": 0, "fixture": 0, "guard": 1} if case == "before_launch" else {
        "subject": 2, "fixture": 1, "guard": 5}


def job_roles(scope):
    return sorted(role for role in MEMBERSHIP if scope in MEMBERSHIP[role])


def actor_trace(events, roles):
    """Apply the frozen Stage 1.6 transaction rules to the actual forwarded trace."""
    legacy = Stage16Contract(events)
    legacy.roles = roles
    return legacy


class Evidence:
    def __init__(self, events):
        self.events = events
        self.index = 0
        self.identities = {}
        self.creations = set()
        self.exit_codes = {}
        self.accounting = {}
        self.trace = []

    def next_kind(self):
        return self.events[self.index][0]["event"] if self.index < len(self.events) else None

    def expect(self, event, actor="witness", **fields):
        if self.index == len(self.events):
            raise EOFError("Missing required stage event")
        row, ns = self.events[self.index]
        require(row.keys() == {"event", "actor", *fields} and row["event"] == event and row["actor"] == actor,
                f"Expected {event} from {actor} at record {self.index + 1}")
        for key, expected in fields.items():
            value = row[key]
            match = expected(value) if callable(expected) else type(value) is type(expected) and value == expected
            require(match, f"Invalid {event}.{key}")
        self.index += 1
        return row, ns

    def register(self, role):
        row, _ = self.expect("registered", role=role, jobs=list(MEMBERSHIP[role]), process=token, creation=token,
                             source="retained_handle")
        require(row["process"] not in self.identities.values() and row["creation"] not in self.creations,
                "Reused process or creation identity")
        self.identities[role] = row["process"]
        self.creations.add(row["creation"])

    def job(self, scope, phase, members, total):
        self.expect("job", scope=scope, phase=phase, members=members, active=len(members), total=total,
                    source="QueryInformationJobObject")
        self.accounting[f"{scope}_{phase}"] = {"members": members, "active": len(members), "total": total}

    def active(self, phase, role):
        self.expect("active", phase=phase, role=role, process=self.identities[role],
                    source="WaitForSingleObject+IsProcessInJob")

    def terminal_pipe(self):
        row, _ = self.expect("controller_pipe_terminal", status=TERMINAL_STATUS, source="ReadFile", bytes=0)
        return row["status"]

    def exit(self, role, code):
        self.expect("signaled", role=role, process=self.identities[role], source="WaitForSingleObject")
        row, _ = self.expect("exit", role=role, process=self.identities[role], code=code, source="GetExitCodeProcess")
        self.exit_codes[role] = row["code"]

    def transaction_records(self):
        while self.next_kind() == "actor_trace":
            row, ns = self.expect("actor_trace", actor="controller", observation=lambda item: type(item) is dict)
            self.trace.append((row["observation"], ns))
        return actor_trace(self.trace, self.identities)

    def boot(self, case):
        self.expect("start", schema=SCHEMA, case=case)
        self.register("witness")
        self.register("controller")
        self.expect("witness_rights", jobs=WITNESS_MASKS, retained_controller=OBSERVE_PROCESS, source="NtQueryObject")
        for scope in JOBS:
            self.job(scope, "before_release", ["controller"] if scope == "guard" else [], int(scope == "guard"))
        self.expect("witness_ready")
        self.expect("protected_storage", actor="controller", canary_write_denied=True, journal_write_denied=True,
                    jobs=CONTROLLER_MASKS)
        if case != "before_launch":
            self.register("owner")
            self.register("server")
            self.job("fixture", "startup", ["server"], 1)
            self.expect("fixture_gate", released=case != "in_flight")
            if case != "in_flight":
                self.expect("fixture_ready", actor="controller")
            self.register("root")
            self.register("relay")
            self.job("subject", "startup", ["relay", "root"], 2)
            self.expect("subject_gate")
            self.expect("actors_ready", actor="controller")

    def checkpoint(self, case):
        roles = expected_roles(case)
        for role in roles:
            self.active("checkpoint", role)
        for scope in JOBS:
            members = sorted(role for role in roles if scope in MEMBERSHIP[role])
            self.job(scope, "checkpoint", members, totals(case)[scope])
        self.expect("checkpoint", case=case, fixture_gate_held=case == "in_flight")

    def finish(self, case, disposition):
        self.active("final", "witness")
        self.expect("terminal", outcome=disposition, case=case, process=self.identities["witness"])
        require(self.index == len(self.events), "Events after the unique terminal record")

    def normal(self):
        trace = self.transaction_records()
        trace.frames()
        trace.graceful_fixture("normal")
        require(trace.index == len(trace.events), "Unexpected normal actor observation")
        self.expect("controller_finished", actor="controller")
        pipe = self.terminal_pipe()
        self.exit("controller", 0)
        for scope in JOBS:
            self.job(scope, "final", [], totals("normal")[scope])
        self.finish("normal", "observed_success")
        return {"outcome": "observed_success", "controller_lost": False, "fixture_eof": "observed",
                "unavailable": [], "wire": trace.wire, "actor_terminal_ReadFile": trace.reads,
                "controller_ReadFile": pipe, "exit_codes": {**trace.codes, **self.exit_codes},
                "final_job_accounting": self.final_jobs(), "recovery_elapsed_ns": None}

    def final_jobs(self):
        return {scope: self.accounting[f"{scope}_final"] for scope in JOBS}

    def fault(self, case):
        trace = self.transaction_records()
        if case == "in_flight":
            for boundary in REQUEST_HOPS[:3]:
                trace.expect("wire", boundary=boundary, **observation(REQUEST))
            trace.wire["request"] = observation(REQUEST)
        elif case == "response_verified":
            trace.frames()
        require(trace.index == len(trace.events), "Fault checkpoint has unexpected actor observations")
        self.checkpoint(case)
        pipe = self.terminal_pipe()
        self.exit("controller", INJECTED_EXIT)
        self.expect("controller_lost", basis="terminal_ReadFile_and_retained_exit")
        self.active("after_controller_loss", "witness")
        row, begin = self.expect("recovery_started", target="guard", budget_ms=RECOVERY_MS,
                                 start_ns=lambda value: type(value) is int and value >= 0)
        require(row["start_ns"] <= begin, "Recovery start clock is inconsistent")
        self.expect("recovery_force", target="guard", requested_exit=RECOVERED_EXIT, source="TerminateJobObject")
        for role in expected_roles(case)[1:]:
            self.exit(role, VALID_EXIT)
        for scope in JOBS:
            self.job(scope, "final", [], totals(case)[scope])
        row_end, end = self.expect("recovery_settled", elapsed_ns=lambda value: type(value) is int and value >= 0)
        require(row_end["elapsed_ns"] <= end - row["start_ns"] <= RECOVERY_MS * 1_000_000,
                "Recovery did not settle within its proved deadline")
        for channel in PIPE_ROLES:
            reason = "actors_not_started" if case == "before_launch" else "controller_lost"
            self.expect("observation_unavailable", channel=channel, reason=reason)
        self.finish(case, "incomplete")
        return {"outcome": "incomplete", "controller_lost": True, "fixture_eof": "unavailable",
                "unavailable": list(PIPE_ROLES), "wire": trace.wire,
                "checkpoint": case, "fixture_gate_held": case == "in_flight",
                "request_hops_before_loss": len(REQUEST_HOPS) if case == "response_verified" else
                (3 if case == "in_flight" else 0),
                "actor_terminal_ReadFile": {}, "controller_ReadFile": pipe, "exit_codes": self.exit_codes,
                "final_job_accounting": self.final_jobs(), "recovery_elapsed_ns": row_end["elapsed_ns"]}


def validate_unavailable(events, case):
    require(len(events) >= 3, "Unavailable journal is missing recovery evidence")
    prefix = Evidence(events[:-2])
    try:
        prefix.boot(case)
        prefix.normal() if case == "normal" else prefix.fault(case)
    except EOFError:
        pass  # A structurally valid prefix ended before the expected terminal proof.
    else:
        raise ValueError("A finalized scenario cannot be followed by emergency recovery")
    proof = Evidence(events[-2:])
    row, _ = proof.expect(
        "emergency", reason=lambda item: item in ("controller_pipe_closed", "bounded_deadline", "invalid_or_unsettled"),
        settled=lambda item: type(item) is bool, elapsed_ns=lambda item: type(item) is int and item >= 0,
        controller_terminal=lambda item: item is None or TERMINAL_STATUS(item),
        exits=lambda item: type(item) is dict, jobs=lambda item: item is None or type(item) is dict,
    )
    require(row["exits"].keys() <= set(prefix.identities) - {"witness"}
            and all(VALID_EXIT(code) for code in row["exits"].values()), "Invalid emergency exit observation")
    if row["reason"] == "controller_pipe_closed":
        require(TERMINAL_STATUS(row["controller_terminal"]), "Missing emergency controller pipe observation")
    if row["settled"]:
        require(row["jobs"] is not None and set(row["jobs"]) == set(JOBS)
                and row["elapsed_ns"] <= RECOVERY_MS * 1_000_000,
                "Unproved or unbounded emergency cleanup")
        for scope, item in row["jobs"].items():
            require(item.keys() == {"active", "members", "total"} and type(item["active"]) is int and item["active"] == 0
                    and item["members"] == [] and type(item["total"]) is int and 0 <= item["total"] <= totals("normal")[scope],
                    "Emergency job accounting differs")
    else:
        require(row["jobs"] is None, "An unsettled emergency cannot contain final job accounting")
    proof.expect("terminal", case=case, outcome="unavailable", reason="unscripted_loss_or_unsettled",
                 process=prefix.identities["witness"])
    return {"valid": True, "case": case, "outcome": "unavailable", "witness_finalized": True,
            "bounded_recovery": row["settled"], "exit_codes": row["exits"], "final_job_accounting": row["jobs"],
            "controller_ReadFile": row["controller_terminal"], "fixture_eof": "unavailable"}


def validate(data):
    """A malformed, truncated, or unproven journal can never validate as a success."""
    try:
        events, truncated = rows(data)
        if truncated or not events:
            return {"valid": False, "outcome": "incomplete", "reason": "truncated_or_empty"}
        case = events[0][0].get("case")
        require(case in CASES, "Unknown witness scenario")
        if events[-1][0].get("outcome") == "unavailable":
            require(sum(row.get("event") == "terminal" for row, _ in events) == 1, "Duplicate terminal event")
            return validate_unavailable(events, case)
        check = Evidence(events)
        check.boot(case)
        result = check.normal() if case == "normal" else check.fault(case)
        return {"valid": True, "case": case, "witness_finalized": True, **result}
    except EOFError:
        return {"valid": False, "outcome": "incomplete", "reason": "missing_event"}
    except (ValueError, KeyError, TypeError, RecursionError, AttributeError, TimeoutError) as error:
        return {"valid": False, "outcome": "invalid", "reason": str(error)}
