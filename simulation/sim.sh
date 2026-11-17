#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
case "${1:-validate}" in
  validate)
    docker compose --profile manual config --quiet
    printf '%s\n' 'Alpha 1S simulation configuration validated; containers remain stopped.'
    ;;
  check|shell)
    if [[ "${ALPHA_SIM_ACCEPT_EULA:-N}" != Y ]]; then
      printf '%s\n' 'Review NVIDIA Isaac Sim terms, then set ALPHA_SIM_ACCEPT_EULA=Y.' >&2
      exit 2
    fi
    if [[ "${ALPHA_SIM_GPU_READY:-0}" != 1 ]]; then
      printf '%s\n' 'Schedule GPU access first; set ALPHA_SIM_GPU_READY=1 only when existing workloads permit it.' >&2
      exit 2
    fi
    if [[ "$1" == check ]]; then
      docker compose --profile manual run --rm isaac ./isaac-sim.compatibility_check.sh --/app/quitAfter=10 --no-window
    else
      docker compose --profile manual run --rm isaac -l
    fi
    ;;
  *) printf '%s\n' 'Usage: ./sim.sh [validate|check|shell]' >&2; exit 2 ;;
esac
