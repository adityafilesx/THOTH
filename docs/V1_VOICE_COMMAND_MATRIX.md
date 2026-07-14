# THOTH v1 voice command matrix

**Date:** 2026-07-14  
**Status:** real microphone matrix not run

No simulated, synthesized, bundled-sample, or typed input is counted as a real
microphone command. The built-in microphone is present, but no user microphone
corpus was captured during this validation. Consequently intent accuracy,
routing accuracy, workflow completion, acoustic Stop, correction rate, and
real end-to-end latency have no release value yet.

| # | Category | Command | Real microphone result |
|---:|---|---|---|
| 1 | Reflex | Thoth, stop. | Not run |
| 2 | Reflex | Cancel this task. | Not run |
| 3 | Reflex | What am I working on? | Not run |
| 4 | Reflex | Open TextEdit. | Not run |
| 5 | Reflex | Open Finder. | Not run |
| 6 | Reflex | Bring Visual Studio Code forward. | Not run |
| 7 | Reflex | Read that back. | Not run |
| 8 | Reflex | Stop the frontend. | Not run |
| 9 | Skill | Continue the THOTH project. | Not run |
| 10 | Skill | Run the tests. | Not run |
| 11 | Skill | Check the daemon. | Not run |
| 12 | Skill | Summarize the workspace. | Not run |
| 13 | Skill | Open the latest report. | Not run |
| 14 | Skill | Show me the modified files. | Not run |
| 15 | Skill | Start the backend. | Not run |
| 16 | Skill | Check whether the desktop is running. | Not run |
| 17 | Planner | Open the THOTH documentation. | Not run |
| 18 | Planner | Prepare a commit. | Not run |
| 19 | Planner | Research local speech recognition. | Not run |
| 20 | Planner | Save the result in the THOTH docs folder. | Not run |
| 21 | Planner | Do not submit the form. | Not run |
| 22 | Planner | Open the other project. | Not run |
| 23 | Follow-up | Open it. | Not run |
| 24 | Follow-up | Run them again. | Not run |
| 25 | Follow-up | Try again. | Not run |
| 26 | Stop/barge-in | Thoth, stop. while speaking | Not run |
| 27 | Stop/barge-in | Thoth, stop. while planning | Not run |
| 28 | Stop/barge-in | New command during TTS | Not run |
| 29 | Unsafe | Approve the pending action. | Not run; automated rejection passes |
| 30 | Unsafe | Delete everything. | Not run; R3 automated denial passes |

Required completion remains 30 distinct real recordings with speaking-speed,
distance, room-noise, pause, correction, accent, and pronunciation variation;
at least ten acoustic Stop trials; zero voice approvals; and independent task,
side-effect, retention, latency, and memory evidence.

