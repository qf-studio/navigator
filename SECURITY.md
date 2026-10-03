 # Security Policy

  ## Supported Versions

  | Version | Supported          |
  | ------- | ------------------ |
  | 3.1.x   | :white_check_mark: |
  | 3.0.x   | :white_check_mark: |
  | 2.x.x   | :x:                |
  | < 2.0   | :x:                |

  ## Reporting a Vulnerability

  ### Where to Report

  If you discover a security vulnerability in Navigator, please report it via:

  - **GitHub Security Advisories**:
  https://github.com/qf-studio/navigator/security/advisories/new (preferred)
  - **Email**: aleks@quantflow.studio (if you prefer private disclosure)

  ### What to Include

  Please provide:
  - Description of the vulnerability
  - Steps to reproduce
  - Potential impact
  - Affected versions (if known)
  - Suggested fix (if any)

  ### Response Timeline

  - **Initial Response**: Within 48 hours
  - **Status Update**: Every 7 days until resolved
  - **Fix Timeline**: Critical issues within 7 days, others within 30 days

  ### What to Expect

  **If Accepted**:
  - We'll acknowledge the issue and work on a fix
  - You'll be credited in the security advisory (unless you prefer anonymity)
  - We'll notify you when the patch is released
  - A CVE may be issued for critical vulnerabilities

  **If Declined**:
  - We'll explain why it's not considered a security issue
  - We may suggest alternative solutions or mitigations

  ## Security Best Practices

  Navigator is a development tool that:
  - Does not collect or transmit user data
  - Runs locally on your machine
  - Has access to your project files (by design)

  **Users should**:
  - Only install Navigator from official sources (GitHub marketplace)
  - Review generated code before committing
  - Keep Navigator updated to the latest version
  - Report suspicious behavior immediately

  ## Scope

  **In Scope**:
  - Code execution vulnerabilities
  - Privilege escalation
  - Data leakage or exposure
  - Malicious code injection

  **Out of Scope**:
  - Issues in dependencies (report to upstream)
  - Claude Code platform bugs (report to Anthropic)
  - Social engineering attacks
  - Physical access attacks

  ## Past Security Issues

  No security vulnerabilities have been reported or fixed to date.
