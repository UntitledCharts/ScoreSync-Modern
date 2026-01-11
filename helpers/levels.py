# lazy so i vibecoded this file quite a bit

from __future__ import annotations

import gzip
import json
import os
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image

import sonolus_converters

from helpers.background import render_png
from helpers.repository import repo


# -----------------------------
# Global: stale-return cache + single-writer gate
# -----------------------------

_LEVELS_SCAN_LOCK = threading.Lock()
_LAST_LEVELS_RESULT: Dict[str, Dict[str, Optional[str]]] = {}
_HAS_LAST_LEVELS_RESULT = False


def _clone_last_result() -> Dict[str, Dict[str, Optional[str]]]:
    return {k: dict(v) for k, v in _LAST_LEVELS_RESULT.items()}


# -----------------------------
# Error printing
# -----------------------------


def _print_exc(e: BaseException) -> None:
    print("".join(traceback.format_exception(e, e, e.__traceback__)))


# -----------------------------
# Repo helpers
# -----------------------------


def _repo_map() -> Optional[dict]:
    return getattr(repo, "_map", None)


def _repo_has_hash(h: Optional[str]) -> bool:
    if not h:
        return False
    m = _repo_map()
    if m is None:
        return False
    return h in m


def _repo_is_empty() -> bool:
    m = _repo_map()
    if m is None:
        return False
    try:
        return len(m) == 0
    except TypeError:
        return False


def _repo_del_hash(h: Optional[str]) -> None:
    """
    Delete from repo._map directly (as requested), but ONLY when:
      - asset confirmed deleted (>10s missing), OR
      - asset confirmed replaced (new hash confirmed)
    """
    if not h:
        return
    m = _repo_map()
    if m is None:
        return
    try:
        del m[h]
    except KeyError:
        pass


# -----------------------------
# Score handling (single pass, convert when needed)
# -----------------------------

_SCORE_EXTS = {
    ".sus",
    ".usc",
    ".json",
    ".gz",
    ".mmws",
    ".ccmmws",
    ".unchmmws",
    "",  # NO EXTENSION
}


def _is_candidate_score_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _SCORE_EXTS


