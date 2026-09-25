"""Hourly check: is it time to send a digest? Standard library only.

GitHub runs the workflow every hour. This decides whether this particular run
should do the work, based on the send time and send days in config.toml and
the date of the last digest in state/state.json.

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
    if day not in sched["send_days"]:
        return False, f"{day} is not a send day"
    send_at = parse_hhmm(sched["send_time"])
    if local.time() < send_at:
        return False, f"too early, it is {local:%H:%M} and send time is {send_at:%H:%M}"
    if state.get("last_sent_local_date") == local.date().isoformat():
        return False, "already sent today"
    return True, f"send time {send_at:%H:%M} reached"


def main():
    from datetime import timezone

    force = os.environ.get("FORCE", "").lower() == "true"
    decision, reason = should_send(load_config(), load_state(), datetime.now(timezone.utc), force)
    print(f"Schedule check: {'RUN' if decision else 'skip'} ({reason})", file=sys.stderr)
    print(f"run={'true' if decision else 'false'}")


if __name__ == "__main__":
    main()
