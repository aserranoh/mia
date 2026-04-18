#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Component:
	name: str
	command: list[str]
	cwd: Path
	process: subprocess.Popen[bytes] | None = None


def _repo_root() -> Path:
	# test/start_dev_components.py -> repository root
	return Path(__file__).resolve().parent.parent


def _start_component(component: Component) -> None:
	print(f"[start] {component.name}: {' '.join(component.command)}")
	component.process = subprocess.Popen(
		component.command,
		cwd=str(component.cwd),
		start_new_session=True,
	)
	print(f"[pid] {component.name}: {component.process.pid}")


def _is_running(component: Component) -> bool:
	if component.process is None:
		return False
	return component.process.poll() is None


def _stop_component(component: Component, timeout: float = 5.0) -> None:
	process = component.process
	if process is None:
		return

	if process.poll() is not None:
		print(f"[stop] {component.name}: already exited ({process.returncode})")
		return

	print(f"[stop] {component.name}: sending SIGTERM")
	try:
		os.killpg(process.pid, signal.SIGTERM)
	except ProcessLookupError:
		return

	try:
		process.wait(timeout=timeout)
		print(f"[stop] {component.name}: exited ({process.returncode})")
		return
	except subprocess.TimeoutExpired:
		pass

	print(f"[stop] {component.name}: timeout, sending SIGKILL")
	try:
		os.killpg(process.pid, signal.SIGKILL)
	except ProcessLookupError:
		return
	process.wait()
	print(f"[stop] {component.name}: killed ({process.returncode})")


def main() -> int:
	repo_root = _repo_root()
	face_binary = repo_root / "src" / "face" / "build" / "face"

	components = [
		Component(
			name="core",
			command=["uv", "run", "core", "--settings", "settings.json"],
			cwd=repo_root,
		),
		Component(
			name="face",
			command=[str(face_binary)],
			cwd=repo_root,
		),
		Component(
			name="nats",
			command=["nats-server"],
			cwd=repo_root,
		),
	]

	if not face_binary.exists():
		print(
			f"[error] face binary not found at: {face_binary}",
			file=sys.stderr,
		)
		return 1

	started: list[Component] = []
	try:
		for component in components:
			_start_component(component)
			started.append(component)

		print("[ready] all components started. Press Ctrl+C to stop.")
		while True:
			time.sleep(0.5)
			for component in started:
				if not _is_running(component):
					code = component.process.returncode if component.process else "?"
					print(
						f"[exit] {component.name} exited unexpectedly ({code}); stopping all...",
						file=sys.stderr,
					)
					return 1
	except KeyboardInterrupt:
		print("\n[signal] keyboard interrupt received. Shutting down...")
		return 0
	except FileNotFoundError as exc:
		print(f"[error] command not found: {exc}", file=sys.stderr)
		return 1
	finally:
		for component in reversed(started):
			_stop_component(component)


if __name__ == "__main__":
	raise SystemExit(main())
