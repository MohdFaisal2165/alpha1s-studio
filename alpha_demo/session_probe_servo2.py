"""Compatibility entry point for the fixed servo-2 diagnostic."""
import sys
from .session_probe import main
if __name__ == '__main__':
    sys.argv.extend(['--servo-id','2'])
    raise SystemExit(main())