def convert_score_to_cache(score_path: Path, out_path_no_ext: Path) -> bool:
    """
    IMPORTANT (per your requirement): open in read mode ("r"), not read_bytes().
    """
    out_path_no_ext.parent.mkdir(parents=True, exist_ok=True)

    try:
        with score_path.open("r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        data = text.encode("utf-8", errors="ignore")
    except Exception as e:
        _print_exc(e)
        return False

    try:
        detection = sonolus_converters.detect(data)
    except Exception as e:
        _print_exc(e)
        return False

    if not detection:
        return False

    try:
        kind = detection[0]

        if kind == "sus":
            with score_path.open("r", encoding="utf-8", errors="ignore") as fp:
                score = sonolus_converters.sus.load(fp)
            sonolus_converters.LevelData.next_sekai.export(
                out_path_no_ext, score, as_compressed=True
            )
            return True

        if kind == "mmw":
            with score_path.open("r", encoding="utf-8", errors="ignore") as fp:
                score = sonolus_converters.mmws.load(fp)
            sonolus_converters.LevelData.next_sekai.export(
                out_path_no_ext, score, as_compressed=True
            )
            return True

        if kind == "usc":
            with score_path.open("r", encoding="utf-8", errors="ignore") as fp:
                score = sonolus_converters.usc.load(fp)
            sonolus_converters.LevelData.next_sekai.export(
                out_path_no_ext, score, as_compressed=True
            )
            return True

        if kind == "lvd":
            variant = detection[1] if len(detection) > 1 else None

            if variant == "compress_pysekai":
                out_path_no_ext.write_bytes(data)
                return True

            if variant == "pysekai":
                out_path_no_ext.write_bytes(gzip.compress(data))
                return True

            return False

        return False

    except Exception as e:
        _print_exc(e)
        return False


# -----------------------------
# Cache helpers
# -----------------------------


def _ensure_cache_json(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "cache.json"
    if not cache_path.exists():
        cache_path.write_text(
            json.dumps(
                {
                    "mtimes": {},
                    "folders": {},  # uuid -> folder_state
                    "folder_ids": {},  # folder_name -> uuid
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return cache_path


def _load_cache(cache_path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as e:
        _print_exc(e)
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("mtimes", {})
    data.setdefault("folders", {})
    data.setdefault("folder_ids", {})
    return data


def _save_cache(cache_path: Path, cache: Dict[str, Any]) -> None:
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def _safe_mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _scan_mtimes(levels_dir: Path) -> Dict[str, float]:
    mtimes: Dict[str, float] = {}
    root_mtime = _safe_mtime(levels_dir)
    if root_mtime is not None:
        mtimes["."] = float(root_mtime)

    for dirpath, _, filenames in os.walk(levels_dir):
        dpath = Path(dirpath)
        rel_dir = dpath.relative_to(levels_dir).as_posix() or "."
        d_mtime = _safe_mtime(dpath)
        if d_mtime is not None:
            mtimes[rel_dir] = float(d_mtime)

        for name in filenames:
            fpath = dpath / name
            rel_file = fpath.relative_to(levels_dir).as_posix()
            f_mtime = _safe_mtime(fpath)
            if f_mtime is not None:
                mtimes[rel_file] = float(f_mtime)

    return mtimes


# -----------------------------
# Listing helpers (non-sticky for “replacement confirmed”)
# -----------------------------


def _first_matching_file(
    folder_dir: Path, *, suffixes: set[str] | None = None, predicate=None
) -> Optional[Path]:
    try:
        files = [p for p in folder_dir.iterdir() if p.is_file()]
    except Exception:
        return None
    if suffixes is not None:
        files = [p for p in files if p.suffix.lower() in suffixes]
    if predicate is not None:
        files = [p for p in files if predicate(p)]
    files.sort(key=lambda p: p.name.lower())
    return files[0] if files else None


# -----------------------------
# Transient-missing grace logic
# -----------------------------

_GRACE_SECONDS = 10.0


def _missing_key(prefix: str) -> str:
    return f"{prefix}_missing_since"


def _mark_missing(folder_state: Dict[str, Any], prefix: str, now: float) -> None:
    k = _missing_key(prefix)
    if folder_state.get(k) is None:
        folder_state[k] = now


def _clear_missing(folder_state: Dict[str, Any], prefix: str) -> None:
    folder_state.pop(_missing_key(prefix), None)


def _missing_too_long(folder_state: Dict[str, Any], prefix: str, now: float) -> bool:
    since = folder_state.get(_missing_key(prefix))
    if since is None:
        return False
    return (now - float(since)) >= _GRACE_SECONDS


# -----------------------------
# Atomic confirm helpers
# -----------------------------


def _confirm_cover_and_background(
    *,
    cover_path: Path,
    bg_version: str,
    folder_cache_dir: Path,
) -> Optional[Tuple[str, str]]:
    """
    Replacement-confirmation for cover:
      - must be openable by Pillow (so file is fully written / not corrupt)
      - background generation must succeed
      - both cover and background must be add_file()'d successfully

    Returns (cover_hash, background_hash) on success, else None.
    """
    try:
        folder_cache_dir.mkdir(parents=True, exist_ok=True)

        # confirm image is readable and fully written
        with Image.open(cover_path) as im:
            im = im.convert("RGBA")
            bg = render_png(bg_version, im)

        background_path = folder_cache_dir / "background.png"

        # write background
        try:
            bg.save(background_path, format="PNG")
        except Exception as e:
            _print_exc(e)
            return None

        # repo add_file confirmations
        cover_hash = repo.add_file(str(cover_path))
        bg_hash = repo.add_file(str(background_path))
        return cover_hash, bg_hash

    except Exception as e:
        _print_exc(e)
        return None


def _confirm_music(*, music_path: Path) -> Optional[str]:
    try:
        return repo.add_file(str(music_path))
    except Exception as e:
        _print_exc(e)
        return None


def _confirm_score(*, score_path: Path, converted_score_path: Path) -> Optional[str]:
    try:
        ok = convert_score_to_cache(score_path, converted_score_path)
        if not ok or not converted_score_path.exists():
            return None
        return repo.add_file(str(converted_score_path))
    except Exception as e:
        _print_exc(e)
        return None


# -----------------------------
# Main loader (sync, stale-while-running)
# -----------------------------


def load_levels_directory(
    bg_version: str,
    levels_dir: str | Path = "levels",
    levels_cache_dir: str | Path = "levels_cache",
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Concurrency:
      - If another call is running, return LAST COMPLETED snapshot immediately (stale).

    Replacement / delete semantics (cover, background, music, score):
      - If file disappears (no candidate exists), KEEP returning old hashes and keep them in repo._map.
      - If missing persists for >10s, then drop hashes (return None) AND delete those hashes from repo._map.
      - If replacement is confirmed (new file exists AND is usable), swap immediately and delete OLD hashes
        from repo._map ONLY AFTER the NEW hashes are confirmed.
    """
    global _HAS_LAST_LEVELS_RESULT, _LAST_LEVELS_RESULT

    if not _LEVELS_SCAN_LOCK.acquire(blocking=False):
        return _clone_last_result() if _HAS_LAST_LEVELS_RESULT else {}

    try:
        now = time.time()

        levels_dir = Path(levels_dir)
        levels_cache_dir = Path(levels_cache_dir)

        cache_path = _ensure_cache_json(levels_cache_dir)
        cache = _load_cache(cache_path)

        old_mtimes: Dict[str, float] = dict(cache.get("mtimes", {}))
        new_mtimes = _scan_mtimes(levels_dir)

        folders_cache: Dict[str, Any] = cache.get("folders", {})
        folder_ids: Dict[str, str] = cache.get("folder_ids", {})

        out: Dict[str, Dict[str, Optional[str]]] = {}
        repo_empty = _repo_is_empty()

        cover_suffixes = {".png", ".jpg", ".jpeg"}
        music_suffixes = {".mp3", ".ogg"}

        for folder_dir in sorted(
            (p for p in levels_dir.iterdir() if p.is_dir()),
            key=lambda p: p.name.lower(),
        ):
            folder_name = folder_dir.name

            # stable UUID per folder name
            folder_id = folder_ids.get(folder_name)
            if not folder_id:
                folder_id = str(uuid.uuid4())
                folder_ids[folder_name] = folder_id

            folder_state: Dict[str, Any] = folders_cache.get(folder_id, {})
            folder_state["name"] = folder_name

            folder_cache_dir = levels_cache_dir / folder_id
            converted_score_path = folder_cache_dir / "converted_score"

            # ----- load current "committed" values -----
            cover_rel = folder_state.get("cover_rel")
            cover_hash = folder_state.get("cover_hash")
            bg_hash = folder_state.get("background_hash")

            music_rel = folder_state.get("music_rel")
            music_hash = folder_state.get("music_hash")

            score_rel = folder_state.get("score_rel")
            score_hash = folder_state.get("converted_score_hash")

            # ----- determine candidates right now -----
            # If the old committed rel exists, prefer it as the candidate; otherwise pick the first available.
            committed_cover_path = (levels_dir / cover_rel) if cover_rel else None
            cover_candidate = (
                committed_cover_path
                if (committed_cover_path and committed_cover_path.exists())
                else _first_matching_file(folder_dir, suffixes=cover_suffixes)
            )

            committed_music_path = (levels_dir / music_rel) if music_rel else None
            music_candidate = (
                committed_music_path
                if (committed_music_path and committed_music_path.exists())
                else _first_matching_file(folder_dir, suffixes=music_suffixes)
            )

            committed_score_path = (levels_dir / score_rel) if score_rel else None
            score_candidate = (
                committed_score_path
                if (committed_score_path and committed_score_path.exists())
                else _first_matching_file(
                    folder_dir, predicate=_is_candidate_score_file
                )
            )

            # ----- COVER+BACKGROUND: gap-safe state machine -----
            if cover_candidate is None:
                # nothing exists right now => treat as missing (gap or delete)
                if cover_hash is not None:
                    _mark_missing(folder_state, "cover", now)
                    _mark_missing(folder_state, "background", now)

                    if _missing_too_long(folder_state, "cover", now):
                        # delete confirmed => drop & delete from repo map
                        _repo_del_hash(cover_hash)
                        if bg_hash:
                            _repo_del_hash(bg_hash)
                        cover_hash = None
                        bg_hash = None
                        cover_rel = None
                        folder_state["cover_hash"] = None
                        folder_state["background_hash"] = None
                        folder_state["cover_rel"] = None
                        _clear_missing(folder_state, "cover")
                        _clear_missing(folder_state, "background")
                    else:
                        # gap => KEEP old hashes/rel; do NOT touch repo._map
                        pass
                else:
                    # nothing committed and nothing present
                    cover_hash = None
                    bg_hash = None
                    cover_rel = None
                    folder_state["cover_hash"] = None
                    folder_state["background_hash"] = None
                    folder_state["cover_rel"] = None

            else:
                # something exists => attempt replacement confirmation if needed
                _clear_missing(folder_state, "cover")
                _clear_missing(folder_state, "background")

                candidate_rel = cover_candidate.relative_to(levels_dir).as_posix()

                candidate_mtime_changed = (
                    candidate_rel in new_mtimes
                    and old_mtimes.get(candidate_rel) != new_mtimes.get(candidate_rel)
                )
                needs_warm = (cover_hash is not None) and (
                    repo_empty or not _repo_has_hash(cover_hash)
                )

                # decide if we should attempt a confirm swap:
                # - different file than committed, OR
                # - same file but mtime changed, OR
                # - repo warm needed, OR
                # - no committed hash yet
                should_confirm = (
                    (candidate_rel != cover_rel)
                    or candidate_mtime_changed
                    or needs_warm
                    or (cover_hash is None)
                    or (bg_hash is None)
                )

                if should_confirm:
                    confirmed = _confirm_cover_and_background(
                        cover_path=cover_candidate,
                        bg_version=bg_version,
                        folder_cache_dir=folder_cache_dir,
                    )
                    if confirmed is not None:
                        new_cover_hash, new_bg_hash = confirmed

                        # replacement confirmed => NOW delete old hashes (only now)
                        if cover_hash and cover_hash != new_cover_hash:
                            _repo_del_hash(cover_hash)
                        if bg_hash and bg_hash != new_bg_hash:
                            _repo_del_hash(bg_hash)

                        cover_hash = new_cover_hash
                        bg_hash = new_bg_hash
                        cover_rel = candidate_rel

                        folder_state["cover_hash"] = cover_hash
                        folder_state["background_hash"] = bg_hash
                        folder_state["cover_rel"] = cover_rel
                    else:
                        # not confirmed yet (file incomplete) => keep old hashes/rel
                        # do NOT start missing timer because "a file exists" (replacement in progress)
                        pass
                else:
                    # committed cover still valid; ensure background is present in repo if needed
                    pass

            # ----- MUSIC: gap-safe -----
            if music_candidate is None:
                if music_hash is not None:
                    _mark_missing(folder_state, "music", now)
                    if _missing_too_long(folder_state, "music", now):
                        _repo_del_hash(music_hash)
                        music_hash = None
                        music_rel = None
                        folder_state["music_hash"] = None
                        folder_state["music_rel"] = None
                        _clear_missing(folder_state, "music")
                    else:
                        pass
                else:
                    music_hash = None
                    music_rel = None
                    folder_state["music_hash"] = None
                    folder_state["music_rel"] = None
            else:
                _clear_missing(folder_state, "music")
                candidate_rel = music_candidate.relative_to(levels_dir).as_posix()
                candidate_mtime_changed = (
                    candidate_rel in new_mtimes
                    and old_mtimes.get(candidate_rel) != new_mtimes.get(candidate_rel)
                )
                needs_warm = (music_hash is not None) and (
                    repo_empty or not _repo_has_hash(music_hash)
                )
                should_confirm = (
                    (candidate_rel != music_rel)
                    or candidate_mtime_changed
                    or needs_warm
                    or (music_hash is None)
                )

                if should_confirm:
                    new_hash = _confirm_music(music_path=music_candidate)
                    if new_hash is not None:
                        if music_hash and music_hash != new_hash:
                            _repo_del_hash(music_hash)
                        music_hash = new_hash
                        music_rel = candidate_rel
                        folder_state["music_hash"] = music_hash
                        folder_state["music_rel"] = music_rel
                    else:
                        # not confirmed => keep old
                        pass

            # ----- SCORE: gap-safe -----
            if score_candidate is None:
                if score_hash is not None:
                    _mark_missing(folder_state, "score", now)
                    if _missing_too_long(folder_state, "score", now):
                        _repo_del_hash(score_hash)
                        score_hash = None
                        score_rel = None
                        folder_state["converted_score_hash"] = None
                        folder_state["score_rel"] = None
                        _clear_missing(folder_state, "score")
                    else:
                        pass
                else:
                    score_hash = None
                    score_rel = None
                    folder_state["converted_score_hash"] = None
                    folder_state["score_rel"] = None
            else:
                _clear_missing(folder_state, "score")
                candidate_rel = score_candidate.relative_to(levels_dir).as_posix()
                candidate_mtime_changed = (
                    candidate_rel in new_mtimes
                    and old_mtimes.get(candidate_rel) != new_mtimes.get(candidate_rel)
                )
                needs_warm = (score_hash is not None) and (
                    repo_empty or not _repo_has_hash(score_hash)
                )
                should_confirm = (
                    (candidate_rel != score_rel)
                    or candidate_mtime_changed
                    or needs_warm
                    or (score_hash is None)
                )

                if should_confirm:
                    new_hash = _confirm_score(
                        score_path=score_candidate,
                        converted_score_path=converted_score_path,
                    )
                    if new_hash is not None:
                        if score_hash and score_hash != new_hash:
                            _repo_del_hash(score_hash)
                        score_hash = new_hash
                        score_rel = candidate_rel
                        folder_state["converted_score_hash"] = score_hash
                        folder_state["score_rel"] = score_rel
                    else:
                        # not confirmed => keep old
                        pass

            # save folder state
            folders_cache[folder_id] = folder_state

            # IMPORTANT: return committed state (never transient locals)
            out[folder_name] = {
                "id": folder_id,
                "score": folder_state.get("converted_score_hash"),
                "cover": folder_state.get("cover_hash"),
                "background": folder_state.get("background_hash"),
                "music": folder_state.get("music_hash"),
            }

        cache["mtimes"] = new_mtimes
        cache["folders"] = folders_cache
        cache["folder_ids"] = folder_ids
        _save_cache(cache_path, cache)

        _LAST_LEVELS_RESULT = out
        _HAS_LAST_LEVELS_RESULT = True
        return _clone_last_result()

    except Exception as e:
        _print_exc(e)
        return _clone_last_result() if _HAS_LAST_LEVELS_RESULT else {}

    finally:
        _LEVELS_SCAN_LOCK.release()
