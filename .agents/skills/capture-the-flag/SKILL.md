---
name: capture-the-flag
description: Investigate source-available capture-the-flag challenges, especially language sandboxes or restricted-execution services. Use when asked to review challenge code, reproduce the target locally, develop exploit probes, validate payloads against a live endpoint, confirm claimed results against the deployed service when available, capture a flag, or turn an exploit into a regression test or hardening patch.
---

# Capture The Flag

Establish the real target before chasing primitives.

- Read the public contract, runtime, and success channel first.
- Identify how input reaches the challenge and how success is surfaced: HTTP response, stdout, files, exit codes, or side effects.
- Prefer the deployed behavior over assumptions from generic exploit patterns.

Reproduce locally as early as possible.

- Run the smallest local entrypoint that exercises the same code path as the live challenge.
- Match the real runtime when behavior could be version-sensitive.
- Use existing tests as a map of closed doors, not just as verification.

Search for boundary mismatches between restricted code and host code.

- Look for plain internal state exposed on wrapper objects, not just blocked dunder chains.
- Inspect helper functions or "safe" builtins that are still ordinary host objects.
- Check metadata paths that may re-evaluate strings or names: signatures, annotations, typing, serialization, descriptors, dataclasses, and similar reflection APIs.
- Inspect locals/globals reconstruction, exception state, generator or coroutine state, module-loading paths, and cached host objects.
- Deprioritize well-known pivots that the code or tests already block unless you see a concrete gap.

Develop payloads one primitive at a time.

1. Form a narrow hypothesis from code.
2. Prove or kill it with the smallest possible local probe.
3. Make the result visible with `print(...)`, a sentinel read, or another direct signal.
4. Promote only locally working primitives to the live target.
5. Turn the working primitive into a final payload that actually reveals the flag.

Keep probes short. A failed tiny probe teaches more than a large speculative payload.

Validate against the live service only after local confirmation.

- Use a client that makes quoting easy for multiline payloads.
- Treat transport details as secondary unless the challenge is specifically in the transport layer.
- Treat the live deployment as the final arbiter for any claimed exploit or flag when it is available.
- Confirm the final exploit prints or otherwise returns the flag, not just that it reaches an interesting object.

When the task includes fixing the bug, tie the exploit to a concrete boundary failure and add a regression test for that primitive.

If the target is this repository, start with `README.md`, `www/app.py`, `www/Dockerfile`, `src/pynterp/`, and the security tests. Confirm any claimed escape or captured flag against `https://pynterp.gmj.dev/`; treat a local-only result as unconfirmed. The main lesson from this codebase is to prioritize ordinary host objects and host-side introspection or evaluation paths over only chasing classic Python reflection chains.
