# lumen-py — Architecture Overview

> **lumen-py**: a server-driven, always-on ambient display system for the Adafruit Matrix Portal M4.

---

## Concept

Lumen splits responsibilities cleanly between a home server and the M4 device. The server owns all logic, data, and scene composition. The M4 owns hardware driving, transitions, and sleep scheduling. The firmware is stable and essentially never changes — all iteration happens on the server.

---

## System Diagram

```
┌─────────────────────────────────┐         ┌──────────────────────────────┐
│           SERVER                │         │        MATRIX PORTAL M4      │
│                                 │         │                              │
│  ┌─────────────────────────┐    │  HTTP   │  ┌────────────────────────┐  │
│  │     Stage Manager       │◄───┼─────────┼──│   /next  (poll)        │  │
│  │  - scene rotation order │    │         │  └────────────────────────┘  │
│  │  - per-scene duration   │    │         │                              │
│  │  - priority injection   │    │  HTTP   │  ┌────────────────────────┐  │
│  └─────────────────────────┘    │◄────────┼──│   /frame/{id} (fetch)  │  │
│                                 │         │  └────────────────────────┘  │
│  ┌─────────────────────────┐    │         │                              │
│  │     Scene Renderers     │    │         │  ┌────────────────────────┐  │
│  │  - weather              │    │         │  │   Local Scene Registry │  │
│  │  - transit departures   │    │         │  │  - clock (NTP-based)   │  │
│  │  - GitHub activity      │    │         │  │  - [future sensors]    │  │
│  │  - countdown (Porto...) │    │         │  └────────────────────────┘  │
│  │  - idle / ambient       │    │         │                              │
│  └─────────────────────────┘    │         │  ┌────────────────────────┐  │
│                                 │         │  │  Transition Engine     │  │
│  ┌─────────────────────────┐    │         │  │  - slide / fade / wipe │  │
│  │  Pillow Compositor      │    │         │  │  - runs at 30+ fps     │  │
│  │  - renders RGB565 frame │    │         │  │  - fully on-device     │  │
│  │  - 64×32 = 4096 bytes   │    │         │  └────────────────────────┘  │
│  └─────────────────────────┘    │         │                              │
│                                 │         │  ┌────────────────────────┐  │
└─────────────────────────────────┘         │  │  Sleep Scheduler       │  │
                                            │  │  - NTP sync on boot    │  │
                                            │  │  - RTC persists sleep  │  │
                                            │  │  - active: 07:00–00:00 │  │
                                            │  └────────────────────────┘  │
                                            └──────────────────────────────┘
```

---

## Responsibilities

| Concern | Server | M4 |
|---|---|---|
| Scene rotation & ordering | ✓ | — |
| API calls & auth tokens | ✓ | — |
| JSON parsing | ✓ | — |
| Frame composition (Pillow) | ✓ | — |
| Scene duration control | ✓ | — |
| Priority scene injection | ✓ | — |
| RGB565 frame delivery | ✓ | — |
| HUB75 panel driving | — | ✓ |
| Transition animations | — | ✓ |
| Clock scene rendering | — | ✓ |
| Sleep / wake scheduling | — | ✓ |
| Local sensor scenes | — | ✓ |
| WiFi + HTTP client | — | ✓ |

---

## M4 Main Loop

```
boot
 └─ NTP sync → write RTC
 └─ check active hours
     ├─ outside window → deep sleep until 07:00
     └─ inside window → enter scene loop

scene loop:
 ┌─────────────────────────────────────────────┐
 │  GET /next  →  { id, duration }             │
 │                                             │
 │  if id in LOCAL_SCENES:                     │
 │      render locally into buf_next           │
 │  else:                                      │
 │      GET /frame/{id}  →  4096 bytes RGB565  │
 │      write into buf_next                    │
 │                                             │
 │  run transition(buf_current → buf_next)     │
 │  swap buffers                               │
 │  sleep(duration)                            │
 │                                             │
 │  if outside active hours → deep sleep       │
 └─────────────────────────────────────────────┘
```

The fetch for scene N happens while scene N-1 is still showing — fetch latency is fully hidden.

---

## Frame Protocol

The server returns raw binary pixel data. No JSON, no headers beyond `Content-Type`.

```
GET /frame/{scene_id}
→ 4096 bytes, big-endian RGB565
   [ pixel(0,0) ][ pixel(1,0) ] ... [ pixel(63,31) ]
   2 bytes per pixel × 64 × 32 = 4096 bytes
```

The stage manager endpoint returns lightweight JSON:

```
GET /next
→ { "id": "weather", "duration": 8 }
```

---

## Scene Inventory

### Server-rendered scenes

| ID | Description | Data source |
|---|---|---|
| `transit` | Next bus/train departures | RMV OpenData API |
| `weather` | Current conditions + temp | Weather API |
| `github` | Commit activity / streak | GitHub REST API |
| `countdown` | Days/hours to target date | Server config |
| `idle` | Ambient / clock overlay | — |

### Local scenes (on-device)

| ID | Description | Why local |
|---|---|---|
| `clock` | HH:MM:SS pixel clock | Needs per-second refresh — server polling model doesn't fit |

---

## Transition Engine

Transitions run entirely on the M4 between two pre-fetched RGB565 framebuffers. No server involvement.

- **Slide** — columns sweep left, cheap, good default
- **Fade** — per-pixel channel blend over ~10 frames, most polished
- **Wipe** — hard vertical edge, fast
- **Dissolve** — randomised pixel order, visually interesting

Target: 30+ fps during transition (~33ms/frame). Tight loop, no sleep.

The transition style can be included in the `/next` response for server-controlled pairing of transitions to scene types.

---

## Power / Sleep

The M4's RTC is set once on first NTP sync and survives deep sleep cycles.

| Time | State |
|---|---|
| 07:00 | Wake from deep sleep, NTP sync, begin scene loop |
| 07:00 – 00:00 | Active — scene loop running |
| 00:00 | `matrix.brightness = 0`, deep sleep until 07:00 |

On unexpected power loss during active hours: boot → check RTC → resume or sleep as appropriate. Self-healing with no intervention.

---

## Extensibility

Adding a new **server scene**: implement a renderer on the server, add the ID to the stage manager rotation. Zero firmware changes.

Adding a new **local scene**: write a `render_*` function on the M4, register it in `LOCAL_SCENES`. The server stage manager just needs to know the ID exists.

The M4 firmware is intended to be stable after initial setup. All day-to-day changes live on the server.

---

## Tech Stack

| Layer | Technology |
|---|---|
| M4 firmware | CircuitPython, `rgbmatrix`, `framebufferio`, `adafruit_requests` |
| Server language | Python |
| Frame rendering | Pillow (PIL) |
| Server framework | Flask (or FastAPI) |
| Scene data | REST APIs, local config |
| Transport | HTTP over WiFi (LAN) |
| Frame format | Raw RGB565 binary |
