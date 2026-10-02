"""S2 — Stop forced continuation: continue:true vs decision:block, with fuse.

Run A (fresh session): variant continue:true; expect one continuation carrying
the sentinel, then the run-twice subtest (same session, second prompt) must
produce ZERO further continuations (fuse consumed, mem-037).
Run B (fresh session, fresh fuse): variant decision:block — the routing-matrix
fallback — probed for comparison evidence.

Both variants count as ONE probe run. The top-level "pass" tracks
continue:true specifically; when it is false but decision_block_works is
true, the channel verdict is "decision:block is the forced-continuation
mechanism" (observed CC 2.1.205, mem-051) — record that outcome, don't
weaken this criterion.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (STATE, arm, disarm, clear_log, read_log, preflight,
                    run_claude, find_transcripts, scan_jsonl, make_sentinel,
                    write_verdict)

preflight()
results = {}

for variant in ("continue", "block"):
    clear_log("s2")
    fuse = STATE / "fuse-s2"
    if fuse.exists():
        fuse.unlink()
    sentinel = make_sentinel(f"2{variant[0].upper()}")
    arm("s2", {"sentinel": sentinel, "variant": variant})
    try:
        r1 = run_claude("Say the word hello and nothing else.")
        fuse_after_r1 = fuse.exists()
        # Run-twice subtest in the SAME session: fuse present => no continuation.
        r2 = run_claude("Say the word goodbye and nothing else.",
                        resume=r1["session_id"]) if r1["session_id"] else None
    finally:
        disarm("s2")

    log = read_log("s2")
    transcripts = find_transcripts(session_id=r1["session_id"], since=r1["started"])
    occurrences = []
    for t in transcripts:
        occurrences += scan_jsonl(t, sentinel)
    echoed = sentinel in r1["result_text"] or any(
        o["role"] == "assistant" for o in occurrences)
    # Delivery-based evidence (CC 2.1.287): the hook reason reached the transcript in a
    # non-assistant position AND the session took a second model turn, even if the model
    # declines to repeat the code.
    delivered = any(o["role"] != "assistant" for o in occurrences)
    num_turns = (r1["parsed"] or {}).get("num_turns") or 0
    continued = echoed or (delivered and num_turns >= 2)
    second_run_events = [e["event"] for e in log
                         if e.get("event") in ("fuse-present-silent-exit",
                                               "stop_hook_active-short-circuit")]
    r2_clean = bool(r2) and sentinel not in (r2["result_text"] or "")

    results[variant] = {
        "sentinel": sentinel,
        "continuation_happened": continued,
        "sentinel_echoed": echoed,
        "reason_delivered": delivered,
        "fuse_consumed": fuse_after_r1,
        "run_twice_no_continuation": r2_clean,
        "second_run_hook_events": second_run_events,
        "occurrences": occurrences,
        "r1_result": r1["result_text"][:300],
        "r2_result": (r2 or {}).get("result_text", "")[:300],
        "r1_num_turns": (r1["parsed"] or {}).get("num_turns"),
        "hook_log": log,
        "transcripts": [str(t) for t in transcripts],
    }

write_verdict("s2", {
    "channel": "Stop continue:true (variant A) vs decision:block (variant B)",
    "variants": results,
    "continue_true_works": results["continue"]["continuation_happened"],
    "decision_block_works": results["block"]["continuation_happened"],
    "pass": bool(results["continue"]["continuation_happened"]
                 and results["continue"]["fuse_consumed"]
                 and results["continue"]["run_twice_no_continuation"]),
})
