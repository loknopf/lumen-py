# lumen-py

Server side of **lumen** — a server-driven ambient display for the Adafruit
Matrix Portal M4. The server owns all logic, data and scene composition; it
renders 64×32 frames and hands them to the M4 as raw RGB565 over HTTP. The
firmware stays stable; all iteration happens here.

See [`design/LUMEN-PY-ARCHITECTURE.md`](design/LUMEN-PY-ARCHITECTURE.md) for the
full system design.

## Protocol

| Endpoint | Returns |
|---|---|
| `GET /next` | `{"id": "weather", "duration": 8, "transition": "fade"}` |
| `GET /frame/{id}` | 4096 bytes, big-endian RGB565, row-major |
| `POST /priority/{id}` | inject a one-shot priority scene |
| `GET /preview` | dev dashboard: every scene scaled up (auto-refresh) |
| `GET /health` | liveness + registered scenes |

## Quick start

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

lumen-server                      # serve on :8080
# open http://localhost:8080/preview
```

## How rendering works

Scenes draw with a small pixel-oriented API on top of Pillow
(`lumen/canvas.py`) using vendored public-domain **bitmap fonts**
(`lumen/assets/fonts/`). At 64×32, crisp pixels beat anti-aliased rasterisation —
so we draw directly rather than rendering from matplotlib/SVG/HTML. Rendering is
deterministic, which the golden tests depend on.

`Canvas.to_rgb565()` produces the exact bytes the `/frame` endpoint serves.

## Adding a scene

1. Create `lumen/scenes/myscene.py`:

   ```python
   from ..canvas import Canvas
   from ..registry import register
   from ..scene import RenderContext, Scene

   @register
   class MyScene(Scene):
       id = "myscene"
       default_duration = 8
       ttl = 60            # frame cache lifetime
       transition = "fade"

       def fetch(self, ctx):           # optional: pull external data (cached)
           return {...}

       def draw(self, ctx) -> Canvas:
           c = Canvas()
           c.text_centered(12, "HELLO", font="6x13")
           return c
   ```

2. Import it in `lumen/scenes/__init__.py`.
3. Add `"myscene"` to `rotation` in your config.
4. `python -m tools.update_golden myscene` to capture its reference image.

No firmware changes, no server wiring.

## Testing the bitmap looks right

- **Golden snapshot tests** — `pytest` renders each scene and compares it
  pixel-for-pixel against committed PNGs in `tests/golden/`. A visual regression
  fails the build and writes `<id>.actual.png` next to the golden for inspection.
  Regenerate intentional changes with `python -m tools.update_golden`.
- **Live preview** — `GET /preview` shows all scenes scaled 8× in the browser,
  auto-refreshing every 5 s.
- **Hardware bring-up** — `python -m tools.dump_frame weather` writes a raw
  `.bin` (wire format) and a `.png` preview.

```bash
pytest                 # unit + golden tests
```

## Configuration

Copy `config.example.toml` to `config.toml` (or point `LUMEN_CONFIG` at a file).
Everything has a default, so it also runs with no config. Per-scene API settings
live under `[scenes.<id>]`.

The transit scene fetches live departures from the RMV OpenData API (HAFAS
`departureBoard`) once station ids plus an access id (`api_key` in config or
the `RMV_API_KEY` env var) are set — either a single `stop_id` or several
stations via `stops`, with optional line filters (`lines = ["U4", "U16"]`)
and direction filters (`direction = "<stop id>"`, only journeys heading
toward that stop), each settable globally or per station. `mode = "compact"`
switches the display from 3 rows with destination text to 4 destination-less
rows with scheduled time and live delay. The github scene
queries the GitHub GraphQL
contributions calendar once `username` plus a token (`token` in config or the
`GITHUB_TOKEN` env var) are set. The weather scene fetches current conditions
from Open-Meteo (no key needed) once a `location` name or
`latitude`/`longitude` are set. Credentials can also live in a local `.env`
file. Without credentials, scenes fall back to built-in demo data (offline
runs, golden tests).

## Credits

The bitmap fonts in `lumen/assets/fonts/` (`4x6.bdf`, `5x8.bdf`, `6x13.bdf`) are
from the **Misc Fixed** collection distributed with the
[X.Org / X Window System](https://www.x.org/) project. Each file carries the
notice: *"Public domain font. Share and enjoy."*

## Layout

```
lumen/
  __init__.py        panel geometry / FRAME_BYTES
  canvas.py          drawing API + RGB565 encoder
  fonts.py           BDF bitmap-font loader
  scene.py           Scene base class + RenderContext
  registry.py        @register decorator + SCENES
  stage.py           rotation order + priority injection
  renderer.py        TTL frame cache + error fallback
  config.py          TOML config (pydantic)
  server.py          FastAPI app + /preview
  scenes/            one module per scene
  sources/           API access layer (GitHub GraphQL, RMV HAFAS, Open-Meteo)
  assets/fonts/      vendored public-domain BDF fonts
tests/               unit + golden tests
tools/               update_golden, dump_frame
```
