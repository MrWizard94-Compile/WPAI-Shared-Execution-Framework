from __future__ import annotations

import json
import os
import re
import secrets
import sys
import time

NAME = "wpai-stage-0b-probe"
BUILD = "0.1.1"
CONTRACT = "wpai.probe.v1"
MODERN = "2026-07-28"
LEGACY = ("2025-11-25", "2025-06-18")
SUPPORTED = (MODERN, *LEGACY)
META = "io.modelcontextprotocol/"
MAX_LINE = 8192
MAX_MESSAGES = 128
CURSOR_TTL = 20.0
ROWS = ("alder", "birch", "cedar", "dogwood")
INFO = {"name": NAME, "version": BUILD}
CAPABILITIES = {"tools": {"listChanged": False}}
STR = {"type": "string"}
BOOL = {"type": "boolean"}
COUNT = {"type": "integer", "minimum": 0, "maximum": 9}
LABEL = {"type": "string", "minLength": 1, "maxLength": 32, "pattern": "^[A-Za-z0-9 _-]+$"}


def shape(properties, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


VALUE = shape({"label": LABEL, "count": COUNT, "enabled": BOOL}, ("label", "count", "enabled"))
ECHO = shape({"value": VALUE}, ("value",))
EMPTY = shape({})
TOOLS = {
    "probe_info": (
        "Return the synthetic probe identity, build and operation contract.",
        EMPTY,
        shape(
            {"server": STR, "build": STR, "contract": STR, "protocol": STR,
             "supported": {"type": "array", "items": STR}},
            ("server", "build", "contract", "protocol", "supported"),
        ),
    ),
    "probe_echo": ("Echo a validated synthetic object.", ECHO, ECHO),
    "probe_validation": (
        "Validate a synthetic integer from 0 to 9.",
        shape({"count": COUNT}, ("count",)),
        shape({"valid": BOOL, "count": COUNT}, ("valid", "count")),
    ),
    "probe_evidence_page": (
        f"Return two synthetic rows. Pass the opaque cursor for page 2 within {CURSOR_TTL:g} seconds.",
        shape({"cursor": {"type": "string", "maxLength": 40}}),
        shape(
            {"page": {"type": "integer"}, "rows": {"type": "array", "items": STR},
             "nextCursor": {"type": ["string", "null"]}},
            ("page", "rows", "nextCursor"),
        ),
    ),
    "probe_denied_operation": ("Attempt a deliberately unauthorized synthetic operation.", EMPTY, None),
}


class InputError(Exception):
    pass


class RpcError(Exception):
    def __init__(self, code, message, data=None):
        self.error = {"code": code, "message": message}
        if data is not None:
            self.error["data"] = data


def validate_object(value, schema):
    if not isinstance(value, dict):
        raise InputError("Expected an object")
    if value.keys() - schema["properties"].keys():
        raise InputError("Unexpected property")
    if set(schema["required"]) - value.keys():
        raise InputError("Required property missing")
    for key, item in value.items():
        rule = schema["properties"][key]
        match rule["type"]:
            case "object":
                validate_object(item, rule)
            case "string":
                if not isinstance(item, str):
                    raise InputError("Expected a string")
                if not rule.get("minLength", 0) <= len(item) <= rule["maxLength"]:
                    raise InputError("String length out of range")
                if "pattern" in rule and re.fullmatch(rule["pattern"], item) is None:
                    raise InputError("Unexpected characters")
            case "integer":
                if type(item) is not int:
                    raise InputError("Expected an integer")
                if not rule["minimum"] <= item <= rule["maximum"]:
                    raise InputError("Integer out of range")
            case "boolean":
                if type(item) is not bool:
                    raise InputError("Expected a boolean")


def compact(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def trace(event, **fields):
    print(compact({"event": event, **fields}), file=sys.stderr, flush=True)


def result_payload(value, *, error=False):
    result = {"content": [{"type": "text", "text": compact(value)}], "isError": error}
    if not error:
        result["structuredContent"] = value
    return result


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def reject_constant(_):
    raise ValueError("invalid constant")


class Probe:
    def __init__(self):
        self.legacy = None
        self.legacy_ready = False
        self.cursors = {}

    def handle(self, method, params, notification):
        meta = params.get("_meta", {})
        if not isinstance(meta, dict):
            raise RpcError(-32602, "Invalid metadata")
        requested = meta.get(META + "protocolVersion")
        if notification:
            if method == "notifications/initialized" and self.legacy:
                self.legacy_ready = True
                trace("initialized", protocol=self.legacy)
            return None
        if method == "initialize" and requested is None:
            if self.legacy is not None:
                raise RpcError(-32600, "Already initialized")
            offered = params.get("protocolVersion")
            if not isinstance(offered, str) or not isinstance(params.get("capabilities"), dict):
                raise RpcError(-32602, "Invalid initialization")
            self.legacy = offered if offered in LEGACY else LEGACY[0]
            trace("negotiate", protocol=self.legacy, offered=offered if offered in SUPPORTED else "other",
                  mechanism="initialize")
            return {"protocolVersion": self.legacy, "serverInfo": INFO, "capabilities": CAPABILITIES}
        if requested is not None or method == "server/discover":
            if requested != MODERN:
                if not isinstance(requested, str):
                    raise RpcError(-32602, "Missing protocol metadata")
                raise RpcError(-32022, "Unsupported protocol version",
                               {"requested": requested, "supported": list(SUPPORTED)})
            if not isinstance(meta.get(META + "clientCapabilities"), dict):
                raise RpcError(-32602, "Missing client capability metadata")
            return {"resultType": "complete", **self.lookup(method, params, MODERN)}
        if self.legacy is None or (not self.legacy_ready and method != "ping"):
            raise RpcError(-32002, "MCP initialization required")
        return self.lookup(method, params, self.legacy)

    def lookup(self, method, params, protocol):
        if method == "server/discover" and protocol == MODERN:
            trace("negotiate", protocol=protocol, mechanism="server/discover")
            return {
                "supportedVersions": list(SUPPORTED),
                "capabilities": CAPABILITIES,
                "_meta": {META + "serverInfo": INFO},
                "ttlMs": 0,
                "cacheScope": "private",
            }
        if method == "ping" and protocol in LEGACY:
            trace("ping", protocol=protocol)
            return {}
        if method == "tools/list":
            if params.get("cursor") is not None:
                raise RpcError(-32602, "Invalid tool catalog cursor")
            catalog = []
            for name, (description, input_schema, output_schema) in sorted(TOOLS.items()):
                tool = {"name": name, "description": description, "inputSchema": input_schema}
                if output_schema is not None:
                    tool["outputSchema"] = output_schema
                catalog.append(tool)
            trace("catalog", protocol=protocol, tools=len(catalog))
            cache = {"ttlMs": 0, "cacheScope": "private"} if protocol == MODERN else {}
            return {"tools": catalog, **cache}
        if method == "tools/call":
            return self.call(params.get("name"), params.get("arguments", {}), protocol)
        raise RpcError(-32601, "Method not supported")

    def call(self, name, arguments, protocol):
        if not isinstance(name, str) or name not in TOOLS:
            raise RpcError(-32602, "Unknown tool")
        if name == "probe_denied_operation":
            trace("call", protocol=protocol, tool=name, outcome="DENIED", protectedActions=0)
            return result_payload({"code": "DENIED", "protectedActions": 0}, error=True)
        try:
            validate_object(arguments, TOOLS[name][1])
        except InputError as exc:
            trace("call", protocol=protocol, tool=name, outcome="INVALID_INPUT")
            return result_payload({"code": "INVALID_INPUT", "reason": str(exc)}, error=True)
        if name == "probe_info":
            value = {"server": NAME, "build": BUILD, "contract": CONTRACT,
                     "protocol": protocol, "supported": list(SUPPORTED)}
        elif name == "probe_echo":
            value = {"value": arguments["value"]}
        elif name == "probe_validation":
            value = {"valid": True, "count": arguments["count"]}
        else:
            cursor = arguments.get("cursor")
            now = time.monotonic()
            self.cursors = {key: end for key, end in self.cursors.items() if end > now}
            if cursor is not None:
                if cursor not in self.cursors:
                    trace("call", protocol=protocol, tool=name, outcome="CURSOR_EXPIRED_OR_UNKNOWN")
                    return result_payload({"code": "CURSOR_EXPIRED_OR_UNKNOWN"}, error=True)
                value = {"page": 2, "rows": ROWS[2:], "nextCursor": None}
            else:
                if len(self.cursors) >= 16:
                    self.cursors.pop(next(iter(self.cursors)))
                token = secrets.token_urlsafe(16)
                self.cursors[token] = now + CURSOR_TTL
                value = {"page": 1, "rows": ROWS[:2], "nextCursor": token}
        trace("call", protocol=protocol, tool=name, outcome="OK")
        return result_payload(value)

    def message(self, raw):
        try:
            message = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_keys,
                                 parse_constant=reject_constant)
        except (UnicodeError, ValueError, RecursionError):
            return {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "Invalid JSON"}}
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32600, "message": "Invalid request"}}
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params", {})
        notification = "id" not in message
        if not notification and (type(request_id) not in (str, int) or
                                 (isinstance(request_id, str) and len(request_id) > 128)):
            return {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32600, "message": "Invalid request ID"}}
        frame = {"jsonrpc": "2.0", "id": request_id}
        try:
            if not isinstance(method, str) or not isinstance(params, dict):
                raise RpcError(-32600, "Invalid request envelope")
            value = self.handle(method, params, notification)
            if not notification:
                return {**frame, "result": value}
        except RpcError as exc:
            if not notification:
                return {**frame, "error": exc.error}
        return None


def main():
    session = Probe()
    trace("start", pid=os.getpid(), build=BUILD)
    for _ in range(MAX_MESSAGES):
        raw = sys.stdin.buffer.readline(MAX_LINE + 1)
        if not raw:
            trace("stop", reason="eof")
            return 0
        if len(raw) > MAX_LINE or not raw.endswith(b"\n"):
            trace("stop", reason="frame_limit")
            return 2
        response = session.message(raw)
        if response is not None:
            try:
                sys.stdout.buffer.write((compact(response) + "\n").encode("ascii"))
                sys.stdout.buffer.flush()
            except BrokenPipeError:
                trace("stop", reason="closed_peer")
                return 0
    trace("stop", reason="message_limit")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
