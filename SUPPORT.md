# Support

## Getting help

- **Bugs and installation problems:** open an issue using the bug template.
  Include the image tag or digest, `bootc status`, hardware/RAM, and relevant
  logs.
- **Feature requests and design questions:** open an issue using the feature
  template.
- **Security vulnerabilities:** do not open a public issue. Use
  [private vulnerability reporting](https://github.com/adwaita-blue-lite/adwaita-lite/security/advisories/new).
  See [`SECURITY.md`](SECURITY.md).

## Supported streams

| Stream | Tag | Support |
|---|---|---|
| Stable | `latest` | Supported |
| Developer | `dx` | Supported for development use |
| Testing | `testing` | Experimental |
| Beta canary | `beta` | Experimental |

Only current stream images are supported. Date tags are kept for pinning but
do not receive backports.

## Before filing

1. Check the [existing issues](https://github.com/adwaita-blue-lite/adwaita-lite/issues).
2. Reproduce on the latest `latest` image if possible.
3. Remove secrets, Wi-Fi passwords, and personal data from logs.
4. Include the output of:

```bash
bootc status
ujust --list
journalctl -b -p err --no-pager
```

There is no private support email. Use the public issue tracker for
non-security problems and private vulnerability reporting for security.
