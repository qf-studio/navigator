---
name: database-migration
description: Create database migration with schema changes and rollback. Auto-invoke when user says "create migration", "add table", "modify schema", or "change database".
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
version: 2.0.0
---

# Database Migration Generator

Generate database migrations with rollback capability for schema changes, with built-in ToM verification for safe database operations.

> **Implementation note**: This skill uses direct `Write()` calls with inline templates (see Steps 3–4 and "Schema Change Templates" section below). Unlike `frontend-component` and `backend-endpoint`, there are no Python helper functions — the skill is prose-driven by design, since migration generation is highly schema-specific and benefits from inline framework templates. Future work (tracked for v6.6.0) may extract a timestamp generator and per-framework templates.

## When to Invoke

Auto-invoke when user mentions:
- "Create migration"
- "Add table"
- "Modify schema"
- "Change database"
- "Database migration for [change]"
- "Add column to [table]"
- "Rename [table/column]"

## What This Does

1. Detects migration framework (Knex, Prisma, TypeORM, raw SQL)
2. Gathers migration requirements
3. **Verifies understanding before generating** (ToM checkpoint - critical for DB changes)
4. Generates migration file with timestamp
5. Creates schema change (up migration)
6. Creates rollback (down migration)
7. Validates migration safety
8. Shows migration summary

## Execution Steps

### Step 0: Check Existing Patterns (Phase 0)

Before detecting the framework, query the knowledge graph for what we already know about database work in this project. For migrations — the highest-stakes execution path — Phase 0 is especially valuable because past pitfalls (failed NOT NULL adds, bad rollback assumptions, naming collisions) often repeat.

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
python3 "$PLUGIN_DIR/skills/nav-graph/functions/graph_manager.py" \
  --action query --concept database \
  --graph-path .agent/knowledge/graph.json 2>/dev/null | head -40
```

Also check `migration`, `schema`, and `performance` (for index decisions).

If memories surface (`PATTERN`, `PITFALL`, `DECISION` entries), read the full memory files for any relevant ones:
```bash
ls .agent/knowledge/memories/{patterns,pitfalls,decisions}/ 2>/dev/null
```

**What to do with what you find**:
- **Patterns**: apply them (e.g. "we always use UUIDs over auto-increment IDs")
- **Pitfalls**: avoid them — these are the most important for migrations (record what you avoided in `pitfalls_avoided` in Step 7)
- **Decisions**: respect them (e.g. "we chose JSONB over separate tables for tags")

Skip this step only if the knowledge graph is disabled in `.agent/.nav-config.json`.

### Step 1: Detect Migration Framework

**Check project for migration tool**:

```bash
# Check for Knex
if [ -f "knexfile.js" ] || [ -f "knexfile.ts" ] || grep -q '"knex"' package.json 2>/dev/null; then
  echo "Knex detected"
fi

# Check for Prisma
if [ -f "prisma/schema.prisma" ]; then
  echo "Prisma detected"
fi

# Check for TypeORM
if [ -f "ormconfig.json" ] || [ -f "ormconfig.ts" ] || grep -q '"typeorm"' package.json 2>/dev/null; then
  echo "TypeORM detected"
fi

# Check for Drizzle
if grep -q '"drizzle-orm"' package.json 2>/dev/null; then
  echo "Drizzle detected"
fi
```

**Framework detection result**:
```
Detected: {FRAMEWORK}
Migration directory: {MIGRATION_PATH}
Naming convention: {CONVENTION}
```

**If no framework detected**:
```
⚠️  No migration framework detected

Options:
1. Generate raw SQL migrations
2. Set up Knex (recommended for flexibility)
3. Set up Prisma (recommended for type safety)

Your choice [1-3]:
```

### Step 2: Gather Migration Requirements

**Ask user for migration details**:
```
Migration name: [e.g., add_user_verification_columns]
Change type:
  - create_table (new table)
  - add_column (add to existing table)
  - modify_column (change existing column)
  - drop_column (remove column)
  - rename (rename table or column)
  - add_index (create index)
  - add_constraint (foreign key, unique, etc.)

Target table: [e.g., users]

Schema details: [describe the changes]
```

### Step 2.5: Verify Understanding (ToM Checkpoint - ALWAYS for DB) [EXECUTE]

**CRITICAL**: This step MUST ALWAYS be executed for database migrations. No exceptions.

**Database migrations are high-stakes - ALWAYS verify before generating**.

**Display verification**:
```
I understood you want:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Migration: {MIGRATION_NAME}
Framework: {FRAMEWORK} (detected)
Type: {CHANGE_TYPE}
Target: {TABLE_NAME}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Schema Changes (UP):
{SCHEMA_CHANGE_PREVIEW}

Rollback (DOWN):
{ROLLBACK_PREVIEW}

⚠️  Database migrations affect production data
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Assumptions I'm making:
- Column types match existing conventions
- Indexes will use default naming
- No data migration needed (schema only)

