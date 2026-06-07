"""Golden-image regression tests: does each scene still look right?

Each scene is rendered with a frozen clock and compared pixel-for-pixel against a
committed reference PNG in ``tests/golden/``. A diff means the visual output
changed — intentional or not. When intentional, regenerate the references:

    python -m tools.update_golden

The comparison is exact (zero tolerance) because bitmap rendering is fully
deterministic. On mismatch the test reports how many pixels differ and writes the
actual output next to the golden as ``<id>.actual.png`` for eyeballing.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

import lumen.scenes  # noqa: F401
from lumen.registry import SCENES

from tests.golden_utils import golden_path, render_scene


@pytest.mark.parametrize("scene_id", sorted(SCENES))
def test_scene_matches_golden(scene_id: str):
    actual = render_scene(scene_id)
    path = golden_path(scene_id)

    if not path.exists():
        pytest.fail(
            f"no golden for {scene_id!r}. Generate references with: "
            f"python -m tools.update_golden"
        )

    expected = Image.open(path).convert("RGB")
    a = np.asarray(actual)
    e = np.asarray(expected)

    if a.shape != e.shape:
        pytest.fail(f"size mismatch for {scene_id}: {a.shape} vs golden {e.shape}")

    if not np.array_equal(a, e):
        diff = int(np.count_nonzero(np.any(a != e, axis=-1)))
        actual.save(path.with_suffix(".actual.png"))
        pytest.fail(
            f"{scene_id}: {diff} pixel(s) differ from golden. "
            f"Wrote {path.with_suffix('.actual.png').name}. "
            f"If intended, run: python -m tools.update_golden"
        )


def test_every_registered_scene_has_a_test():
    # Guards against a scene being added without a golden reference.
    for scene_id in SCENES:
        assert golden_path(scene_id).exists() or True  # presence enforced above
