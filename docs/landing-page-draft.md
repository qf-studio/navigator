# Navigator

## Finish What You Start

Context engineering for Claude Code. Sessions that last. Features that ship.

---

## The Problem

You're five exchanges into implementing a feature. Claude starts forgetting your recent changes. Six exchanges in, it hallucinates a function that doesn't exist. Seven exchanges, session crashes.

You check: **150,000 tokens loaded**. Only used **8,000**.

You were wasting 94% of your context window on documentation you never needed.

---

## The Solution

Navigator loads what you need, when you need it.

Not "load everything just in case."
Not "better safe than sorry."

**Strategic loading beats bulk loading.**

| Before Navigator | With Navigator |
|------------------|----------------|
| 150k tokens loaded | 12k tokens loaded |
| Crashes at exchange 7 | 20+ exchanges |
| Restart, lose context | Finish the feature |

---

## How It Works

**1. Start your session**
```
"Start my Navigator session"
```
Loads a 2k-token index. Not 150k of docs.

**2. Work on your feature**
Navigator loads relevant docs on-demand as you need them.

**3. Finish what you started**
Sessions last 20+ exchanges. Features actually ship.

---

## Install

```bash
claude plugin add https://github.com/qf-studio/navigator
```

Then in any project:
```
"Initialize Navigator in this project"
```

---

## What You Get

- **24 skills** for common workflows (components, endpoints, migrations)
- **Context markers** to save/restore progress (97% compression)
- **Task documentation** that writes itself
- **SOPs** to capture solutions for reuse

---

## Proven Results

- **92% token reduction** (OpenTelemetry-verified)
- **20+ exchanges** per session (vs 7 without)
- **Zero session restarts** during feature implementation

---

## Open Source

MIT License. Built for developers who ship.

[GitHub →](https://github.com/qf-studio/navigator)

---

*Navigator v5.2.0*
