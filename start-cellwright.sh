#!/bin/sh
# SPDX-License-Identifier: EUPL-1.2
set -eu
cd -- "$(dirname -- "$0")"
if [ -x ./cellwright ]; then binary=./cellwright; else binary=./target/release/cellwright; fi
exec "$binary" serve --open --data "${XDG_DATA_HOME:-$HOME/.local/share}/cellwright/workspace"