Proceed with generation? [Y/n]
```

**Never skip verification for database migrations** - they can cause data loss.

### Step 3: Generate Migration File

**Based on detected framework**:

#### Knex Migration
```bash
# Generate filename
TIMESTAMP=$(date +%Y%m%d%H%M%S)
FILENAME="${TIMESTAMP}_${MIGRATION_NAME}.ts"

# Create migration file
Write(
  file_path: "migrations/${FILENAME}",
  content: [knex migration template]
)
```

**Knex template**:
```typescript
import { Knex } from 'knex';

export async function up(knex: Knex): Promise<void> {
  ${UP_MIGRATION}
}

export async function down(knex: Knex): Promise<void> {
  ${DOWN_MIGRATION}
}
```

#### Prisma Migration
```bash
# Prisma uses schema.prisma + migrate commands
# Update schema.prisma with new models/fields
# Then run: npx prisma migrate dev --name ${MIGRATION_NAME}
```

**Show Prisma workflow**:
```
Prisma detected - updating schema.prisma

1. I'll update prisma/schema.prisma with:
   ${SCHEMA_CHANGES}

2. Run migration:
   npx prisma migrate dev --name ${MIGRATION_NAME}

3. Generate client:
   npx prisma generate
```

#### TypeORM Migration
```bash
TIMESTAMP=$(date +%Y%m%d%H%M%S)
FILENAME="${TIMESTAMP}-${MIGRATION_NAME}.ts"
```

**TypeORM template**:
```typescript
import { MigrationInterface, QueryRunner, Table } from 'typeorm';

export class ${MIGRATION_CLASS_NAME}${TIMESTAMP} implements MigrationInterface {
  public async up(queryRunner: QueryRunner): Promise<void> {
    ${UP_MIGRATION}
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    ${DOWN_MIGRATION}
  }
}
```

### Step 4: Generate Rollback Logic

**Ensure every UP has a corresponding DOWN**:

| UP Operation | DOWN Operation |
|--------------|----------------|
| CREATE TABLE | DROP TABLE |
| ADD COLUMN | DROP COLUMN |
| ADD INDEX | DROP INDEX |
| ADD CONSTRAINT | DROP CONSTRAINT |
| RENAME | RENAME (reverse) |
| ALTER COLUMN | ALTER COLUMN (reverse) |

**Warning for destructive operations**:
```
⚠️  DROP COLUMN in DOWN migration will lose data!

Column: {COLUMN_NAME}
Type: {COLUMN_TYPE}

If this column has data, consider:
1. Backup data before migration
2. Add data migration step
3. Keep column but deprecate

Understood? [Y/n]
```

### Step 5: Validate Migration Safety

**Check for common issues**:

```
Migration Safety Check:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Rollback defined (can undo changes)
✅ No DROP TABLE without backup warning
✅ No ALTER on large tables without consideration
⚠️  Adding NOT NULL column - needs DEFAULT value
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Safety warnings to check**:
- Adding NOT NULL without DEFAULT (will fail on existing rows)
- Dropping columns with data
- Renaming columns (may break application code)
- Adding UNIQUE constraint (may fail if duplicates exist)
- Large table alterations (may lock table)

### Step 6: Show Migration Summary

**Display completed migration**:

```
✅ Migration Created: {MIGRATION_NAME}

File: {MIGRATION_PATH}/{FILENAME}
Framework: {FRAMEWORK}
Timestamp: {TIMESTAMP}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Schema Changes:
┌─────────────────────────────────────────────┐
│ UP (Apply)                                  │
├─────────────────────────────────────────────┤
│ {UP_MIGRATION_SUMMARY}                      │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ DOWN (Rollback)                             │
├─────────────────────────────────────────────┤
│ {DOWN_MIGRATION_SUMMARY}                    │
└─────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run Migration:
{RUN_COMMAND}

Test Rollback:
{ROLLBACK_COMMAND}

Next Steps:
1. Review migration file
2. Test on development database
3. Run migration: {RUN_COMMAND}
4. Verify schema changes
5. Commit migration file
```

### Step 7: Emit Execution Summary (Graph Ingestion)

After Step 6, emit an `execution_summary` JSON block. Database migrations are the highest-stakes execution path — recording the patterns and decisions here is the most valuable. This block flows into the knowledge graph via `execution_to_graph.py`.

**Output the block verbatim** (replace placeholders with actual values):

```json
{
  "execution_summary": {
    "skill": "database-migration",
    "task": "{MIGRATION_NAME}",
    "files_created": ["{migration file path}"],
    "files_modified": [],
    "tests_added": [],
    "stack_detected": "{e.g. knex+postgres or prisma+postgres}",
    "patterns_followed": [
      {"summary": "{convention applied — e.g. timestamp-prefixed filenames, UUID primary keys}", "concepts": ["database"], "confidence": 0.8}
    ],
    "decisions_made": [
      {"summary": "{non-obvious choice — e.g. used VARCHAR(255) over TEXT for indexability}", "concepts": ["database"], "confidence": 0.75, "evidence": "{path:line}"}
    ],
    "pitfalls_avoided": [
      {"summary": "{e.g. added DEFAULT to NOT NULL column to avoid failing on existing rows}", "concepts": ["database"], "confidence": 0.9}
    ],
    "assumptions_made": ["{e.g. PostgreSQL 14+ — used gen_random_uuid()}"]
  }
}
```

