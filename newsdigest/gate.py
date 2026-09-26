"""Hourly check: is it time for the daily news update? Standard library only.

GitHub runs the workflow every hour. This decides whether this particular run
should do the work, based on the update time and update days in config.toml and
the date of the last update in state/state.json.

Usage in the workflow:  python3 -m newsdigest.gate >> "$GITHUB_OUTPUT"
Set FORCE=true to always run (the manual "Run workflow" button does this).
"""

import os
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

from .settings import DAY_NAMES, load_config, load_state


def parse_hhmm(text):
    hours, minutes = text.strip().split(":")
    return time(int(hours), int(minutes))


def should_send(cfg, state, now_utc, force=False):
    """Return (decision, reason)."""
    if force:
        return True, "manual run"
    sched = cfg["schedule"]
    local = now_utc.astimezone(ZoneInfo(sched["timezone"]))
    day = DAY_NAMES[local.weekday()]
    if day not in sched["update_days"]:
        return False, f"{day} is not an update day"
    update_at = parse_hhmm(sched["update_time"])
    if local.time() < update_at:
        return False, f"too early, it is {local:%H:%M} and the update time is {update_at:%H:%M}"
    if state.get("last_sent_local_date") == local.date().isoformat():
        return False, "already updated today"
    return True, f"update time {update_at:%H:%M} reached"


def main():
    from datetime import timezone

    force = os.environ.get("FORCE", "").lower() == "true"
    decision, reason = should_send(load_config(), load_state(), datetime.now(timezone.utc), force)
    print(f"Schedule check: {'RUN' if decision else 'skip'} ({reason})", file=sys.stderr)
    print(f"run={'true' if decision else 'false'}")


if __name__ == "__main__":
    main()
