---
title: "Lab Manual: Web Technologies Laboratory, Semester VI"
doc_id: "DEMO/LAB/CE/WT/2026"
is_demo: true
demo_reason: "Internal teaching material for enrolled students, not published.
  Synthesised to provide lab content whose vocabulary overlaps heavily with the
  networks and database manuals, so that retrieval must distinguish between
  documents rather than matching on shared terminology."
category: "lab_manual"
department: "Computer Engineering"
created: "2026-01-06"
---

## Environment

HTML, CSS and JavaScript in the browser; Node.js on the server; PostgreSQL for
persistence. Work runs on the lab workstations against a local server; nothing
is deployed to a public host from this lab.

## Acceptable use

Test only against your own server on the lab segment. Testing techniques from
Experiment 8 against any host you do not own is out of scope for this lab and is
a disciplinary matter.

## Experiment 1: Semantic markup and accessibility

Build a multi-section page using semantic elements. Run an accessibility check
and fix what it reports.

**Expected observation.** Record what the check flagged before and after. A page
that looks identical but goes from twelve issues to zero is the point.

## Experiment 2: Layout

Implement the same layout twice, once with flexbox and once with grid, and make
both responsive at three breakpoints.

**Expected observation.** State which tool suited the layout better and why.
"Both work" is not an observation.

## Experiment 3: DOM and events

Build an interactive list with add, edit, delete and filter, with no framework.

**Expected observation.** Demonstrate event delegation. Compare the listener
count against attaching one listener per row for a thousand rows.

## Experiment 4: Asynchronous requests

Consume a local JSON endpoint. Handle loading, empty, and error states
explicitly.

**Expected observation.** Simulate a slow response and a failing one. A page
that only handles success is not complete; the three states are the experiment.

## Experiment 5: Server-side routing and templating

Build a small Node server with routes for listing, viewing and creating a
resource.

**Expected observation.** Record status codes for success, not-found and
validation failure. Returning 200 with an error message in the body is the
defect to avoid.

## Experiment 6: Persistence

Connect the server to PostgreSQL. Implement create, read, update and delete
with parameterised queries.

**Expected observation.** Demonstrate that a value containing a quote character
is stored and retrieved intact. Then explain what string concatenation would
have done with the same input.

## Experiment 7: Sessions and authentication

Implement registration and login with hashed passwords and a session cookie.

**Expected observation.** Show the stored hash for two identical passwords and
explain why they differ. Show that the session cookie carries the security
attributes you set.

## Experiment 8: Input validation

Add server-side validation to every endpoint from Experiment 6.

**Expected observation.** Demonstrate that removing client-side validation does
not remove protection. Client-side validation is a convenience; server-side
validation is the control, and this experiment exists to make that concrete.

## Submission

Source, a short README explaining how to run it, and the observation section.
Code that only runs on your own machine because of hard-coded paths is marked
down.
