#!/usr/bin/env python3
"""
Task to Graph - Syncs task documents with knowledge graph

Extracts concepts and decisions from task documents and updates the graph.
"""

import json
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from graph_manager import load_graph, save_graph, add_node, add_edge, add_memory


def extract_concepts_from_task(content: str) -> list:
    """Extract concepts from task document content."""
    concepts = set()

    keyword_map = {
        'auth': 'authentication',
        'login': 'authentication',
        'jwt': 'authentication',
        'oauth': 'authentication',
        'api': 'api',
        'endpoint': 'api',
        'rest': 'api',
        'graphql': 'api',
        'test': 'testing',
        'spec': 'testing',
        'unit': 'testing',
        'integration': 'testing',
        'component': 'frontend',
        'react': 'frontend',
        'vue': 'frontend',
        'database': 'database',
        'migration': 'database',
        'schema': 'database',
        'deploy': 'deployment',
        'ci': 'deployment',
        'cd': 'deployment',
        'skill': 'skills',
        'plugin': 'skills',
        'marker': 'markers',
        'compact': 'markers',
        'context': 'context',
        'token': 'context',
        'memory': 'knowledge',
        'graph': 'knowledge',
        'profile': 'theory of mind',
        'tom': 'theory of mind',
        'loop': 'workflow',
        'task.mode': 'workflow',
        'simplif': 'simplification',
    }

    content_lower = content.lower()
    for keyword, concept in keyword_map.items():
        if keyword in content_lower:
            concepts.add(concept)

    return list(concepts) if concepts else ['general']


# Emoji → canonical status. Emoji-only Status lines (no word) resolve here.
STATUS_EMOJI = {
    '✅': 'completed',
    '🚧': 'in-progress',
    '📋': 'backlog',
    '🔬': 'research',
    '📐': 'design',
    '❌': 'deprecated',
    '🚫': 'blocked',
    '📨': 'dispatched',
}

# (phrase, canonical) matched case-insensitively as whole words against the
# Status line, most-specific phrase first so 'in progress' wins over any
# shorter substring. Existing canonicals (completed/in-progress/backlog/
# research) are preserved; new task states get their own canonical value.
STATUS_WORDS = [
    ('in progress', 'in-progress'),
    ('completed', 'completed'),
    ('complete', 'completed'),
    ('implemented', 'completed'),
    ('deprecated', 'deprecated'),
    ('dispatched', 'dispatched'),
    ('blocked', 'blocked'),
    ('planned', 'backlog'),
    ('backlog', 'backlog'),
    ('research', 'research'),
    ('design', 'design'),
]

# Tolerant Status-line matcher: accepts '**Status**:', '**Status:**', 'Status:'
# with optional blockquote/bold/whitespace decoration around the label.
_STATUS_LINE = re.compile(
    r'(?im)^[>\s]*\*{0,2}\s*status\s*\*{0,2}\s*:\s*\*{0,2}\s*(.+?)\s*$'
)


def extract_status(content: str) -> str:
    """Extract task status from content.

    Recognizes plain-text status words (case-insensitive, with or without a
    leading emoji/punctuation) on the Status line, plus the legacy emoji-only
    forms. Recognition is scoped to the Status line so prose mentions of
    'design'/'research' elsewhere do not misclassify the task.
    """
    line_match = _STATUS_LINE.search(content)
    if line_match:
        line = line_match.group(1)
        lowered = line.lower()
        for phrase, canonical in STATUS_WORDS:
            if re.search(r'\b' + re.escape(phrase) + r'\b', lowered):
                return canonical
        for emoji, canonical in STATUS_EMOJI.items():
            if emoji in line:
                return canonical

    # Legacy fallback for docs without a standard Status line: the exact
    # emoji+word combos the pre-TASK-67 extractor matched anywhere in content.
    legacy = [
        ('✅ Completed', 'completed'),
        ('🚧 In Progress', 'in-progress'),
        ('📋 Backlog', 'backlog'),
        ('🔬 Research', 'research'),
    ]
    for needle, canonical in legacy:
        if needle in content:
            return canonical
    return 'unknown'


