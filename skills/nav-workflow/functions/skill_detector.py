"""nav-workflow skill-match CLI (v8): thin entry point over hooks/nav_hook_lib/scoring.py."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "hooks" / "nav_hook_lib"))
from scoring import (  # noqa: E402,F401  (public names the nav-workflow skill and tests use)
    SKILL_TRIGGERS, SkillMatch, calculate_match_score, detect_skill_match,
    skill_detector_main as main,
)

if __name__ == "__main__":
    sys.exit(main())