**Ingestion** (run from project root):

```bash
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cat "${NAVIGATOR_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/navigator}/plugin-root" 2>/dev/null)}"
[ -d "$PLUGIN_DIR/skills" ] || PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/navigator-marketplace"
echo '<execution_summary JSON>' | python3 "$PLUGIN_DIR/skills/nav-graph/functions/execution_to_graph.py" -
```

**Migration-specific rules**:
- Always record pitfalls — DB changes are easy to get wrong, future agents need the warning.
- Stack detection should include both the migration framework AND the target DB (e.g. `knex+postgres`).
- Decisions about column types, indexes, and constraints are valuable to capture even when they feel obvious.

---

## Schema Change Templates

### Create Table (Knex)
```typescript
export async function up(knex: Knex): Promise<void> {
  await knex.schema.createTable('${TABLE_NAME}', (table) => {
    table.uuid('id').primary().defaultTo(knex.raw('gen_random_uuid()'));
    ${COLUMN_DEFINITIONS}
    table.timestamps(true, true);
  });
}

export async function down(knex: Knex): Promise<void> {
  await knex.schema.dropTableIfExists('${TABLE_NAME}');
}
```

### Add Column (Knex)
```typescript
export async function up(knex: Knex): Promise<void> {
  await knex.schema.alterTable('${TABLE_NAME}', (table) => {
    table.${COLUMN_TYPE}('${COLUMN_NAME}')${MODIFIERS};
  });
}

export async function down(knex: Knex): Promise<void> {
  await knex.schema.alterTable('${TABLE_NAME}', (table) => {
    table.dropColumn('${COLUMN_NAME}');
  });
}
```

### Add Index (Knex)
```typescript
export async function up(knex: Knex): Promise<void> {
  await knex.schema.alterTable('${TABLE_NAME}', (table) => {
    table.index(['${COLUMN_NAME}'], '${INDEX_NAME}');
  });
}

export async function down(knex: Knex): Promise<void> {
  await knex.schema.alterTable('${TABLE_NAME}', (table) => {
    table.dropIndex(['${COLUMN_NAME}'], '${INDEX_NAME}');
  });
}
```

---

## Framework-Specific Commands

### Knex
```bash
# Run pending migrations
npx knex migrate:latest

# Rollback last batch
npx knex migrate:rollback

# Run specific migration
npx knex migrate:up ${MIGRATION_NAME}

# Check status
npx knex migrate:status
```

### Prisma
```bash
# Create and apply migration
npx prisma migrate dev --name ${MIGRATION_NAME}

# Apply in production
npx prisma migrate deploy

# Reset database (dev only)
npx prisma migrate reset

# Check status
npx prisma migrate status
```

### TypeORM
```bash
# Run pending migrations
npx typeorm migration:run

# Revert last migration
npx typeorm migration:revert

# Generate migration from entities
npx typeorm migration:generate -n ${MIGRATION_NAME}

# Show migrations
npx typeorm migration:show
```

---

## Error Handling

**Framework not detected**:
```
⚠️  No migration framework detected in project

Please set up a migration framework first:
- Knex: npm install knex && npx knex init
- Prisma: npm install prisma && npx prisma init
- TypeORM: npm install typeorm && create ormconfig
```

**Migration name conflict**:
```
⚠️  Migration with similar name already exists

Existing: 20251209_add_users_table.ts
Requested: add_users_table

Options:
1. Use different name
2. Add version suffix (add_users_table_v2)
3. Check if existing migration is sufficient

Your choice [1-3]:
```

**Validation failure**:
```
❌ Migration validation failed

Issues:
- Column 'status' is NOT NULL but has no DEFAULT
- Table 'orders' doesn't exist (referenced in foreign key)

Fix these issues before generating migration.
```

---

## Success Criteria

Migration is successful when:
- [ ] Migration file generated with unique timestamp
- [ ] Framework conventions followed
- [ ] UP migration creates/modifies schema correctly
- [ ] DOWN migration rolls back changes completely
- [ ] ToM verification passed (user confirmed understanding)
- [ ] Safety checks passed
- [ ] Commands shown for running migration

---

## Best Practices

### Naming Conventions
- `create_users_table` - for new tables
- `add_email_to_users` - for adding columns
- `add_index_on_users_email` - for indexes
- `change_status_type_in_orders` - for modifications

### Safety
- Always test on development database first
- Backup production before running migrations
- Use transactions where supported
- Consider data migration for non-null columns

### Code Review
- Review generated SQL before running
- Check rollback logic is complete
- Verify no data loss in DOWN migration
- Test full rollback cycle

---

**Database migrations affect production data - ToM verification is mandatory for this skill** 🗄️
