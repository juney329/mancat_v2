from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


@dataclass
class BandInfo:
    """Lightweight information about an available band."""

    band_id: str
    meta: Mapping[str, object]


class BandDataset:
    """Represents a single band and exposes slicing helpers."""

    def __init__(self, band_id: str, root: Path) -> None:
        self.band_id = band_id
        self.root = root
        self._meta: Optional[Mapping[str, object]] = None
        self._freqs: Optional[np.ndarray] = None
        self._times: Optional[np.ndarray] = None
        self._summary: Optional[Mapping[str, np.ndarray]] = None
        self._waterfall: Optional[np.memmap] = None
        self._waterfall_shape: Optional[Tuple[int, int]] = None

    # ------------------------------------------------------------------
    # Metadata
    @property
    def meta(self) -> Mapping[str, object]:
        if self._meta is None:
            path = self.root / f"meta_{self.band_id}.json"
            with path.open("r", encoding="utf-8") as fh:
                self._meta = json.load(fh)
        return self._meta

    # ------------------------------------------------------------------
    @property
    def freqs(self) -> np.ndarray:
        if self._freqs is None:
            path = self.root / f"freqs0_{self.band_id}.npy"
            self._freqs = np.load(path)
        return self._freqs

    @property
    def times(self) -> np.ndarray:
        if self._times is None:
            path = self.root / f"rel_t_{self.band_id}.npy"
            self._times = np.load(path)
        return self._times

    @property
    def summary(self) -> Mapping[str, np.ndarray]:
        if self._summary is None:
            path = self.root / f"summary_{self.band_id}.npz"
            archive = np.load(path)
            self._summary = {key: archive[key] for key in archive.files}
        return self._summary

    # ------------------------------------------------------------------
    def _waterfall_path(self) -> Path:
        explicit_path = self.meta.get("waterfall_path")
        if isinstance(explicit_path, str):
            return Path(explicit_path)
        return self.root / f"waterfall_band{self.band_id}.dat"

    def waterfall_shape(self) -> Tuple[int, int]:
        if self._waterfall_shape is not None:
            return self._waterfall_shape
        meta_shape = self.meta.get("waterfall_shape")
        if isinstance(meta_shape, (list, tuple)) and len(meta_shape) == 2:
            shape = int(meta_shape[0]), int(meta_shape[1])
        else:
            freqs = self.freqs
            path = self._waterfall_path()
            total_samples = path.stat().st_size // np.dtype(np.int16).itemsize
            width = len(freqs)
            if width == 0:
                raise ValueError("Frequency axis is empty")
            height = total_samples // width
            shape = (height, width)
        self._waterfall_shape = shape
        return shape

    @property
    def waterfall(self) -> np.memmap:
        if self._waterfall is None:
            shape = self.waterfall_shape()
            self._waterfall = np.memmap(
                self._waterfall_path(), dtype=np.int16, mode="r", shape=shape
            )
        return self._waterfall

    # ------------------------------------------------------------------
    def list_curves(self) -> Iterable[str]:
        return self.summary.keys()

    # ------------------------------------------------------------------
    def _window_indices(
        self, axis: np.ndarray, start: Optional[float], end: Optional[float]
    ) -> Tuple[int, int]:
        if start is None:
            lo = 0
        else:
            lo = int(np.searchsorted(axis, start, side="left"))
        if end is None:
            hi = len(axis)
        else:
            hi = int(np.searchsorted(axis, end, side="right"))
        hi = max(hi, lo + 1)
        lo = max(0, min(lo, len(axis) - 1))
        hi = min(hi, len(axis))
        return lo, hi

    def _resample_axis(
        self, data: np.ndarray, axis: int, max_samples: Optional[int]
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        if max_samples is None or max_samples <= 0:
            return data, None
        length = data.shape[axis]
        if length <= max_samples:
            return data, None
        indices = np.linspace(0, length, num=max_samples, endpoint=False, dtype=int)
        indices = np.clip(indices, 0, length - 1)
        resampled = np.take(data, indices, axis=axis)
        return resampled, indices

    # ------------------------------------------------------------------
    def summary_slice(
        self,
        f0: Optional[float],
        f1: Optional[float],
        max_points: Optional[int] = None,
    ) -> Dict[str, np.ndarray]:
        freqs = self.freqs
        lo, hi = self._window_indices(freqs, f0, f1)
        window = freqs[lo:hi]
        subset = {key: values[lo:hi] for key, values in self.summary.items()}
        window_ds = window
        if max_points and window.shape[0] > max_points:
            window_ds = np.linspace(window[0], window[-1], max_points)
            subset = {
                key: np.interp(window_ds, window, values)
                for key, values in subset.items()
            }
        return {"freqs": window_ds, **subset}

    def waterfall_tile(
        self,
        f0: Optional[float],
        f1: Optional[float],
        t0: Optional[float],
        t1: Optional[float],
        maxw: Optional[int],
        maxt: Optional[int],
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        freqs = self.freqs
        times = self.times
        freq_lo, freq_hi = self._window_indices(freqs, f0, f1)
        time_lo, time_hi = self._window_indices(times, t0, t1)

        tile = self.waterfall[time_lo:time_hi, freq_lo:freq_hi]
        tile = np.asarray(tile, dtype=np.float32)

        # Resample time axis first (axis=0)
        tile_t, t_indices = self._resample_axis(tile, axis=0, max_samples=maxt)
        time_axis = times[time_lo:time_hi]
        if t_indices is not None:
            time_axis = np.take(time_axis, t_indices, axis=0)
        else:
            time_axis = time_axis

        # Resample frequency axis (axis=1)
        tile_tf, f_indices = self._resample_axis(tile_t, axis=1, max_samples=maxw)
        freq_axis = freqs[freq_lo:freq_hi]
        if f_indices is not None:
            freq_axis = np.take(freq_axis, f_indices, axis=0)
        else:
            freq_axis = freq_axis

        return tile_tf, time_axis, freq_axis

    # ------------------------------------------------------------------
    def peak_candidates(
        self,
        curve: str,
        f0: Optional[float],
        f1: Optional[float],
        **find_kwargs: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        summary = self.summary_slice(f0=f0, f1=f1, max_points=None)
        if curve not in summary:
            raise KeyError(f"Curve '{curve}' not found in summary")
        freqs = summary["freqs"]
        values = summary[curve]
        return freqs, values

    # ------------------------------------------------------------------
    def markers_path(self) -> Path:
        return self.root / f"markers_{self.band_id}.json"

    def load_markers(self) -> List[Mapping[str, object]]:
        path = self.markers_path()
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def save_markers(self, markers: List[Mapping[str, object]]) -> None:
        path = self.markers_path()
        with path.open("w", encoding="utf-8") as fh:
            json.dump(markers, fh, indent=2)


class DatasetService:
    """Coordinates access to datasets stored on disk."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self._band_cache: Dict[str, BandDataset] = {}

    def available_bands(self) -> List[BandInfo]:
        bands: List[BandInfo] = []
        pattern = "meta_*.json"
        for meta_path in self.data_dir.glob(pattern):
            band_id = meta_path.stem.replace("meta_", "")
            dataset = self.get_band(band_id)
            bands.append(BandInfo(band_id=band_id, meta=dataset.meta))
        return sorted(bands, key=lambda info: info.band_id)

    @lru_cache(maxsize=128)
    def _get_cached_band(self, band_id: str) -> BandDataset:
        if band_id not in self._band_cache:
            band = BandDataset(band_id=band_id, root=self.data_dir)
            self._band_cache[band_id] = band
        return self._band_cache[band_id]

    def get_band(self, band_id: str) -> BandDataset:
        return self._get_cached_band(band_id)


_service: Optional[DatasetService] = None


def get_dataset_service() -> DatasetService:
    global _service
    if _service is None:
        _service = DatasetService()
    return _service
