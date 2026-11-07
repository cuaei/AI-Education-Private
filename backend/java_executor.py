"""Isolated CORE-NAME execution primitives.

This module is deliberately separate from ``java_course.run_check``.  The
legacy harness remains the default path until the new containers have passed
real Docker integration tests.  Student observations are always treated as
untrusted; only the checker container creates objective check results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import select
import struct
import subprocess
import threading
import time
from typing import BinaryIO, Iterable


PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 64 * 1024
MAX_MESSAGES = 64
CORE_NAME = "CORE-NAME"
STUDENT_IMAGE = "course-platform-java-core-name-student:2026.11.6"
CHECKER_IMAGE = "course-platform-java-core-name-checker:2026.11.6"
FORBIDDEN_STUDENT_FIELDS = frozenset(
    {"passed", "score", "actual", "necessary", "attempts_used", "grade", "checks"}
)


class ProtocolError(ValueError):
    """Malformed, oversized, replayed, or unauthorised protocol data."""


class EnvironmentFailure(RuntimeError):
    """The execution environment failed; this must not consume an attempt."""


def encode_frame(message: dict) -> bytes:
    if not isinstance(message, dict):
        raise ProtocolError("message must be an object")
    try:
        body = json.dumps(message, ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("message is not JSON encodable") from exc
    if len(body) > MAX_FRAME_BYTES:
        raise ProtocolError("message exceeds 64 KiB")
    return struct.pack(">I", len(body)) + body


def _read_exact(stream: BinaryIO, size: int, timeout: float | None = None) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        if timeout is not None:
            ready, _, _ = select.select([stream], [], [], max(0.0, timeout))
            if not ready:
                raise TimeoutError("frame read timed out")
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError("unexpected EOF")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(stream: BinaryIO, timeout: float | None = None) -> dict:
    header = _read_exact(stream, 4, timeout)
    length = struct.unpack(">I", header)[0]
    if length == 0 or length > MAX_FRAME_BYTES:
        raise ProtocolError("invalid frame length")
    try:
        message = json.loads(_read_exact(stream, length, timeout).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("invalid JSON frame") from exc
    if not isinstance(message, dict):
        raise ProtocolError("frame must contain a JSON object")
    return message


def validate_envelope(message: dict, *, job_id: str, nonce: str,
                      case: str = CORE_NAME, request_id: str | None = None) -> dict:
    if message.get("protocol") != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    if message.get("job_id") != job_id or message.get("nonce") != nonce:
        raise ProtocolError("job_id or nonce mismatch")
    if message.get("case") != case:
        raise ProtocolError("case is not allowed for this job")
    if request_id is not None and message.get("request_id") != request_id:
        raise ProtocolError("request_id mismatch")
    return message


def validate_observation(message: dict, *, job_id: str, nonce: str,
                         request_id: str) -> dict:
    validate_envelope(message, job_id=job_id, nonce=nonce, request_id=request_id)
    if message.get("command") != "observation":
        raise ProtocolError("expected observation")
    if FORBIDDEN_STUDENT_FIELDS.intersection(message):
        raise ProtocolError("student cannot submit scoring fields")
    kind = message.get("kind")
    if kind not in {"exception", "return", "process_error"}:
        raise ProtocolError("invalid observation kind")
    if not isinstance(message.get("payload", {}), dict):
        raise ProtocolError("observation payload must be an object")
    return message


def _hmac_payload(message: dict) -> bytes:
    unsigned = dict(message)
    unsigned.pop("mac", None)
    return json.dumps(unsigned, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sign_trusted_result(message: dict, key: bytes) -> dict:
    if not key:
        raise ValueError("HMAC key must not be empty")
    result = dict(message)
    result["mac"] = base64.b64encode(hmac.new(key, _hmac_payload(result), hashlib.sha256).digest()).decode("ascii")
    return result


def verify_trusted_result(message: dict, key: bytes, *, job_id: str,
                          nonce: str, case: str = CORE_NAME) -> dict:
    validate_envelope(message, job_id=job_id, nonce=nonce, case=case)
    mac = message.get("mac")
    if not isinstance(mac, str):
        raise ProtocolError("trusted result has no MAC")
    try:
        supplied = base64.b64decode(mac.encode("ascii"), validate=True)
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError("invalid result MAC") from exc
    expected = hmac.new(key, _hmac_payload(message), hashlib.sha256).digest()
    if not hmac.compare_digest(supplied, expected):
        raise ProtocolError("trusted result MAC mismatch")
    if message.get("command") != "trusted_result":
        raise ProtocolError("invalid trusted result command")
    checks = message.get("checks")
    if not isinstance(checks, list) or len(checks) != 1:
        raise ProtocolError("unexpected checker result count")
    check = checks[0]
    if not isinstance(check, dict) or set(check) - {"key", "label", "passed", "weight", "dimension", "expected", "actual"}:
        raise ProtocolError("invalid checker result fields")
    if check.get("key") != CORE_NAME or check.get("weight") != 5 or check.get("dimension") != "core":
        raise ProtocolError("checker result does not match CORE-NAME")
    if not isinstance(check.get("passed"), bool):
        raise ProtocolError("checker passed must be boolean")
    return message


def core_name_cases() -> list[dict]:
    """Inputs are generated by the trusted coordinator, not by the student."""
    return [
        {"label": "null", "student_name": None},
        {"label": "empty", "student_name": ""},
        {"label": "space", "student_name": " "},
        {"label": "many-spaces", "student_name": "   "},
        {"label": "tab-newline", "student_name": "\t\n"},
        {"label": "unicode-space", "student_name": "\u2003\u2003"},
        {"label": "valid", "student_name": "陳同學"},
        {"label": "literal-null", "student_name": "null"},
    ]


def evaluate_core_name(observations: Iterable[dict], *, job_id: str, nonce: str,
                       key: bytes) -> dict:
    observations = list(observations)
    if len(observations) > MAX_MESSAGES:
        raise ProtocolError("message count exceeds per-job limit")
    if len(observations) != len(core_name_cases()):
        raise ProtocolError("incomplete CORE-NAME observation set")
    request_ids: set[str] = set()
    results = []
    for case, observation in zip(core_name_cases(), observations):
        request_id = observation.get("request_id")
        if not isinstance(request_id, str) or request_id in request_ids:
            raise ProtocolError("duplicate or missing request_id")
        request_ids.add(request_id)
        validate_observation(observation, job_id=job_id, nonce=nonce, request_id=request_id)
        expected_invalid = case["student_name"] is None or str(case["student_name"]).isspace() or case["student_name"] == ""
        if observation.get("kind") == "exception":
            payload = observation.get("payload", {})
            observed_type = payload.get("exception_type")
            observed_reason = payload.get("reason")
            passed = expected_invalid and observed_type == "RegistrationException" and observed_reason == "INVALID_NAME"
            actual = {"kind": "exception", "exception_type": observed_type, "reason": observed_reason}
        elif observation.get("kind") == "return":
            passed = not expected_invalid
            actual = {"kind": "return", "value": observation.get("payload", {}).get("value")}
        else:
            passed = False
            actual = {"kind": "process_error", "error": observation.get("payload", {}).get("error")}
        results.append({"key": CORE_NAME, "label": f"CORE-NAME/{case['label']}",
                        "dimension": "core", "weight": 5 if case["label"] == "null" else 0,
                        "passed": passed, "expected": "INVALID_NAME" if expected_invalid else "正常姓名可注册",
                        "actual": actual})
    # The existing score has one CORE-NAME item worth five points.  The
    # additional vectors strengthen the assertion but do not add points.
    passed = all(item["passed"] for item in results)
    check = {"key": CORE_NAME, "label": "空白姓名必須拒絕並回 INVALID_NAME",
             "dimension": "core", "weight": 5, "passed": passed,
             "expected": "null/空白拒絕，正常姓名接受", "actual": results}
    return sign_trusted_result({"protocol": PROTOCOL_VERSION, "job_id": job_id,
                                "nonce": nonce, "case": CORE_NAME,
                                "command": "trusted_result", "status": "completed",
                                "checks": [check]}, key)


@dataclass
class CoreNameJob:
    job_id: str = field(default_factory=lambda: secrets.token_urlsafe(18))
    nonce: str = field(default_factory=lambda: secrets.token_urlsafe(18))
    hmac_key: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    seen_requests: set[str] = field(default_factory=set, repr=False)


def validate_submission_dir(submission: Path, data_root: Path | None = None) -> Path:
    submission = Path(submission)
    if submission.is_symlink() or not submission.is_dir():
        raise EnvironmentFailure("submission directory is missing or is a symlink")
    resolved = submission.resolve(strict=True)
    if data_root is not None:
        root = Path(data_root).resolve(strict=True)
        if Path(data_root).is_symlink() or not resolved.is_relative_to(root):
            raise EnvironmentFailure("submission directory is outside DATA_DIR")
    return resolved


def _docker_security_flags(*, user: str = "10001:10001") -> list[str]:
    return ["--network", "none", "--read-only", "--init", "--user", user,
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--security-opt", "seccomp=default", "--pids-limit", "128",
            "--cpus", "1", "--memory", "600m", "--memory-swap", "600m",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=128m"]


class DockerCoreNameCoordinator:
    """Docker CLI coordinator for the vertical slice.

    It is intentionally opt-in; ``backend.java_course.run_check`` still uses
    the legacy path until this class has passed real Docker integration tests.
    """

    def __init__(self, *, docker_bin: str = "docker", student_image: str = STUDENT_IMAGE,
                 checker_image: str = CHECKER_IMAGE, timeout: float = 90.0):
        self.docker_bin = docker_bin
        self.student_image = student_image
        self.checker_image = checker_image
        self.timeout = timeout

    def _run(self, args: list[str], *, input_bytes: bytes | None = None,
             timeout: float | None = None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([self.docker_bin, *args], input=input_bytes,
                                  capture_output=True, timeout=timeout or self.timeout,
                                  check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EnvironmentFailure(f"Docker execution failed: {type(exc).__name__}") from exc

    def check_available(self) -> None:
        result = self._run(["version", "--format", "{{.ServerVersion}}"], timeout=10)
        if result.returncode != 0:
            raise EnvironmentFailure("Docker daemon is unavailable")

    def build_student_command(self, submission: Path, adapter: Path, job: CoreNameJob) -> list[str]:
        return [self.docker_bin, "create", "--rm", "-i", "--name", f"java-student-{job.job_id}",
                *_docker_security_flags(), "--mount", f"type=bind,source={submission},target=/submission,readonly",
                "--mount", f"type=bind,source={adapter},target=/adapter,readonly",
                "-e", f"JOB_ID={job.job_id}", "-e", f"JOB_NONCE={job.nonce}",
                self.student_image, "sh", "/adapter/start-core-name.sh"]

    def build_checker_command(self, job: CoreNameJob) -> list[str]:
        return [self.docker_bin, "create", "--rm", "-i", "--name", f"java-checker-{job.job_id}",
                *_docker_security_flags(user="10002:10002"),
                "-e", f"CHECKER_JOB_ID={job.job_id}", "-e", f"CHECKER_NONCE={job.nonce}",
                self.checker_image]

    def run(self, submission: Path, *, data_root: Path | None = None,
            adapter_dir: Path | None = None) -> tuple[str, dict]:
        """Run only when explicitly called; returns existing status vocabulary."""
        submission = validate_submission_dir(submission, data_root)
        self.check_available()
        if adapter_dir is None:
            adapter_dir = Path(__file__).resolve().parents[1] / "training/java-practice/runner"
        adapter_dir = adapter_dir.resolve(strict=True)
        job = CoreNameJob()
        student_cmd = self.build_student_command(submission, adapter_dir, job)
        checker_cmd = self.build_checker_command(job)
        student = checker = None
        drains = []
        student_name = f"java-student-{job.job_id}"
        checker_name = f"java-checker-{job.job_id}"
        try:
            student_created = self._run(student_cmd, timeout=20)
            checker_created = self._run(checker_cmd, timeout=20)
            if student_created.returncode != 0 or checker_created.returncode != 0:
                raise EnvironmentFailure("container creation failed")
            for name in (student_name, checker_name):
                started = self._run(["start", name], timeout=20)
                if started.returncode != 0:
                    raise EnvironmentFailure("container start failed")
            # No -t is supplied: Docker attach keeps stdout and stderr as
            # separate streams and the coordinator is the only relay.
            student = subprocess.Popen([self.docker_bin, "attach", student_name], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            checker = subprocess.Popen([self.docker_bin, "attach", checker_name], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # stderr is untrusted and bounded; draining it prevents a malicious
            # student from blocking the protocol by filling the pipe.
            for process in (student, checker):
                buffer = bytearray()
                def drain(stream=process.stderr, target=buffer):
                    while True:
                        chunk = stream.read(8192)
                        if not chunk:
                            return
                        if len(target) < 1024 * 1024:
                            target.extend(chunk[:1024 * 1024 - len(target)])
                thread = threading.Thread(target=drain, daemon=True)
                thread.start()
                drains.append((thread, buffer))
            observations = []
            deadline = time.monotonic() + self.timeout
            for case in core_name_cases():
                request_id = secrets.token_urlsafe(12)
                job.seen_requests.add(request_id)
                request = {"protocol": PROTOCOL_VERSION, "job_id": job.job_id, "nonce": job.nonce,
                           "request_id": request_id, "case": CORE_NAME, "command": "case_start",
                           "input": {"competition_id": "cup", "student_id": "s01", "student_name": case["student_name"]}}
                student.stdin.write(encode_frame(request)); student.stdin.flush()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("student execution timed out")
                observation = read_frame(student.stdout, timeout=remaining)
                observations.append(validate_observation(observation, job_id=job.job_id,
                                                         nonce=job.nonce, request_id=request_id))
            checker.stdin.write(encode_frame({"protocol": PROTOCOL_VERSION, "job_id": job.job_id,
                                              "nonce": job.nonce, "case": CORE_NAME, "command": "init",
                                              "hmac_key_b64": base64.b64encode(job.hmac_key).decode("ascii")}))
            evaluate = {"protocol": PROTOCOL_VERSION, "job_id": job.job_id, "nonce": job.nonce,
                        "case": CORE_NAME, "command": "evaluate", "observations": observations}
            checker.stdin.write(encode_frame(evaluate)); checker.stdin.flush(); checker.stdin.close()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("checker execution timed out")
            trusted = read_frame(checker.stdout, timeout=remaining)
            verify_trusted_result(trusted, job.hmac_key, job_id=job.job_id, nonce=job.nonce)
            return "completed", {"checks": trusted["checks"], "job_id": job.job_id}
        except (EOFError, OSError, ProtocolError, TimeoutError, subprocess.TimeoutExpired) as exc:
            return "environment_failed", {"message": f"CORE-NAME isolated execution failed: {type(exc).__name__}"}
        finally:
            for process in (student, checker):
                if process is None:
                    continue
                if process.poll() is None:
                    process.kill()
                try:
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            for name in (student_name, checker_name):
                try:
                    self._run(["rm", "-f", name], timeout=10)
                except EnvironmentFailure:
                    pass


def run_core_name_isolated(submission: Path, *, data_root: Path | None = None) -> tuple[str, dict]:
    return DockerCoreNameCoordinator().run(submission, data_root=data_root)
