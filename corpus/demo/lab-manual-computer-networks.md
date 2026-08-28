---
title: "Lab Manual: Computer Networks Laboratory, Semester V"
doc_id: "DEMO/LAB/CE/CN/2026"
is_demo: true
demo_reason: "Laboratory manuals are internal teaching material distributed to
  enrolled students and are not published. Synthesised to provide technical
  procedural content with safety and acceptable-use constraints."
category: "lab_manual"
department: "Computer Engineering"
created: "2026-01-06"
---

## Laboratory environment

Experiments use the isolated networking lab segment, which is deliberately not
connected to the campus production network. Capture and analysis use Wireshark;
topology simulation uses Cisco Packet Tracer; command-line work is on Linux.

## Acceptable use — read before session one

Packet capture is performed **only** on the isolated lab segment and **only** on
traffic you generate yourself. Capturing on the campus production network, or
capturing traffic belonging to other people, is a disciplinary matter and is not
covered by "it was for the lab".

If an experiment appears to require capturing someone else's traffic, you have
misread the experiment. Ask the instructor.

## Experiment 1: Network interface configuration

Configure a static address, netmask and gateway on a lab host. Verify with `ip
addr` and `ip route`. Break the configuration deliberately — wrong netmask —
and record which hosts become unreachable and why.

**Expected observation.** A wrong netmask produces asymmetric reachability:
some hosts reachable, some not, depending on whether they fall inside the
incorrectly computed subnet.

## Experiment 2: ARP and the local segment

Clear the ARP cache, generate traffic to a neighbour, and capture the exchange.

**Expected observation.** An ARP request is broadcast; the reply is unicast.
Record both frames and identify the fields that make this so.

## Experiment 3: ICMP and path discovery

Use `ping` and `traceroute` across the lab topology while capturing.

**Expected observation.** Successive traceroute probes carry increasing TTL
values and elicit time-exceeded replies from successive routers. Match each
reply to the hop that generated it.

## Experiment 4: TCP connection establishment and teardown

Capture a complete TCP session against a lab server.

**Expected observation.** Identify the three-way handshake, the sequence and
acknowledgement number relationship, and the four-way teardown. Record what
happens to the sequence numbers across the FIN exchange.

## Experiment 5: TCP versus UDP under loss

Introduce artificial loss on the link and transfer the same payload over TCP and
over UDP.

**Expected observation.** TCP retransmits and the payload arrives intact with
higher elapsed time; UDP does not and the payload arrives incomplete. Quantify
both.

## Experiment 6: DNS resolution

Capture a resolution against the lab resolver for a name held in the lab zone.

**Expected observation.** Identify the query and response, the record type, and
the TTL. Repeat immediately and explain why the second lookup may produce no
network traffic at all.

## Experiment 7: Static routing between subnets

Build a two-router topology in Packet Tracer, configure static routes, and
demonstrate end-to-end reachability. Then remove one route and diagnose the
resulting failure from the router's perspective rather than the host's.

**Expected observation.** Reachability may fail in one direction only. Explain
why a return route is as necessary as a forward route.

## Experiment 8: Basic firewall rules

Apply a rule set on a lab host permitting SSH from one subnet and denying it
from another. Verify both cases.

**Expected observation.** The denied case should be distinguishable from a host
that is simply down. Record how, and what that difference implies for someone
scanning the network.

## Submission

Each write-up includes the capture file, the relevant filtered frames, and the
observation. Submit captures as `.pcapng`; screenshots of Wireshark are not
accepted in place of the capture file.
