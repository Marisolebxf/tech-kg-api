#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend_dir="$(dirname "${bundle_dir}")"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  python_bin="${PYTHON_BIN}"
elif [[ -x "${backend_dir}/.venv/bin/python" ]]; then
  python_bin="${backend_dir}/.venv/bin/python"
else
  python_bin="python3"
fi
exec "${python_bin}" "${bundle_dir}/run_etl.py" "$@"
