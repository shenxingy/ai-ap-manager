# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in AI AP Manager, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, email: **alex@get-reality.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix release**: Depends on severity, typically within 2 weeks for critical issues

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | Yes       |

## Security Best Practices for Deployment

- Always change default secrets (`JWT_SECRET`, `APPROVAL_TOKEN_SECRET`) — generate with `openssl rand -hex 32`
- Use HTTPS in production (configure SSL in nginx)
- Keep Docker images updated
- Set `APP_ENV=production` to disable debug endpoints
- Never expose PostgreSQL or Redis ports publicly
- Review `.env.example` for all security-relevant configuration
