---
title: "Helpdesk: Lab Machine Will Not Boot, and Reimaging Requests"
doc_id: "DEMO/HELP/LAB/2026/04"
is_demo: true
demo_reason: "Internal helpdesk knowledge base articles are held in a ticketing
  system and are not public. Synthesised to provide troubleshooting content that
  overlaps with the laboratory SOP, so that retrieval must distinguish a
  procedure from a troubleshooting guide."
category: "helpdesk"
department: "IT Services"
created: "2026-02-10"
---

## Before you do anything

**Your work is not on the lab machine.** Tier 0 accounts have local home
directories that the reimaging process wipes. If your work is only on the
workstation, say so when you report the fault — recovery may be possible before
reimaging, but not after.

Export to your Tier 1 network home at the end of every session. See
DEMO/WIKI/IT/012.

## Symptom: nothing on screen

1. Check the monitor power and cable at both ends. This is the single most
   common cause and takes ten seconds to rule out.
2. Check whether the machine fans are running. Fans running with no display is a
   different fault from nothing at all.
3. Try a different monitor cable if one is available at the bench.
4. Report to the lab assistant with what you observed, using the asset tag on
   the case.

## Symptom: powers on, does not reach the operating system

Note the exact text on screen before anything else. "No bootable device",
"Operating system not found" and a filesystem error are three different faults
with three different fixes, and the message is the diagnosis.

Do not attempt BIOS or boot-order changes. Lab machines have a standard
configuration and changing it turns a five-minute fix into a reimage.

## Symptom: boots, but very slow or repeatedly freezing

Note whether it affects one account or all accounts on that machine, and whether
it affects one machine or the whole bench. One account on one machine is a
profile problem; every account on one machine is hardware; a whole bench is
usually the network or the share.

## Requesting a reimage

Reimaging is requested by the lab assistant, not by students directly, and is
scheduled outside teaching hours. It restores the standard image and destroys
everything in the local home directory.

Before a reimage, the lab assistant records the asset tag, the fault, and
whether any user has asked for local data to be preserved. Preservation is
best-effort and is never guaranteed.

## What to include when reporting

Asset tag from the case label, the exact on-screen message, whether it affects
other accounts, whether it affects neighbouring machines, and what you had been
doing when it started. A report of "machine not working" cannot be triaged and
will come back to you for these details.

## Triage expectations

Faults are triaged per DEMO/SOP/LAB/2026/04: category A is same working day,
category B is three working days, category C is the next maintenance window. A
single unusable workstation in a lab that can still run its practical is
category B, not A, however inconvenient.
