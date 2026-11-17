import argparse
import json
from pathlib import Path
from .controller import Controller
from .diagnostics import collect
from .motions import MOTIONS


def main():
    parser = argparse.ArgumentParser(description='Alpha1 passive diagnostics and simulation')
    parser.add_argument('--diagnose', metavar='REPORT_JSON')
    parser.add_argument('--gemini', action='store_true', help='Send typed requests to Gemini')
    args = parser.parse_args()
    if args.diagnose:
        Path(args.diagnose).write_text(json.dumps(collect(), indent=2))
        print('Passive inspection saved. No device interfaces opened.')
        return
    controller = Controller()
    print('SIMULATION ONLY — hardware disabled. Commands: wave, idle, preview, cancel, quit.')
    if args.gemini:
        print('Other text is sent to Gemini. Review each proposal, then type preview.')
    try:
        while True:
            text = input('> ').strip()
            if text == 'quit':
                break
            try:
                if text == 'cancel':
                    controller.cancel()
                    print('Proposal cleared. This is not a physical emergency stop.')
                elif text == 'preview':
                    print('\n'.join(controller.preview()))
                else:
                    controller.cancel()
                    if text in MOTIONS:
                        motion = text
                    elif args.gemini:
                        from .gemini import propose
                        motion = propose(text)
                    else:
                        raise ValueError('Choose wave or idle, or enable --gemini')
                    p = controller.propose('propose_motion', {'motion': motion})
                    print(f'Proposed: {p.motion}. Type preview within 30 seconds to simulate once.')
            except (ValueError, ImportError) as exc:
                controller.cancel()
                print(f'Blocked: {exc}')
            except Exception as exc:
                controller.cancel()
                print(f'Request failed ({type(exc).__name__}); nothing queued.')
    except (EOFError, KeyboardInterrupt):
        controller.cancel()
        print('\nSimulation closed.')


if __name__ == '__main__':
    main()