def extract_title(content: str, filename: str) -> str:
    """Extract title from task content."""
    match = re.search(r'^#\s+[A-Z][A-Z0-9]*-\d+:\s*(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return filename.replace('.md', '').replace('-', ' ').title()


def extract_decisions(content: str) -> list:
    """Extract technical decisions from task document."""
    decisions = []

    # Look for Technical Decisions section
    decision_match = re.search(
        r'## Technical Decisions\s*\n(.*?)(?=\n##|\Z)',
        content,
        re.DOTALL
    )

    if not decision_match:
        return decisions

    decision_section = decision_match.group(1)

    # Parse table rows (skip header)
    rows = re.findall(r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|', decision_section)

    for row in rows:
        decision, options, chosen, reasoning = [col.strip() for col in row]
        # Skip the header row and the separator row. Separator cells are any
        # run of dashes/colons/spaces (e.g. `----------` or `:---:`) — an
        # exact-match list missed wide cells and ingested them as decisions
        # ("----------: -------- - -----------", see mem-038/mem-044).
        if decision.lower() == 'decision' or re.fullmatch(r'[-:\s]+', decision):
            continue
        if chosen and reasoning and len(reasoning) > 5:
            decisions.append({
                'decision': decision,
                'chosen': chosen,
                'reasoning': reasoning
            })

    return decisions


def add_task_to_graph(task_path: str, graph_path: str) -> dict:
    """Add a task document to the knowledge graph."""
    task_file = Path(task_path)
    if not task_file.exists():
        return {'error': f'Task file not found: {task_path}'}

    content = task_file.read_text()

    # Extract task ID from filename
    match = re.match(r'([A-Z][A-Z0-9]*-\d+)', task_file.name)  # TASK-12, GH-57 (GH-32)
    task_id = match.group(1) if match else task_file.stem

    # Load graph
    graph = load_graph(graph_path)

    # Extract metadata
    title = extract_title(content, task_file.name)
    status = extract_status(content)
    concepts = extract_concepts_from_task(content)

    # Create task node
    task_data = {
        'path': str(task_file),
        'title': title,
        'status': status,
        'concepts': concepts
    }

    graph = add_node(graph, 'tasks', task_id, task_data)

    # Add 'implements' edges only to concepts that exist as concept nodes
    # (referential integrity — keyword_map may yield a concept with no
    # canonical node, e.g. a fresh project that has not run a full build).
    # Without this filter every task edit re-introduces a dangling edge that
    # the wp6 repair then has to clean. The task is still indexed under every
    # concept via add_node, so query_by_concept still finds it.
    concept_nodes = graph.get('nodes', {}).get('concepts', {})
    for concept in concepts:
        if concept in concept_nodes:
            graph = add_edge(graph, task_id, concept, 'implements')

    # Extract and create decision memories (for completed tasks)
    memories_created = []
    if status == 'completed':
        decisions = extract_decisions(content)
        # Re-syncing a task must not duplicate its decision memories: the
        # TASK-54 sync ran twice and produced mem-044..049 as byte-identical
        # copies of mem-038..043. Skip any summary already in the graph.
        existing_summaries = {
            m.get('summary')
            for m in graph.get('nodes', {}).get('memories', {}).values()
            if m.get('type') == 'decision'
        }
        for decision in decisions:
            summary = f"{decision['decision']}: {decision['chosen']} - {decision['reasoning']}"
            if len(summary) > 200:
                summary = summary[:197] + '...'
            if summary in existing_summaries:
                continue
            existing_summaries.add(summary)

            try:
                memory_id = add_memory(
                    graph=graph,
                    memory_type='decision',
                    summary=summary,
                    concepts=concepts,
                    confidence=0.95,
                    source_task=task_id
                )
            except (OSError, FileExistsError, ValueError) as e:
                # add_memory is fail-loud since v6.17.0 (file written before
                # node). This runs inside the PostToolUse sync hook — skip the
                # memory rather than dying mid-sync.
                print(f"warning: skipped decision memory for {task_id}: {e}",
                      file=sys.stderr)
                continue
            memories_created.append(memory_id)

    # Save graph
    if save_graph(graph_path, graph):
        return {
            'task_id': task_id,
            'title': title,
            'status': status,
            'concepts': concepts,
            'memories_created': memories_created
        }

    return {'error': 'Failed to save graph'}


def sync_all_tasks(tasks_dir: str, graph_path: str) -> dict:
    """Sync all tasks from directory to graph."""
    tasks_path = Path(tasks_dir)
    results = {
        'synced': 0,
        'failed': 0,
        'tasks': []
    }

    for task_file in tasks_path.glob('TASK-*.md'):
        result = add_task_to_graph(str(task_file), graph_path)
        if 'error' in result:
            results['failed'] += 1
        else:
            results['synced'] += 1
            results['tasks'].append(result['task_id'])

    return results


def main():
    parser = argparse.ArgumentParser(description='Sync tasks with knowledge graph')
    parser.add_argument('--action', required=True,
                       choices=['add', 'sync-all'],
                       help='Action to perform')
    parser.add_argument('--task-path', help='Path to task file')
    parser.add_argument('--tasks-dir', default='.agent/tasks',
                       help='Directory containing tasks')
    parser.add_argument('--graph-path', default='.agent/knowledge/graph.json',
                       help='Path to knowledge graph')

    args = parser.parse_args()

    if args.action == 'add':
        if not args.task_path:
            print("Error: --task-path required for add", file=sys.stderr)
            sys.exit(1)

        result = add_task_to_graph(args.task_path, args.graph_path)
        if 'error' in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)

        print(f"Added task: {result['task_id']}")
        print(f"Title: {result['title']}")
        print(f"Status: {result['status']}")
        print(f"Concepts: {', '.join(result['concepts'])}")
        if result['memories_created']:
            print(f"Decisions extracted: {len(result['memories_created'])}")

    elif args.action == 'sync-all':
        result = sync_all_tasks(args.tasks_dir, args.graph_path)
        print(f"Synced {result['synced']} tasks")
        if result['failed'] > 0:
            print(f"Failed: {result['failed']}")


if __name__ == '__main__':
    main()
