# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for a
suspected vulnerability.

Use GitHub's private vulnerability reporting:
[**Report a vulnerability**](https://github.com/musharna/ghostcite/security/advisories/new)
(Security → Advisories → Report a vulnerability on the repo).

Include as much as you can: affected version/commit, a reproduction, and the
impact you observed. You'll get an acknowledgement within a few days; please
allow time for a fix before any public disclosure.

## Threat model

ghostcite is a read-only CLI. Its full external footprint is:

- **Outbound HTTPS GET** to `api.crossref.org` (CrossRef metadata lookup).
- **Outbound HTTPS GET** to `eutils.ncbi.nlm.nih.gov` (optional PubMed
  cross-check, only when `--pubmed` / `NCBI_API_KEY` is supplied).

It stores nothing, runs no server, spawns no subprocesses, and executes no
untrusted input. The only credential it touches is an optional
`NCBI_API_KEY` (env var or `--ncbi-api-key` flag) passed through to NCBI
rate-limit headers — it is never logged or written to disk.

**In scope** (please report):

- Any path by which ghostcite executes code derived from user-supplied input
  (e.g. a BibTeX file that triggers arbitrary execution).
- Credential leakage: `NCBI_API_KEY` appearing in logs, error output, or
  network requests to a host other than `eutils.ncbi.nlm.nih.gov`.
- HTTPS downgrade or certificate-validation bypass in the HTTP client.

**Out of scope** (accepted, documented properties):

- Network errors or rate-limiting from CrossRef/NCBI — ghostcite is a
  best-effort tool and surfaces these as warnings.
- Results that differ from CrossRef/NCBI ground truth due to metadata lag.

## Supported versions

ghostcite is pre-1.0; security fixes land on the latest release. Pin a version
and watch releases for advisories.
