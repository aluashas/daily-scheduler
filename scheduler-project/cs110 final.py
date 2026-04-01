# Generated from: cs110 final.ipynb
# Converted at: 2026-04-01T14:10:27.406Z
# Next step (optional): refactor into modules & generate tests with RunCell
# Quick start: pip install runcell

class MaxHeapq:
    """
    Small max-heap specialized for Task objects.
    Design choice:
    - I implement the heap mechanics explicitly (parent/left/right, bubble-up, heapify) instead of using heapq so that the scheduling logic is transparent and inspectable.
    - This also makes tie-breaking behavior explicit and deterministic, which is important for reproducibility and fair comparison across experiments.
    """

    def __init__(self):
        # internal array representation of the heap
        self.heap = []

    def left(self, i):
        """
        Return the index of the left child of node i, or None if it doesn't exist.
        """
        idx = 2*i + 1
        return idx if idx < len(self.heap) else None

    def right(self, i):
        """
        Return the index of the right child of node i, or None if it doesn't exist.
        """
        idx = 2*i + 2
        return idx if idx < len(self.heap) else None

    def parent(self, i):
        """
        Return the index of the parent of node i, or None if i is the root.
        """
        if i <= 0 or i >= len(self.heap):
            return None
        return (i - 1) // 2

    def _key(self, t):
        """
        Deterministic ordering:
        1) higher priority first,
        2) shorter duration is preferred (secondary optimization),
        3) then lower id as a tie-breaker.

        Using a total ordering guarantees deterministic behavior and ensures that scheduling results do not depend on input order.
        """
        return (t.priority, -t.duration, -t.id)

    def _dominates(self, i, j):
        """
        Return True if heap[i] should be ordered above heap[j] according to the priority key.
        """
        return self._key(self.heap[i]) > self._key(self.heap[j])

    def heappush(self, task):
        """
        Insert a new task into the heap while maintaining the heap invariant

        Complexity: O(log n)
        """
        self.heap.append(task)
        i = len(self.heap) - 1
        p = self.parent(i)
        #bubble up until heap property is restored
        while p is not None and self._dominates(i, p):
            self.heap[i], self.heap[p] = self.heap[p], self.heap[i]
            i = p
            p = self.parent(i)

    def heapify(self, i):
        """
        Restore heap property downward from index i.

        This is used after removing the root element.
        Complexity: O(log n)
        """
        while True:
            L = self.left(i)
            R = self.right(i)
            best = i
            if L is not None and self._dominates(L, best):
                best = L
            if R is not None and self._dominates(R, best):
                best = R
            if best == i:
                break
            self.heap[i], self.heap[best] = self.heap[best], self.heap[i]
            i = best

    def heappop(self):
        """
        Remove and return the current max, highest-priority task (root).

        Returns: task or None if the heap is empty.

        Complexity: O(log n)
        """
        if len(self.heap) == 0:
            return None

        #Swap root with the last element and remove it.
        self.heap[0], self.heap[-1] = self.heap[-1], self.heap[0]
        top = self.heap.pop()

        #Restore the heap property if elements remain.
        if len(self.heap) > 0:
            self.heapify(0)
        return top

    def __len__(self):
        """
        Return the number of elements currently stored in the heap.
        """
        return len(self.heap)


class Task:
    """
    Minimal task representation used by the scheduler.

    Attributes:
    - id: unique identifier (used for the deterministic tie-breaking)
    - description: human readable task descriptions
    - duration: time required for the task in minutes
    - dependencies: list of task IDs that must be completed first
    - type: used to encode preferencing (city-centered or not)
    - status: tracks tasks progress during the scheduling
    - multi-tasking: an attribute that is not in code, but sees if a task CAN and SHOULD be multitasked.
    """

    def __init__(self, task_id, description, duration, dependencies=None, task_type="regular"):
        self.id = task_id
        self.description = description
        self.duration = duration
        self.dependencies = dependencies if dependencies else []
        self.type = task_type
        self.status = "not_yet_started"
        self.priority = 0  # The priority is computed dynamically when the task becomes eligible.

    def __repr__(self):
        return f"Task({self.id}, '{self.description}', prio={self.priority}, status={self.status})"


