#!/bin/sh
printf '\033c\033]0;%s\a' GlassesAR
base_path="$(dirname "$(realpath "$0")")"
"$base_path/GlassesAR.arm64" "$@"
