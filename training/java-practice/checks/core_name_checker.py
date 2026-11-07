#!/usr/bin/env python3
"""Trusted CORE-NAME checker container entrypoint.

The checker never imports Java classes and never receives a student source
directory. It re-evaluates observations and signs only its own result.
"""
import base64
import os
import sys

from backend.java_executor import (
    ProtocolError, evaluate_core_name, read_frame, validate_envelope,
)


def main() -> int:
    try:
        init = read_frame(sys.stdin.buffer)
        expected_job = os.environ.get("CHECKER_JOB_ID", "")
        expected_nonce = os.environ.get("CHECKER_NONCE", "")
        validate_envelope(init, job_id=expected_job, nonce=expected_nonce)
        if init.get("command") != "init" or not isinstance(init.get("hmac_key_b64"), str):
            raise ProtocolError("invalid checker init")
        key = base64.b64decode(init["hmac_key_b64"].encode("ascii"), validate=True)
        request = read_frame(sys.stdin.buffer)
        validate_envelope(request, job_id=expected_job, nonce=expected_nonce)
        if request.get("command") != "evaluate" or not isinstance(request.get("observations"), list):
            raise ProtocolError("invalid evaluate request")
        result = evaluate_core_name(request["observations"], job_id=request["job_id"],
                                    nonce=request["nonce"], key=key)
        sys.stdout.buffer.write(__import__("backend.java_executor", fromlist=["encode_frame"]).encode_frame(result))
        sys.stdout.buffer.flush()
        return 0
    except (EOFError, ProtocolError, KeyError, TypeError, ValueError):
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