class MyScheduler:
    """
    Priority-driven daily scheduler using a single max-heap

    This scheduler has some core assumptions:
    - tasks are not taken in advance
    - only tasks whose dependencies are completed can be scheduled
    - scheduling decisions are made incrementally as tasks complete
    - determinism > raw performance
    """

    def __init__(self, tasks, init_time=8*60, final_time=None):
        self.tasks = tasks
        self.by_id = {t.id: t for t in tasks} # O(1) per lookups
        self.init_time = init_time
        self.final_time = final_time
        self.current_time = init_time
        self.completed_tasks = []
        self.utility_sum = 0
        self._enqueued_ids = set() # avoids duplicate heap insertions

    def compute_priority(self, task):
        """
        Simple scoring:
        
        base 100
        - 10 * number of dependencies  
        - 0.1 * duration_minutes      
        + 15 if city-centered

        Why:

        - dependencies penalize rigidity in the schedule
        - duration introduces a slight bias toward quicker tasks
        - city-centered tasks reflect experiential preference
        """
        score = 100
        score -= 10 * len(task.dependencies)
        score -= int(0.1 * task.duration)
        if task.type == "city-centered":
            score += 15
        return score

    def format_time(self, minutes):
        # Converts time in minutes to a readable hour-minute string
        h = int(minutes // 60)
        m = int(minutes % 60)
        return f"{h}h{m:02d}"

    def _deps_done(self, task):
        """Return True if all dependencies of a task have been completed."""
        for dep_id in task.dependencies:
            if self.by_id[dep_id].status != "completed":
                return False
        return True

    def _try_enqueue(self, pq, task):
        """
        Add a task to the priority queue if:
        - it has not been started
        - it has not already been enqueued
        - all its dependencies are satisfied
        """
        if task.status == "not_yet_started" and task.id not in self._enqueued_ids and self._deps_done(task):
            task.priority = self.compute_priority(task)
            pq.heappush(task)
            self._enqueued_ids.add(task.id)

    def run(self, verbose=True):
        """
        Execute the scheduling loop:

        Algorithm:
        1) Initialize the heap with all dependency-free tasks
        2) Repeatedly select the highest-priority task
        3) Execute it non-preemptively
        4) Update time, status, and newly available tasks
        """
        pq = MaxHeapq()

        #initial seeding of ready tasks
        for task in self.tasks:
            self._try_enqueue(pq, task)

        while len(pq) > 0:
            current_task = pq.heappop()
            #defensive check (shouldn't trigger)
            if current_task.status == "completed":
                continue 

            start_time = self.current_time
            current_task.status = "in_progress"
            if verbose:
                print(f"t={self.format_time(start_time)}, started '{current_task.description}'")

            #non-preemtive execution
            end_time = start_time + current_task.duration
            self.current_time = end_time
            current_task.status = "completed"
            
            self.completed_tasks.append(current_task)
            self.utility_sum += current_task.priority

            if verbose:
                print(f"t={self.format_time(end_time)}, completed '{current_task.description}', priority={current_task.priority}")

            # check if new tasks have become eligible
            for t in self.tasks:
                self._try_enqueue(pq, t)

            if self.final_time is not None and self.current_time >= self.final_time:
                if verbose:
                    print("Final time reached.")
                break

        total_time = self.current_time - self.init_time
        h = total_time // 60
        m = total_time % 60
        if verbose:
            print(f"\nCompleted {len(self.completed_tasks)} of {len(self.tasks)} tasks "
                  f"in {total_time} minutes ({int(h)}h{int(m):02d}).")
            print(f"Total utility value: {self.utility_sum}")

        return self.completed_tasks


# TASKS
# Durations and dependencies reflect my latest table exactly.

task_0  = Task(0,  "Get up and dress",                    30,  [],                "regular")
task_1  = Task(1,  "Brush my teeth",                      10,  [0],              "regular")
task_2  = Task(2,  "Do my makeup",                        60,  [0, 1],           "regular")
task_3  = Task(3,  "Eat a quick breakfast at the buffet", 40,  [0, 1],           "regular")
task_4  = Task(4,  "Take a walk around the property",     60,  [0, 1, 2, 3],     "city-centered")
task_5  = Task(5,  "Visit the TSUNAMI memorial tour",     90,  [4],              "city-centered")
task_6  = Task(6,  "Have our BBQ lunch",                  30,  [5],              "city-centered")
task_7  = Task(7,  "Work on my assignment",               120, [2],              "city-centered")  
task_8  = Task(8,  "Have fun with my friends at Kamaishi",120, [3],              "city-centered")
task_9  = Task(9,  "Have dinner at the hotel with the friends", 75, [8],         "regular")
task_10 = Task(10, "Take an onsen bath",                  60,  [9],              "regular")

my_tasks = [task_0, task_1, task_2, task_3, task_4, task_5, task_6, task_7, task_8, task_9, task_10]

# Running
if __name__ == "__main__":
    print("="*70)
    print("MY DAILY SCHEDULE IN KAMAISHI (updated dependencies/types)")
    print("="*70 + "\n")
    scheduler = MyScheduler(my_tasks, init_time=8*60, final_time=None)
    scheduler.run(verbose=True)

    # Minimal asserts (quiet) to keep things stable
    def create_fresh_tasks():
        return [
            Task(0, "Get up and dress", 30, []),
            Task(1, "Brush my teeth", 10, [0]),
            Task(2, "Do my makeup", 60, [0, 1]),
            Task(3, "Eat a quick breakfast at the buffet", 40, [0, 1]),
            Task(4, "Take a walk around the property", 60, [0, 1, 2, 3], "city-centered"),
            Task(5, "Visit the TSUNAMI memorial tour", 90, [4], "city-centered"),
            Task(6, "Have our BBQ lunch", 30, [5], "city-centered"),
            Task(7, "Work on my assignment", 120, [2], "city-centered"),
            Task(8, "Have fun with my friends at Kamaishi", 120, [3], "city-centered"),
            Task(9, "Have dinner at the hotel with the friends", 75, [8], "regular"),
            Task(10,"Take an onsen bath", 60, [9], "regular"),
        ]

    # Order independence: reversed input should yield same execution order
    t1 = create_fresh_tasks()
    s1 = MyScheduler(t1, init_time=8*60)
    s1.run(verbose=False)
    order1 = [t.id for t in s1.completed_tasks]

    t2 = list(reversed(create_fresh_tasks()))
    s2 = MyScheduler(t2, init_time=8*60)
    s2.run(verbose=False)
    order2 = [t.id for t in s2.completed_tasks]

    assert order1 == order2, "Execution order should not depend on input order."

    # Deterministic tie-break: two identical ready tasks -> lower id first
    a = Task(100, "Tie A", 30, [])
    b = Task(101, "Tie B", 30, [])
    st = MyScheduler([b, a], init_time=8*60)
    st.run(verbose=False)
    exec_ids = [t.id for t in st.completed_tasks]
    assert exec_ids[0] == 100, "Lower ID should win when priorities are equal."

    # Empty schedule edge case
    se = MyScheduler([], init_time=8*60)
    out = se.run(verbose=False)
    assert len(out) == 0, "Empty schedule should complete zero tasks."
    

# CS110 Final Project — Priority Scheduling with Greedy, DP, and Data Visualization
# -----------------------------------------------------------------------------
# This file intentionally preserves the original greedy + max-heap structure
# and layers Dynamic Programming (DP), testing, and quantitative scaling
# analysis on top, in accordance with the CS110 course guide.
#
# Key goals:
# 1) Demonstrate a correct, deterministic greedy scheduler using a heap
# 2) Compare it against a DP scheduler with guaranteed optimality
# 3) Support claims with runtime scaling experiments and plots
# 4) Avoid overclaiming: emphasize tradeoffs, variance, and limits
# -----------------------------------------------------------------------------

import time
import math
import random
from typing import List, Dict, Tuple, Set
import numpy as np
import matplotlib.pyplot as plt

# =============================================================================
# MAX HEAP IMPLEMENTATION (PRIORITY QUEUE)
# =============================================================================



class MaxHeapq:
    """
    Max-heap specialized for Task objects.

    Why a heap?
    - O(log n) insertion when tasks become ready
    - O(log n) extraction of highest-utility task
    - No need for full sorting or random access
    - Matches incremental scheduling perfectly
    """

    def __init__(self):
        self.heap = []

    def _key(self, task):
        """
        Deterministic ordering:
        1) higher utility first
        2) shorter duration preferred
        3) lower ID as final tie-break
        """
        return (task.priority, -task.duration, -task.id)

    def _dominates(self, i, j):
        return self._key(self.heap[i]) > self._key(self.heap[j])

    def _parent(self, i):
        return (i - 1) // 2 if i > 0 else None

    def _left(self, i):
        idx = 2 * i + 1
        return idx if idx < len(self.heap) else None

    def _right(self, i):
        idx = 2 * i + 2
        return idx if idx < len(self.heap) else None

    def push(self, task):
        self.heap.append(task)
        i = len(self.heap) - 1
        p = self._parent(i)
        while p is not None and self._dominates(i, p):
            self.heap[i], self.heap[p] = self.heap[p], self.heap[i]
            i = p
            p = self._parent(i)

    def pop(self):
        if not self.heap:
            return None
        self.heap[0], self.heap[-1] = self.heap[-1], self.heap[0]
        top = self.heap.pop()
        if self.heap:
            self._heapify(0)
        return top

    def _heapify(self, i):
        while True:
            best = i
            L, R = self._left(i), self._right(i)
            if L is not None and self._dominates(L, best):
                best = L
            if R is not None and self._dominates(R, best):
                best = R
            if best == i:
                break
            self.heap[i], self.heap[best] = self.heap[best], self.heap[i]
            i = best

    def __len__(self):
        return len(self.heap)

# =============================================================================
# TASK DEFINITION
# =============================================================================

class Task:
    """
    Task abstraction consistent with the CS110 specification.
    """
    def __init__(self, task_id, duration, dependencies=None, task_type="regular"):
        self.id = task_id
        self.duration = duration
        self.dependencies = dependencies if dependencies else []
        self.type = task_type
        self.status = "not_started"
        self.priority = 0

    def copy(self):
        t = Task(self.id, self.duration, self.dependencies.copy(), self.type)
        t.status = self.status
        t.priority = self.priority
        return t

# =============================================================================
# GREEDY SCHEDULER
# =============================================================================

class GreedyScheduler:
    """
    Priority-driven greedy scheduler using a max-heap.

    Utility function (shared with DP):
    priority = 100 - 10 * |dependencies| - 0.1 * duration + 15 * city_bonus
    """

    def __init__(self, tasks: List[Task]):
        self.tasks = tasks
        self.by_id = {t.id: t for t in tasks}
        self.completed = []
        self.utility_sum = 0
        self.enqueued = set()

    def compute_priority(self, task: Task) -> float:
        score = 100
        score -= 10 * len(task.dependencies)
        score -= 0.1 * task.duration
        if task.type == "city-centered":
            score += 15
        return score

    def _deps_done(self, task: Task) -> bool:
        return all(self.by_id[d].status == "completed" for d in task.dependencies)

    def run(self) -> Tuple[List[int], float]:
        pq = MaxHeapq()

        for t in self.tasks:
            if not t.dependencies:
                t.priority = self.compute_priority(t)
                pq.push(t)
                self.enqueued.add(t.id)

        while len(pq) > 0:
            task = pq.pop()
            if task.status == "completed":
                continue
            task.status = "completed"
            self.completed.append(task.id)
            self.utility_sum += task.priority

            for t in self.tasks:
                if t.id not in self.enqueued and self._deps_done(t):
                    t.priority = self.compute_priority(t)
                    pq.push(t)
                    self.enqueued.add(t.id)

        return self.completed, self.utility_sum

# =============================================================================
# DYNAMIC PROGRAMMING SCHEDULER (TOP-DOWN)
# =============================================================================

class DPScheduler:
    """
    Top-down DP scheduler with memoization.

    State: frozenset(completed_task_ids)
    Goal: maximize total utility
    """

    def __init__(self, tasks: List[Task]):
        self.tasks = tasks
        self.by_id = {t.id: t for t in tasks}
        self.memo = {}
        self.states_explored = 0

    def compute_priority(self, task: Task) -> float:
        score = 100
        score -= 10 * len(task.dependencies)
        score -= 0.1 * task.duration
        if task.type == "city-centered":
            score += 15
        return score

    def _can_run(self, task: Task, completed: Set[int]) -> bool:
        return all(d in completed for d in task.dependencies)

    def _solve(self, completed: frozenset) -> Tuple[float, List[int]]:
        self.states_explored += 1
        if len(completed) == len(self.tasks):
            return 0, []
        if completed in self.memo:
            return self.memo[completed]

        best_u, best_order = 0, []
        for t in self.tasks:
            if t.id in completed:
                continue
            if not self._can_run(t, completed):
                continue
            u = self.compute_priority(t)
            future_u, future_order = self._solve(completed | {t.id})
            if u + future_u > best_u:
                best_u = u + future_u
                best_order = [t.id] + future_order

        self.memo[completed] = (best_u, best_order)
        return best_u, best_order

    def run(self) -> Tuple[List[int], float]:
        utility, order = self._solve(frozenset())
        return order, utility

# =============================================================================
# RANDOM TASK GENERATION (DAG)
# =============================================================================

def generate_tasks(n: int, seed=0) -> List[Task]:
    random.seed(seed)
    tasks = []
    for i in range(n):
        deps = random.sample(range(i), random.randint(0, min(2, i)))
        ttype = "city-centered" if random.random() < 0.3 else "regular"
        tasks.append(Task(i, random.randint(20, 90), deps, ttype))
    return tasks

# =============================================================================
# SCALING EXPERIMENTS
# =============================================================================

def measure_scaling(ns: List[int], trials=5):
    results = {"greedy": [], "dp": []}

    for n in ns:
        g_times, d_times = [], []
        for trial in range(trials):
            tasks = generate_tasks(n, seed=trial)

            g_tasks = [t.copy() for t in tasks]
            start = time.time()
            GreedyScheduler(g_tasks).run()
            g_times.append(time.time() - start)

            if n <= 14:
                d_tasks = [t.copy() for t in tasks]
                start = time.time()
                DPScheduler(d_tasks).run()
                d_times.append(time.time() - start)

        results["greedy"].append((n, np.mean(g_times), np.std(g_times)))
        if d_times:
            results["dp"].append((n, np.mean(d_times), np.std(d_times)))

    return results

# =============================================================================
# DATA VISUALIZATION
# =============================================================================

def plot_scaling(results):
    plt.figure(figsize=(8, 6))

    g_n, g_mean, g_std = zip(*results["greedy"])
    plt.errorbar(g_n, g_mean, yerr=g_std, label="Greedy (mean ± std)", marker='o')

    if results["dp"]:
        d_n, d_mean, d_std = zip(*results["dp"])
        plt.errorbar(d_n, d_mean, yerr=d_std, label="DP (mean ± std)", marker='s')

    plt.yscale("log")
    plt.xlabel("Number of tasks (n)")
    plt.ylabel("Runtime (seconds, log scale)")
    plt.title("Runtime Scaling of Scheduling Algorithms")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    plt.tight_layout()
    plt.show()

# =============================================================================
# TESTS
# =============================================================================

def run_tests():
    # Determinism test
    tasks1 = generate_tasks(8, seed=1)
    tasks2 = generate_tasks(8, seed=1)
    o1, u1 = GreedyScheduler([t.copy() for t in tasks1]).run()
    o2, u2 = GreedyScheduler([t.copy() for t in tasks2]).run()
    assert o1 == o2 and abs(u1 - u2) < 1e-6

    # DP optimality dominance
    g_order, g_u = GreedyScheduler([t.copy() for t in tasks1]).run()
    d_order, d_u = DPScheduler([t.copy() for t in tasks1]).run()
    assert d_u >= g_u

    print("All tests passed.")

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    run_tests()
    ns = [5, 8, 10, 12, 14, 16, 20]
    results = measure_scaling(ns, trials=7)
    plot_scaling(results)


import time
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Dict
import random


class Task:
    # Simple task object to hold all info we care about
    def __init__(self, task_id, duration, dependencies=None, task_type="regular"):
        self.id = task_id                  # unique ID for the task
        self.duration = duration           # how long the task takes
        self.dependencies = dependencies if dependencies else []  # tasks that must finish first
        self.type = task_type              # e.g., "city-centered" vs "regular"
        self.status = "not_yet_started"    # used by the greedy scheduler
        self.priority = 0                  # cached priority score
    
    def copy(self):
        # Shallow copy helper so each experiment run has fresh task objects
        t = Task(self.id, self.duration, self.dependencies.copy(), self.type)
        t.status = self.status
        t.priority = self.priority
        return t


def generate_random_tasks(n: int, avg_deps: int = 2, seed: int = 42) -> List[Task]:
    """
    Generate a list of n random tasks with a valid DAG of dependencies.
    Lower indices can be dependencies of higher indices, but not the other way around.
    """
    random.seed(seed)
    tasks = []
    
    for i in range(n):
        # Random duration between 20 and 90 "minutes" (or arbitrary time units)
        duration = random.randint(20, 90)
        
        # Only allow dependencies on earlier tasks, so we stay acyclic
        max_deps = min(i, max(0, avg_deps + random.randint(-1, 2)))
        
        if i > 0 and max_deps > 0:
            num_deps = random.randint(0, max_deps)
            deps = random.sample(range(i), num_deps)
        else:
            deps = []
        
        # Randomly flag some tasks as "city-centered" to affect priority
        task_type = "city-centered" if random.random() < 0.3 else "regular"
        tasks.append(Task(i, duration, deps, task_type))
    
    return tasks


class MaxHeapq:
    """
    Very lightweight max-heap just for prioritizing tasks.
    Using (priority, -duration, -id) so higher priority and shorter tasks bubble up.
    """
    def __init__(self):
        self.heap = []
    
    def _key(self, t):
        # Higher priority first; if tie, shorter duration; if tie, smaller id
        return (t.priority, -t.duration, -t.id)
    
    def _dominates(self, i, j):
        # Returns True if heap[i] should be above heap[j]
        return self._key(self.heap[i]) > self._key(self.heap[j])
    
    def _parent(self, i):
        if i <= 0:
            return None
        return (i - 1) // 2
    
    def _left(self, i):
        idx = 2 * i + 1
        return idx if idx < len(self.heap) else None
    
    def _right(self, i):
        idx = 2 * i + 2
        return idx if idx < len(self.heap) else None
    
    def push(self, task):
        # Standard heap push: add to end then bubble up
        self.heap.append(task)
        i = len(self.heap) - 1
        p = self._parent(i)
        while p is not None and self._dominates(i, p):
            self.heap[i], self.heap[p] = self.heap[p], self.heap[i]
            i = p
            p = self._parent(i)
    
    def pop(self):
        # Pop the max element (root) and re-heapify
        if len(self.heap) == 0:
            return None
        self.heap[0], self.heap[-1] = self.heap[-1], self.heap[0]
        top = self.heap.pop()
        if len(self.heap) > 0:
            self._heapify(0)
        return top
    
    def _heapify(self, i):
        # Push an element down until the heap property is restored
        while True:
            L = self._left(i)
            R = self._right(i)
            best = i
            if L is not None and self._dominates(L, best):
                best = L
            if R is not None and self._dominates(R, best):
                best = R
            if best == i:
                break
            self.heap[i], self.heap[best] = self.heap[best], self.heap[i]
            i = best
    
    def __len__(self):
        return len(self.heap)


class UnconstrainedGreedyScheduler:
    """
    Greedy scheduler with no time limit.
    Always finishes all tasks and chooses the next "best" ready task by priority.
    """
    def __init__(self, tasks):
        self.tasks = tasks
        self.by_id = {t.id: t for t in tasks}  # quick lookup by id
        self.completed_tasks = []
        self.utility_sum = 0                   # sum of priorities of executed tasks
        self._enqueued_ids = set()             # to avoid pushing same task multiple times
    
    def compute_priority(self, task):
        """
        Simple scoring function:
        - Base score 100
        - Penalty for more dependencies and longer duration
        - Bonus if task is "city-centered"
        """
        score = 100
        score -= 10 * len(task.dependencies)
        score -= 0.1 * task.duration
        if task.type == "city-centered":
            score += 15
        return score
    
    def _deps_done(self, task):
        # A task is ready if all its dependencies are completed
        return all(self.by_id[dep_id].status == "completed" 
                   for dep_id in task.dependencies)
    
    def _try_enqueue(self, pq, task):
        # Only enqueue tasks that haven't been started and whose deps are done
        if (task.status == "not_yet_started" and 
            task.id not in self._enqueued_ids and 
            self._deps_done(task)):
            task.priority = self.compute_priority(task)
            pq.push(task)
            self._enqueued_ids.add(task.id)
    
    def run(self, verbose=False):
        """
        Run the greedy algorithm until every task is completed.
        Returns:
            completed_tasks, total_utility, number_of_heap_operations
        """
        pq = MaxHeapq()
        operations = 0  # rough count of heap operations
        
        # Initial phase: push all tasks that are ready at the start
        for task in self.tasks:
            self._try_enqueue(pq, task)
            operations += 1
        
        # Main loop: always pick the highest-priority ready task
        while len(pq) > 0:
            current_task = pq.pop()
            operations += 1
            
            if current_task.status == "completed":
                # Can happen if same task was already processed earlier
                continue
            
            current_task.status = "completed"
            self.completed_tasks.append(current_task)
            self.utility_sum += current_task.priority
            
            # After finishing a task, some tasks might become ready
            for t in self.tasks:
                before_len = len(pq.heap)
                self._try_enqueue(pq, t)
                if len(pq.heap) > before_len:
                    operations += 1
        
        if verbose:
            print(f"Greedy: Completed {len(self.completed_tasks)}/{len(self.tasks)} tasks")
            print(f"        Utility: {self.utility_sum:.2f}")
            print(f"        Operations: {operations}")
        
        return self.completed_tasks, self.utility_sum, operations


class UnconstrainedDPScheduler:
    """
    Exhaustive DP over subsets of tasks (2^n states).
    State = set of completed task IDs; transition = choose any ready task to add.
    """
    def __init__(self, tasks):
        self.tasks = tasks
        self.by_id = {t.id: t for t in tasks}
        self.memo = {}              # memo[state] = (best_utility, best_order_from_here)
        self.states_explored = 0    # just to see how big the search space is
    
    def compute_priority(self, task):
        # Same scoring as greedy so we can compare apples to apples
        score = 100
        score -= 10 * len(task.dependencies)
        score -= 0.1 * task.duration
        if task.type == "city-centered":
            score += 15
        return score
    
    def _can_schedule(self, task, completed_ids):
        # Task is schedulable if all its dependencies are already in completed_ids
        return all(dep_id in completed_ids for dep_id in task.dependencies)
    
    def _solve(self, completed_ids):
        """
        Recursive DP:
        - completed_ids is a frozenset of tasks done so far
        - returns (best_future_utility, best_future_order) from this state onward
        """
        self.states_explored += 1
        
        # Base case: all tasks are done, nothing more to gain
        if len(completed_ids) == len(self.tasks):
            return (0, [])
        
        # If we've already solved this subset, reuse the result
        if completed_ids in self.memo:
            return self.memo[completed_ids]
        
        best_utility = 0
        best_order = []
        
        # Try scheduling each ready task next
        for task in self.tasks:
            if task.id in completed_ids:
                continue
            if not self._can_schedule(task, completed_ids):
                continue
            
            task_priority = self.compute_priority(task)
            new_completed = frozenset(completed_ids | {task.id})
            
            # Recursively solve the rest of the tasks
            future_utility, future_order = self._solve(new_completed)
            total_utility = task_priority + future_utility
            
            if total_utility > best_utility:
                best_utility = total_utility
                best_order = [task.id] + future_order
        
        # Cache result for this subset
        self.memo[completed_ids] = (best_utility, best_order)
        return (best_utility, best_order)
    
    def run(self, verbose=False):
        """
        Kick off the DP from the empty set of completed tasks.
        Returns:
            completed_tasks_in_optimal_order, max_utility, states_explored
        """
        self.states_explored = 0
        max_utility, optimal_order = self._solve(frozenset())
        
        completed_tasks = [self.by_id[tid] for tid in optimal_order]
        
        if verbose:
            print(f"DP:     Completed {len(completed_tasks)}/{len(self.tasks)} tasks")
            print(f"        Utility: {max_utility:.2f}")
            print(f"        States explored: {self.states_explored}")
        
        return completed_tasks, max_utility, self.states_explored


def measure_unconstrained_scaling(n_values: List[int], trials: int = 5) -> Dict:
    """
    For each n in n_values, run several trials and measure:
    - Greedy: average runtime and heap operations
    - DP (for small n): average runtime and number of DP states explored
    """
    results = {
        'greedy': {'n': [], 'time_mean': [], 'time_std': [], 
                   'ops_mean': [], 'ops_std': [], 'completion': []},
        'dp': {'n': [], 'time_mean': [], 'time_std': [], 
               'states_mean': [], 'states_std': [], 'completion': []}
    }
    
    for n in n_values:
        print(f"Testing n={n}...")
        
        greedy_times = []
        greedy_ops = []
        dp_times = []
        dp_states = []
        
        for trial in range(trials):
            # New random instance for each trial to smooth out randomness
            tasks = generate_random_tasks(n, seed=trial)
            
            # Greedy measurement
            greedy_tasks = [t.copy() for t in tasks]
            sched_g = UnconstrainedGreedyScheduler(greedy_tasks)
            
            start = time.time()
            completed_g, util_g, ops_g = sched_g.run(verbose=False)
            greedy_times.append(time.time() - start)
            greedy_ops.append(ops_g)
            
            # DP measurement only for small n (exponential)
            if n <= 14:
                dp_tasks = [t.copy() for t in tasks]
                sched_dp = UnconstrainedDPScheduler(dp_tasks)
                
                start = time.time()
                completed_dp, util_dp, states_dp = sched_dp.run(verbose=False)
                dp_times.append(time.time() - start)
                dp_states.append(states_dp)
        
        # Aggregate greedy stats
        results['greedy']['n'].append(n)
        results['greedy']['time_mean'].append(np.mean(greedy_times))
        results['greedy']['time_std'].append(np.std(greedy_times))
        results['greedy']['ops_mean'].append(np.mean(greedy_ops))
        results['greedy']['ops_std'].append(np.std(greedy_ops))
        results['greedy']['completion'].append(100.0)  # unconstrained, so always 100%
        
        # Aggregate DP stats (only stored when we actually ran DP)
        if n <= 14:
            results['dp']['n'].append(n)
            results['dp']['time_mean'].append(np.mean(dp_times))
            results['dp']['time_std'].append(np.std(dp_states))
            results['dp']['states_mean'].append(np.mean(dp_states))
            results['dp']['states_std'].append(np.std(dp_states))
            results['dp']['completion'].append(100.0)
    
    return results


def create_unconstrained_plots(data: Dict):
    """
    Build two plots:
    1) Runtime vs number of tasks for greedy and DP.
    2) Greedy heap operations vs DP states explored as n grows.
    """
    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(2, 1, hspace=0.3, wspace=0.3)
    
    # === Plot 1: Runtime comparison (linear scale) ===
    ax1 = fig.add_subplot(gs[0, 0])
    
    g_n = data['greedy']['n']
    g_time = data['greedy']['time_mean']
    g_std = data['greedy']['time_std']
    
    d_n = data['dp']['n']
    d_time = data['dp']['time_mean']
    d_std = data['dp']['time_std']
    
    # Greedy runtime with error bars
    ax1.errorbar(g_n, g_time, yerr=g_std, marker='o', linewidth=2.5,
                 capsize=5, label='Greedy (unconstrained)', color='#2E86AB')
    # DP runtime with error bars (only for small n)
    ax1.errorbar(d_n, d_time, yerr=d_std, marker='s', linewidth=2.5,
                 capsize=5, label='DP (unconstrained)', color='#A23B72')
    
    ax1.set_xlabel('Number of Tasks (n)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Runtime (seconds)', fontsize=12, fontweight='bold')
    ax1.set_title('Unconstrained Scheduling: Runtime Scaling', 
                  fontsize=13, fontweight='bold')
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3)
    
    # === Plot 2: Operations vs states ===
    ax3 = fig.add_subplot(gs[1, 0])
    
    g_ops = data['greedy']['ops_mean']
    d_states = data['dp']['states_mean']
    
    # Left y-axis: greedy operations
    ax3_twin = ax3.twinx()  # Right y-axis for DP states
    
    line1 = ax3.plot(g_n, g_ops, marker='o', linewidth=2.5,
                     label='Greedy Operations', color='#2E86AB')
    line2 = ax3_twin.plot(d_n, d_states, marker='s', linewidth=2.5,
                          label='DP States Explored', color='#A23B72')
    
    ax3.set_xlabel('Number of Tasks (n)', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Greedy Operations', fontsize=12, fontweight='bold', color='#2E86AB')
    ax3_twin.set_ylabel('DP States', fontsize=12, fontweight='bold', color='#A23B72')
    ax3.tick_params(axis='y', labelcolor='#2E86AB')
    ax3_twin.tick_params(axis='y', labelcolor='#A23B72')
    ax3.set_title('Algorithmic Work: Greedy Operations vs DP States', 
                  fontsize=13, fontweight='bold')
    
    # Merge legends from both axes
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax3.legend(lines, labels, fontsize=11, loc='upper left')
    ax3.grid(True, alpha=0.3)
    
    plt.suptitle('Unconstrained Scheduling Analysis', fontsize=16, fontweight='bold', y=0.995)
    
    return fig


if __name__ == "__main__":
    # Range of problem sizes for each algorithm
    greedy_n = [5, 10, 15, 20, 30, 40, 50, 75, 100]
    dp_n = [4, 6, 8, 10, 12, 14]
    
    # Union of sizes so we can run both schedulers where possible
    n_values = sorted(list(set(greedy_n + dp_n)))
    
    data = measure_unconstrained_scaling(n_values, trials=3)
    
    # Basic text summary for greedy
    print("Greedy Scheduler (unconstrained):")
    print(f"{'n':>5} {'Time (s)':>12} {'Operations':>12} {'Completion':>12}")
    print("-" * 50)
    for i, n in enumerate(data['greedy']['n']):
        print(f"{n:>5} {data['greedy']['time_mean'][i]:>12.6f} "
              f"{data['greedy']['ops_mean'][i]:>12.0f} "
              f"{data['greedy']['completion'][i]:>11.1f}%")
    
    # Basic text summary for DP
    print("\nDP Scheduler (unconstrained):")
    print(f"{'n':>5} {'Time (s)':>12} {'States':>12} {'Completion':>12}")
    print("-" * 50)
    for i, n in enumerate(data['dp']['n']):
        print(f"{n:>5} {data['dp']['time_mean'][i]:>12.6f} "
              f"{data['dp']['states_mean'][i]:>12.0f} "
              f"{data['dp']['completion'][i]:>11.1f}%")
    
    # Simple speedup calculation (how many times slower DP is)
    print("\nSpeedup Analysis (DP time / Greedy time):")
    print(f"{'n':>5} {'Speedup Factor':>20}")
    print("-" * 30)
    for n in data['dp']['n']:
        g_idx = data['greedy']['n'].index(n)
        d_idx = data['dp']['n'].index(n)
        speedup = data['dp']['time_mean'][d_idx] / data['greedy']['time_mean'][g_idx]
        print(f"{n:>5} {speedup:>19.1f}x")
    
    # Create and save figures
    fig = create_unconstrained_plots(data)
    fig.savefig('unconstrained_scaling_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()