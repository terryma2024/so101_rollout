#!/usr/bin/env bash
# Anchor checkout launchers without depending on caller cwd or installed paths.
so101_init() {
  SO101_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P) || return
  cd -- "$SO101_ROOT" || return
  local selected=${SO101_CONFIG_DIR-"$SO101_ROOT/config"}
  if [[ ! -d "$selected" ]]; then
    printf 'Configuration directory does not exist: %s\n' "$selected" >&2
    return 1
  fi
  SO101_CONFIG_DIR=$(cd -- "$selected" && pwd -P) || return
  export SO101_CONFIG_DIR
}

so101_source_defaults() {
  local defaults_file=$1 line key
  local -A known=() saved=()
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^([a-zA-Z_][a-zA-Z_0-9]*)= ]]; then
      key=${BASH_REMATCH[1]}
      known["$key"]=1
      if [[ -v "$key" ]]; then
        saved["$key"]=${!key}
      fi
    fi
  done < "$defaults_file" || return
  source "$defaults_file" || return
  for key in "${!known[@]}"; do
    if [[ -v 'saved[$key]' ]]; then
      printf -v "$key" '%s' "${saved[$key]}"
    fi
    export "$key"
  done
}
