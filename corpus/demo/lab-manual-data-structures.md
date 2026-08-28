---
title: "Lab Manual: Data Structures Laboratory, Semester III"
doc_id: "DEMO/LAB/CE/DS/2026"
is_demo: true
demo_reason: "Laboratory manuals are internal teaching material distributed to
  enrolled students and are not published. Synthesised to add a fourth manual
  with the same structure but different content, so retrieval precision across
  near-sibling documents can be measured."
category: "lab_manual"
department: "Computer Engineering"
created: "2026-01-06"
---

## Environment

C on Linux, compiled with warnings enabled. Code that compiles with warnings
suppressed is not accepted; the warnings are usually the bug.

Every program must free what it allocates. Programs are checked for leaks, and a
leaking program scores a reduced mark even where the output is correct.

## Experiment 1: Dynamic arrays

Implement a growable array with append, indexed access and removal. Double the
capacity on growth.

**Expected observation.** Measure the cost of a million appends with doubling
against growth by a fixed increment. Explain the difference in terms of
amortised cost rather than by quoting a result.

## Experiment 2: Singly linked list

Implement insert at head, at tail, at position, and delete by value.

**Expected observation.** Compare indexed access on the linked list against the
dynamic array from Experiment 1. Record where each wins and state the crossover
you actually measured, not the one you expected.

## Experiment 3: Stack and queue

Implement both over an array and over a linked list. Use the stack to check
balanced parentheses and to evaluate a postfix expression.

**Expected observation.** The array-backed queue must handle wrap-around
correctly. Test with a sequence that wraps at least twice; a queue that works
until it wraps is the classic defect here.

## Experiment 4: Binary search tree

Implement insert, search, delete and in-order traversal.

**Expected observation.** Insert sorted input and record the resulting height.
Explain why the tree degenerates and what that does to search cost. This is the
motivation for Experiment 5, so do not skip the explanation.

## Experiment 5: Balanced trees

Implement AVL rotations on top of Experiment 4.

**Expected observation.** Insert the same sorted input as before and record the
height. Compare against the unbalanced case and against log2(n).

## Experiment 6: Hashing

Implement a hash table with separate chaining and with linear probing.

**Expected observation.** Measure the average probe count at load factors of
0.5, 0.75 and 0.95 for both. Explain why linear probing degrades faster, and
what clustering means in your own words.

## Experiment 7: Heaps and priority queues

Implement a binary min-heap with insert and extract-min, then heapsort.

**Expected observation.** Compare building a heap by repeated insertion against
building it in place. Record both timings and explain the difference in
complexity.

## Experiment 8: Graph traversal

Represent a graph as an adjacency list. Implement breadth-first and depth-first
traversal, and detect a cycle.

**Expected observation.** State which traversal you used for cycle detection and
why. Test on a disconnected graph — a traversal that visits only one component
is the most common defect in this experiment.

## Submission

Source, sample input and output, and the observation section. Observations that
restate what the code does without reporting a measurement score zero for that
section; the measurement is the experiment.
