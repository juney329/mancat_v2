from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.dataset import BandDataset, DatasetService


@pytest.fixture()
def synthetic_dataset(tmp_path: Path) -> DatasetService:
    band_id = "test"
    freqs = np.linspace(100, 200, num=500, dtype=np.float64)
    times = np.linspace(0, 50, num=300, dtype=np.float64)

    np.save(tmp_path / f"freqs0_{band_id}.npy", freqs)
    np.save(tmp_path / f"rel_t_{band_id}.npy", times)

    summary_path = tmp_path / f"summary_{band_id}.npz"
    np.savez(summary_path, Avg=np.sin(freqs / 20.0), Max=np.cos(freqs / 30.0))

    meta = {"waterfall_shape": [len(times), len(freqs)], "start_unix": 1000.0}
    with (tmp_path / f"meta_{band_id}.json").open("w", encoding="utf-8") as fh:
        json.dump(meta, fh)

    waterfall_path = tmp_path / f"waterfall_band{band_id}.dat"
    tile = (np.outer(np.linspace(0, 1, len(times)), np.linspace(0, 1, len(freqs))) * 1000).astype(
        np.int16
    )
    mm = np.memmap(waterfall_path, dtype=np.int16, mode="w+", shape=meta["waterfall_shape"])
    mm[:] = tile[:]
    mm.flush()

    service = DatasetService(data_dir=tmp_path)
    service.get_band(band_id)
    return service


def test_summary_slice_resamples(synthetic_dataset: DatasetService) -> None:
    band = synthetic_dataset.get_band("test")
    result = band.summary_slice(f0=120.0, f1=180.0, max_points=100)
    assert "freqs" in result
    assert len(result["freqs"]) <= 100
    assert all(len(values) == len(result["freqs"]) for key, values in result.items() if key != "freqs")


def test_waterfall_tile_downsamples(synthetic_dataset: DatasetService) -> None:
    band = synthetic_dataset.get_band("test")
    tile, times, freqs = band.waterfall_tile(
        f0=120.0, f1=190.0, t0=5.0, t1=25.0, maxw=50, maxt=40
    )
    assert tile.shape[0] <= 40
    assert tile.shape[1] <= 50
    assert times.shape[0] == tile.shape[0]
    assert freqs.shape[0] == tile.shape[1]


def test_markers_roundtrip(tmp_path: Path) -> None:
    band = BandDataset("demo", tmp_path)
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "meta_demo.json").write_text("{}", encoding="utf-8")
    np.save(tmp_path / "freqs0_demo.npy", np.array([1.0, 2.0]))
    np.save(tmp_path / "rel_t_demo.npy", np.array([0.0, 1.0]))
    np.savez(tmp_path / "summary_demo.npz", Avg=np.array([1.0, 2.0]))
    with pytest.raises(FileNotFoundError):
        band.waterfall_shape()

    markers = [{"id": "a", "freq": 1.23, "label": "test", "color": "#fff", "width": 10.0}]
    band.save_markers(markers)
    loaded = band.load_markers()
    assert loaded == markers
