# Next.js SaaS - Navigator Reference Example

> **This is NOT a starter template.** This is a reference implementation showing Navigator documentation workflow for a Next.js SaaS project.

---

## What This Example Shows

**The Value**: Complete `.agent/` structure with real documentation
- ✅ Task implementation plans (how features were planned)
- ✅ System architecture docs (tech decisions documented)
- ✅ Standard Operating Procedures (patterns discovered during development)
- ✅ Navigator workflow in action (navigator-first, on-demand loading)

**NOT Included**: Production-ready code to copy-paste
- ❌ No guarantee of latest Next.js version
- ❌ No "run npm install and deploy" starter kit
- ❌ Not meant to be forked as-is

---

## How to Use This Example

### 1. Study the `.agent/` Structure

```bash
# Read the navigator first (Navigator workflow)
cat .agent/DEVELOPMENT-README.md

# See how tasks were planned
ls .agent/tasks/

# See how patterns were documented
ls .agent/sops/development/

# See architecture decisions
cat .agent/system/project-architecture.md
```

### 2. Copy the Pattern, Not the Code

**Do this**:
```bash
# Copy .agent/ structure to your project
cp -r examples/nextjs-saas/.agent/ your-project/

# Customize for your stack
vim your-project/.agent/DEVELOPMENT-README.md
vim your-project/.agent/system/project-architecture.md
```

**Don't do this**:
```bash
# Fork this repo as starter template ❌
# Copy-paste code without understanding ❌
```

### 3. Adapt to Your Tech Stack

This example uses specific choices (see `stack-choices.md`).

**If you use different tech**, the `.agent/` structure stays the same:
- Keep: Navigator pattern, task structure, SOP organization
- Change: Framework names, tool names, specific patterns

**Navigator workflow is universal. Tech stack is not.**

---

## What You'll Learn

### Navigator Workflow in Practice

**See how**:
1. Features start as task docs (`.agent/tasks/TASK-XX.md`)
2. Implementation generates SOPs (`.agent/sops/development/`)
3. Decisions documented (`.agent/system/`)
4. Knowledge compounds over time

### Documentation Quality

**Examples of**:
- Well-written task plans (context, steps, decisions)
- Useful SOPs (how to add feature, how to debug issue)
- Clear architecture docs (what, why, tradeoffs)
- Navigator efficiency (2k tokens, high value)

### Token Optimization

**See**:
- Navigator loads first (~2k tokens)
- Task docs loaded on-demand (~3k each)
- System docs lazy-loaded (~5k)
- Total: ~12k vs 150k loading everything

---

## Project Context

**Imaginary SaaS app**: AI content generation tool with credits system

**Features built** (as documented in `.agent/tasks/`):
- TASK-01: Authentication (Supabase Auth)
- TASK-02: Dashboard layout (Next.js App Router)
- TASK-03: Credits system (PostgreSQL)
- TASK-04: Stripe integration (payments)
- TASK-05: AI API integration (OpenAI)

**Not actually built** - Just documented to show Navigator workflow

---

## Tech Stack (This Example)

See `stack-choices.md` for full reasoning and alternatives.

**Framework**: Next.js 15 (App Router, SSR)
**Styling**: Tailwind CSS
**Database**: Supabase (PostgreSQL)
**Auth**: Supabase Auth
**Payments**: Stripe
**Hosting**: Vercel

**Created**: 2025-10-15
**Next.js version at creation**: 15.0.x

**These versions will be outdated.** Use latest when you build.

---

## Quick Start (For Understanding Navigator)

```bash
# 1. Read the navigator
cat .agent/DEVELOPMENT-README.md

# 2. Pick a task to study
cat .agent/tasks/TASK-01-auth-setup.md

# 3. See the SOP created from that task
cat .agent/sops/development/adding-protected-routes.md

# 4. Understand the architecture
cat .agent/system/project-architecture.md

# 5. Copy the .agent/ structure to your project
cp -r .agent/ ~/your-project/

# 6. Start your Navigator workflow
cd ~/your-project
/nav:start
```

---

## Questions?

**"Can I use this with Remix/SvelteKit/Vue?"**
Yes. The `.agent/` structure works with any framework. Change the framework names in docs.

**"Can I use this with different styling (CSS Modules, etc.)?"**
Yes. The Navigator workflow doesn't care about styling choices. Update docs to match your stack.

**"Why Supabase? I use Firebase/Prisma"**
Arbitrary choice for this example. Replace with your DB/auth setup. `.agent/` structure stays the same.

**"Is there actual code in this example?"**
No. This is a documentation reference, not a code starter. The value is the `.agent/` folder.

**"What if Next.js 16 changes everything?"**
The Navigator workflow (navigator → tasks → SOPs) won't change. Update framework-specific docs.

---

## Repository

Part of [Navigator Plugin](https://github.com/qf-studio/navigator)

**More examples**:
- `examples/python-api/` - FastAPI backend example (coming soon)

---

**Remember**: Copy the documentation pattern, not the code. Navigator is about workflow, not tech stack.
