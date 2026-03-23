# Security Policy

## Supported Versions

| Version | Supported          |
|---------|-------------------|
| 0.2.x   | ✅ Yes             |

## Reporting a Vulnerability

If you discover a security vulnerability in OpenEtruscan, **please do not open a public issue.**

Instead, report it privately:

1. **Email:** Send details to the maintainers via GitHub's private vulnerability reporting feature at [https://github.com/Eddy1919/openEtruscan/security/advisories/new](https://github.com/Eddy1919/openEtruscan/security/advisories/new)
2. **Include:** A description of the vulnerability, steps to reproduce, and potential impact

We will acknowledge your report within 48 hours and aim to release a fix within 7 days for critical issues.

## Scope

The following are in scope:
- SQL injection in the corpus query API
- Path traversal in file upload endpoints
- Credential leaks in committed files
- Docker container escape / privilege escalation

The following are **out of scope**:
- The public read-only corpus database (it is intentionally public)
- Brute-force attacks against rate-unlimited endpoints (we're an open corpus, not a bank)

## Responsible Disclosure

We follow [coordinated vulnerability disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure). We will credit you in the release notes unless you prefer to remain anonymous.
