"""Conservative CPU-based defaults for Ollama thread pool sizing."""

from __future__ import annotations

import os


def available_cpu_count() -> int:
    """Logical CPUs visible to this process (cgroup-aware on Linux)."""
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def default_ollama_num_threads() -> int:
    """Conservative llama.cpp thread count: ~half cores, leave headroom, cap at 8."""
    cpus = available_cpu_count()
    if cpus <= 2:
        return 1
    return max(1, min(cpus // 2, cpus - 1, 8))


if __name__ == "__main__":
    print(default_ollama_num_threads())
