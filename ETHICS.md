# Ethics & Responsible Use

This project is for **defensive / measurement security research** on agent skills.

- The bundled "malicious" skills are **inert, canary-only** samples. Their exfiltration
  endpoints are unreachable (`*.evil`, `*.canary.*`) and the sandbox blocks egress, so
  nothing actually leaks. They exist to be **scanned and to test isolation**, never to run
  against real targets.
- Do **not** use this against systems, registries, or credentials you are not authorized to test.
- Run real agents only inside the provided sandbox (non-root, read-only rootfs, egress allowlist).
- The single secret placed in the container is the LLM API key you provide; the egress lock is
  designed so that even a malicious skill cannot exfiltrate it or reach cloud metadata.
