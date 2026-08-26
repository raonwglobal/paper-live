# GitHub Plugin Security

GitHub repository URLs are treated as untrusted input. Adding a URL does not grant execution or broker access.

## Lifecycle

1. Parse and validate HTTPS GitHub source.
2. Fetch metadata/manifest only.
3. Pin an immutable commit before installation.
4. Verify artifact integrity (SHA-256 and, when configured, signature).
5. Validate requested permissions against the server policy.
6. Run untrusted code only inside a restricted sandbox.
7. Register skills only after verification.
8. Route all trading operations through RiskGuardian, ExecutionGateway and EnvironmentController.
9. `REAL_LIVE` always requires the existing explicit LiveApprovalGate; a plugin cannot grant itself live access.

## Default-deny permissions

- Shell execution: denied.
- Credential-bearing repository URLs: denied.
- Arbitrary network destinations: denied.
- Secrets: not inherited from the host; explicit allow-list only.
- Filesystem: explicit read/write allow-list only.
- Live broker execution: denied to plugins by default.

## Important boundary

The repository loader fetches `plugin.yaml` metadata only. It must never import or execute downloaded repository code. A separate sandbox installer/executor is required before a plugin can become executable.
