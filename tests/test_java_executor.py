import base64
import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from backend.java_executor import (
    CORE_NAME,
    CoreNameJob,
    DockerCoreNameCoordinator,
    ProtocolError,
    core_name_cases,
    encode_frame,
    evaluate_core_name,
    read_frame,
    sign_trusted_result,
    validate_observation,
    verify_trusted_result,
)


def _observation(job, request_id, case, *, invalid=True, reason="INVALID_NAME"):
    if invalid:
        payload = {"exception_type": "RegistrationException", "reason": reason}
        kind = "exception"
    else:
        payload = {"value": {"sequence": 1}}
        kind = "return"
    return {"protocol": 1, "job_id": job.job_id, "nonce": job.nonce,
            "request_id": request_id, "case": case, "command": "observation",
            "kind": kind, "payload": payload}


def _all_observations(job):
    result = []
    for index, case in enumerate(core_name_cases()):
        invalid = case["student_name"] is None or case["student_name"] == "" or str(case["student_name"]).isspace()
        result.append(_observation(job, f"r-{index}", CORE_NAME, invalid=invalid))
    return result


def test_length_prefixed_protocol_round_trip_and_limit():
    message = {"protocol": 1, "job_id": "j", "payload": "中文"}
    frame = encode_frame(message)
    assert struct.unpack(">I", frame[:4])[0] == len(frame) - 4
    import io
    assert read_frame(io.BytesIO(frame)) == message
    with pytest.raises(ProtocolError):
        encode_frame({"payload": "x" * 70000})


def test_core_name_checker_recomputes_result_and_preserves_existing_weight():
    job = CoreNameJob(job_id="job-1", nonce="nonce-1", hmac_key=b"k" * 32)
    result = evaluate_core_name(_all_observations(job), job_id=job.job_id,
                                nonce=job.nonce, key=job.hmac_key)
    verified = verify_trusted_result(result, job.hmac_key, job_id=job.job_id,
                                     nonce=job.nonce)
    assert verified["checks"] == [verified["checks"][0]]
    assert verified["checks"][0]["key"] == CORE_NAME
    assert verified["checks"][0]["weight"] == 5
    assert verified["checks"][0]["passed"] is True


def test_student_cannot_submit_passed_or_score_or_replay_request():
    job = CoreNameJob(job_id="job-2", nonce="nonce-2", hmac_key=b"k" * 32)
    forged = _observation(job, "r-1", CORE_NAME)
    forged["passed"] = True
    with pytest.raises(ProtocolError):
        validate_observation(forged, job_id=job.job_id, nonce=job.nonce, request_id="r-1")
    observations = _all_observations(job)
    observations[-1]["request_id"] = observations[0]["request_id"]
    with pytest.raises(ProtocolError):
        evaluate_core_name(observations, job_id=job.job_id, nonce=job.nonce, key=job.hmac_key)


def test_wrong_job_nonce_and_mac_are_rejected():
    job = CoreNameJob(job_id="job-3", nonce="nonce-3", hmac_key=b"k" * 32)
    result = sign_trusted_result({"protocol": 1, "job_id": job.job_id, "nonce": job.nonce,
                                  "case": CORE_NAME, "command": "trusted_result",
                                  "checks": [{"key": CORE_NAME, "passed": True, "weight": 5, "dimension": "core"}]}, job.hmac_key)
    with pytest.raises(ProtocolError):
        verify_trusted_result(result, job.hmac_key, job_id="other", nonce=job.nonce)
    result["checks"][0]["passed"] = False
    with pytest.raises(ProtocolError):
        verify_trusted_result(result, job.hmac_key, job_id=job.job_id, nonce=job.nonce)


def test_docker_command_has_no_socket_and_uses_fixed_security_flags(tmp_path):
    submission = tmp_path / "submission"
    submission.mkdir()
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    coordinator = DockerCoreNameCoordinator()
    job = CoreNameJob(job_id="job-4", nonce="nonce-4", hmac_key=b"k" * 32)
    student = coordinator.build_student_command(submission, adapter, job)
    checker = coordinator.build_checker_command(job)
    joined = " ".join(student + checker)
    assert "docker.sock" not in joined
    assert "--network none" in joined
    assert "--cap-drop ALL" in joined
    assert "--read-only" in joined
    assert "/submission" in joined
    assert "CHECKER_HMAC_KEY_B64=" not in joined


def test_java_core_name_contract(tmp_path):
    """Compile and run the fixed contract against the trusted base implementation."""
    javac = shutil.which("javac")
    java = shutil.which("java")
    if not javac or not java:
        pytest.skip("JDK unavailable")
    root = Path(__file__).resolve().parents[1]
    starter = root / "training/java-practice/starter/src"
    base = root / "training/java-practice/checks/base/competition/RegistrationService.java"
    test = root / "training/java-practice/runner/CoreNameContractTest.java"
    out = Path(tmp_path) / "classes"
    out.mkdir(parents=True, exist_ok=True)
    sources = [str(p) for p in starter.rglob("*.java") if p.name != "RegistrationService.java"] + [str(base), str(test)]
    compiled = subprocess.run([javac, "-encoding", "UTF-8", "-proc:none", "-d", str(out), *sources], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    executed = subprocess.run([java, "-cp", str(out), "CoreNameContractTest"], capture_output=True, text=True, timeout=10)
    assert executed.returncode == 0, executed.stderr
