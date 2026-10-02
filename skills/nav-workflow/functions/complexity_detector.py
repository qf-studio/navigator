"""nav-workflow complexity CLI (v8): thin entry point over hooks/nav_hook_lib/scoring.py."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "hooks" / "nav_hook_lib"))
from scoring import (  # noqa: E402,F401  (public names the nav-workflow skill and tests use)
    COMPLEXITY_SIGNALS, SIMPLICITY_SIGNALS, ComplexityResult, detect_complexity, detect_signals,
    get_recommendation, complexity_detector_main as main,
    calculate_signal_complexity as calculate_complexity,
)

if __name__ == "__main__":
    sys.exit(main())
