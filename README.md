# Daily Scheduler

A deterministic, priority-based task scheduler implemented in Python using a custom max-heap.

## 🚀 Features
- Custom max-heap implementation (no built-in heapq)
- Dependency-aware scheduling
- Deterministic execution order
- Priority scoring system

## 🧠 How it works
Tasks are scheduled based on:
- Priority score
- Duration
- Dependency completion

The scheduler ensures that:
- Tasks only run when dependencies are completed
- Higher priority tasks execute first
- Results are reproducible

## ▶️ How to run
```bash
python scheduler.py
