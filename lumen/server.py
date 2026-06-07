"""FastAPI app exposing the M4 protocol plus a developer preview.

Device-facing endpoints (the only ones the firmware uses):
    GET  /next            -> {"id", "duration", "transition"?}
    GET  /frame/{id}      -> 4096 bytes, big-endian RGB565

Operator / developer endpoints:
    POST /priority/{id}   -> inject a one-shot priority scene
    GET  /preview         -> HTML dashboard, all scenes scaled up
    GET  /preview/{id}.png-> single scene as a scaled PNG
    GET  /health          -> liveness + registered scenes
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Response

import lumen.scenes  # noqa: F401  -- import for side effect: registers all scenes

from . import FRAME_BYTES
from .config import load_config
from .registry import SCENES
from .renderer import FrameRenderer
from .stage import StageManager

config = load_config()
stage = StageManager(config)
renderer = FrameRenderer(config)

app = FastAPI(title="lumen-py", version="0.1.0")


# -- device protocol --------------------------------------------------------
@app.get("/next")
def next_scene() -> dict:
    nxt = stage.next()
    body = {"id": nxt.id, "duration": nxt.duration}
    if nxt.transition:
        body["transition"] = nxt.transition
    return body


@app.get("/current")
def current_scene() -> dict:
    cur = stage.current()
    body = {"id": cur.id, "duration": cur.duration}
    if cur.transition:
        body["transition"] = cur.transition
    return body


@app.get("/frame/{scene_id}")
def frame(scene_id: str) -> Response:
    data = renderer.frame(scene_id)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Length": str(len(data))},
    )


# -- operator ---------------------------------------------------------------
@app.post("/priority/{scene_id}")
def priority(scene_id: str) -> dict:
    if not stage.inject(scene_id):
        raise HTTPException(status_code=404, detail=f"unknown scene: {scene_id}")
    return {"queued": scene_id}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "scenes": sorted(SCENES), "frame_bytes": FRAME_BYTES}


# -- developer preview ------------------------------------------------------
@app.get("/preview/{scene_id}.png")
def preview_png(scene_id: str, scale: int = 8) -> Response:
    scene = SCENES.get(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail=f"unknown scene: {scene_id}")
    from datetime import datetime

    from .scene import RenderContext

    ctx = RenderContext(now=datetime.now(), config=config)
    png = scene.render(ctx).to_png(scale=max(1, min(scale, 20)))
    return Response(content=png, media_type="image/png")


@app.get("/preview")
def preview() -> Response:
    cards = "\n".join(
        f'<figure><img src="/preview/{sid}.png?scale=8" alt="{sid}">'
        f"<figcaption>{sid}</figcaption></figure>"
        for sid in sorted(SCENES)
    )
    html = f"""<!doctype html><html><head><meta charset=utf-8>
<title>lumen-py preview</title>
<meta http-equiv=refresh content=5>
<style>
 body{{background:#111;color:#ccc;font-family:system-ui,sans-serif;margin:24px}}
 h1{{font-size:16px;font-weight:600}}
 .grid{{display:flex;flex-wrap:wrap;gap:20px}}
 figure{{margin:0}}
 img{{image-rendering:pixelated;border:1px solid #333;display:block}}
 figcaption{{font-size:12px;margin-top:6px;color:#888}}
</style></head><body>
<h1>lumen-py &middot; scene preview <span style=color:#555>(auto-refresh 5s)</span></h1>
<div class=grid>{cards}</div>
</body></html>"""
    return Response(content=html, media_type="text/html")


def main() -> None:
    import uvicorn

    uvicorn.run("lumen.server:app", host="0.0.0.0", port=8080, reload=False)


if __name__ == "__main__":
    main()
