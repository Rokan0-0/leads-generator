#!/usr/bin/env python3
"""LeadPulse NG - Automated High-Ticket Lead & Bio-Link Auditor."""
import sys

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from leadpulse.cli import main

if __name__ == "__main__":
    main()

