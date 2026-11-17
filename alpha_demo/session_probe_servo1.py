"""Compatibility entry point for the fixed servo-1 diagnostic."""
import sys
from .session_probe import main
if __name__ == '__main__':
    sys.argv.extend(['--servo-id','1'])
    raise SystemExit(main())
