---
title: "Lab Manual: Operating Systems Laboratory, Semester IV"
doc_id: "DEMO/LAB/CE/OS/2026"
is_demo: true
demo_reason: "Internal teaching material for enrolled students; not published
  publicly. Synthesised to add a third lab manual so that chunking and
  retrieval can be evaluated on near-sibling documents that share structure but
  differ in content."
category: "lab_manual"
department: "Computer Engineering"
created: "2026-01-06"
---

## Laboratory environment

Experiments run on Linux on the lab workstations. Where an experiment risks
leaving the system in a poor state — fork bombs, memory exhaustion — it is run
inside a container or a virtual machine, never on the host.

## Experiment 1: Process creation

Write a program using `fork()` that prints the process and parent process
identifiers from both branches.

**Expected observation.** The order of the two outputs is not deterministic.
Run twenty times and record how often each order appears. The point is that
concurrency has no default order.

## Experiment 2: Process replacement

Extend Experiment 1 so the child replaces itself using an `exec` family call.

**Expected observation.** Code after the `exec` call in the child never runs
unless the call failed. Demonstrate both cases.

## Experiment 3: Zombie and orphan processes

Create a zombie by having a parent not reap its child, and an orphan by having
the parent exit first. Observe both with `ps`.

**Expected observation.** The zombie shows state `Z` and disappears when reaped;
the orphan is re-parented to init. Record the parent process identifier before
and after.

## Experiment 4: CPU scheduling simulation

Implement first-come-first-served, shortest-job-first and round-robin over a
given set of arrival and burst times. Compute average waiting and turnaround
time for each.

**Expected observation.** Shortest-job-first gives the lowest average waiting
time for the given set. Construct a second set where round-robin is preferable
and explain what changed.

## Experiment 5: Synchronisation

Implement the producer-consumer problem using semaphores over a bounded buffer.
Then deliberately remove one semaphore operation.

**Expected observation.** The broken version fails intermittently, not
consistently. Run it enough times to observe the failure, and note that a race
condition passing a single test proves nothing.

## Experiment 6: Deadlock

Construct a two-process, two-resource deadlock, observe it, then resolve it by
imposing a global lock ordering.

**Expected observation.** With lock ordering imposed, the deadlock cannot form.
Explain which of the four Coffman conditions the fix removes.

## Experiment 7: Memory and page replacement

Implement FIFO, LRU and optimal page replacement over a reference string.
Compute fault counts for increasing frame counts.

**Expected observation.** FIFO can exhibit Belady's anomaly — more frames
producing more faults. Find a reference string that demonstrates it, and confirm
LRU does not.

## Experiment 8: File system operations

Use system calls rather than library functions to copy a file. Compare
throughput at buffer sizes of 1, 512, 4096 and 65536 bytes.

**Expected observation.** Throughput improves sharply up to around the block
size and then flattens. Plot it and explain the shape in terms of system call
overhead.

## Submission

Source code, output, and the observation section. Code that does not compile
scores zero regardless of the write-up; check on a lab machine, not only on your
own laptop.
