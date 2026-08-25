# Security policy

## Supported version

Security fixes are applied to the `langchain-migration` branch while the
project remains a work in progress.

## Reporting a vulnerability

Please use GitHub's private vulnerability-reporting feature for this
repository. Do not open a public issue containing credentials, private DARS
data, or an unpatched exploit. Include the affected commit, reproduction steps,
impact, and any proposed mitigation.

## Deployment boundaries

- DARS reports contain education records. Run the application locally unless
  the deployment has appropriate access control, encryption, retention, and
  institutional approval.
- BYOK credentials are request-only and must never be logged. Public operators
  should enforce an outbound provider allowlist in addition to application URL
  validation.
- SQLite is the default for a single-process local deployment. Use one Uvicorn
  worker with this configuration. A multi-instance service should replace the
  local job runner and SQLite checkpointer with managed queue and database
  services.
- Keep dependencies updated and do not enable private or insecure model base
  URLs on a public server.
