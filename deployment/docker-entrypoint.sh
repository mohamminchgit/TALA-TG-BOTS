#!/usr/bin/env bash
set -euo pipefail

RUN_MODE="${RUN_MODE:-all}"

if [ "$RUN_MODE" = "engine" ]; then
	exec python main.py engine
elif [ "$RUN_MODE" = "agents" ]; then
	exec python main.py run
elif [ "$RUN_MODE" = "all" ]; then
	python main.py engine &
	ENGINE_PID=$!
	python main.py run &
	AGENTS_PID=$!

	terminate() {
		kill -TERM "$ENGINE_PID" "$AGENTS_PID" 2>/dev/null || true
	}

	trap terminate SIGTERM SIGINT

	wait -n || true
	terminate
	wait
else
	echo "Unknown RUN_MODE: $RUN_MODE"
	exit 1
fi

