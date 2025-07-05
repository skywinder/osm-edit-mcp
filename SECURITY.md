# Security Policy

## Supported Versions

Currently supported versions for security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please follow these steps:

### 1. **Do NOT** create a public GitHub issue

Security vulnerabilities should not be reported publicly to avoid exploitation.

### 2. Report privately

Send an email to: right.crew7885@fastmail.com

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if available)

### 3. Response timeline

- **Initial response**: Within 48 hours
- **Status update**: Within 7 days
- **Resolution target**: Within 30 days for critical issues

## Security Best Practices

When using OSM Edit MCP Server:

### Authentication

1. **Never share OAuth tokens**
   - Tokens are stored securely in your system keyring
   - Don't commit token files to version control

2. **Use development API for testing**
   - Always test with `OSM_USE_DEV_API=true`
   - Only use production API when necessary

3. **Rotate credentials regularly**
   - Revoke and regenerate OAuth apps periodically
   - Update tokens if compromise is suspected

### Configuration

1. **Environment variables**
   ```bash
   # Never commit .env files
   # Use .env.example as template
   cp .env.example .env
   ```

2. **Secure file permissions**
   ```bash
   chmod 600 .env
   chmod 600 .osm_token_*.json
   ```

### API Usage

1. **Rate limiting**
   - Respect OSM API rate limits
   - Default: 60 requests per minute
   - Configure in .env if needed

2. **Input validation**
   - All inputs are validated before API calls
   - Coordinate ranges are checked
   - Tag values are sanitized

3. **Error handling**
   - Errors don't expose sensitive data
   - API keys are never logged
   - Stack traces are sanitized

## Security Features

### Built-in protections

1. **OAuth 2.0 authentication**
   - Industry-standard authentication
   - Secure token storage with keyring
   - Automatic token refresh

2. **HTTPS only**
   - All API calls use HTTPS
   - Certificate verification enabled
   - No fallback to HTTP

3. **Development/Production separation**
   - Separate OAuth apps for dev/prod
   - Different API endpoints
   - Clear mode indicators

4. **Audit logging**
   - User actions are logged
   - Changeset tracking
   - No sensitive data in logs

### Security checklist

Before deploying:

- [ ] Review all environment variables
- [ ] Ensure .gitignore includes sensitive files
- [ ] Run security audit: `python scripts/security_audit.py`
- [ ] Test with development API first
- [ ] Review OAuth app permissions
- [ ] Enable rate limiting
- [ ] Configure secure logging

## Known Security Considerations

1. **Token storage**
   - Tokens are stored locally
   - Use system keyring when available
   - Fallback to encrypted JSON files

2. **API limitations**
   - OSM API has public read access
   - Write operations require authentication
   - Some operations need special permissions

3. **Natural language processing**
   - User input is parsed locally
   - No data sent to external NLP services
   - Sanitization before API calls

## Security Updates

Subscribe to security updates:
- Watch the GitHub repository
- Check releases for security patches
- Follow [@skywinder](https://github.com/skywinder) for announcements

## Acknowledgments

Thanks to the security researchers who help keep this project secure through responsible disclosure.