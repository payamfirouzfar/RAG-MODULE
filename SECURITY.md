# Security Policy

## Reporting a vulnerability

Please report suspected security issues privately rather than opening a
public issue. Include a description of the issue and steps to reproduce.

## Scope and guarantees

- The core kernel (`src/ragtorch/core`) never executes arbitrary shell
  commands, loads arbitrary code, or logs secrets.
- Do not commit `.env` files or credentials. `.gitignore` excludes `.env`.
- Dependencies are kept minimal deliberately; the core has zero runtime
  dependencies outside the Python standard library.
