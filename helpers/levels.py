# lazy so i vibecoded this file quite a bit

from __future__ import annotations

import gzip
import json
import os
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image

import sonolus_converters

from helpers.background import render_png
from helpers.repository import repo


# -----------------------------
# Folder name normalization
# -----------------------------


def normalize_folder_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_")


# -----------------------------
# Score handling (merged)
# -----------------------------


def convert_score_to_cache(score_path: Path, out_path_no_ext: Path) -> bool:
    """
    Convert `score_path` into NextSekai LevelData and write to `out_path_no_ext`
    (NO extension). Returns True if conversion succeeded, else False.

    Special cases for lvd:
      - ("lvd", "compress_pysekai") -> write raw bytes as-is (already compressed)
      - ("lvd", "pysekai")          -> gzip the raw bytes and write to out_path_no_ext
    """
    out_path_no_ext.parent.mkdir(parents=True, exist_ok=True)

    try:
        data = score_path.read_bytes()
    except Exception as e:
        print("".join(traceback.format_exception(e, e, e.__traceback__)))
        return False

    # Standardize detect() to bytes
    try:
        detection = sonolus_converters.detect(data)
    except Exception as e:
        print("".join(traceback.format_exception(e, e, e.__traceback__)))
        return False

    if not detection:
        return False

    try:
        kind = detection[0]

        if kind == "sus":
            score = sonolus_converters.sus.load(score_path.open("r"))
            sonolus_converters.LevelData.next_sekai.export(
                out_path_no_ext, score, as_compressed=True
            )
            return True

        if kind == "mmw":
            score = sonolus_converters.mmws.load(score_path.open("r"))
            sonolus_converters.LevelData.next_sekai.export(
                out_path_no_ext, score, as_compressed=True
            )
            return True

        if kind == "usc":
            score = sonolus_converters.usc.load(score_path.open("r"))
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
        print("".join(traceback.format_exception(e, e, e.__traceback__)))
        return False


def is_valid_score_file(score_path: Path) -> bool:
    """
    Valid if it can be detected AND converted successfully.
    (This intentionally performs conversion work.)
    """
    dummy_out = Path("levels_cache") / "__detect_tmp__" / "converted_score"
    ok = convert_score_to_cache(score_path, dummy_out)
    if ok:
        try:
            dummy_out.unlink(missing_ok=True)
        except Exception:
            pass
    return ok


# -----------------------------
# Cache helpers
# -----------------------------


def _ensure_cache_json(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "cache.json"
    if not cache_path.exists():
        cache_path.write_text(
            json.dumps({"mtimes": {}, "folders": {}}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return cache_path


def _load_cache(cache_path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("mtimes", {})
    data.setdefault("folders", {})
    return data


def _save_cache(cache_path: Path, cache: Dict[str, Any]) -> None:
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def _safe_mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _scan_mtimes(levels_dir: Path) -> Dict[str, float]:
    """
    Store last-modified timestamps for EVERY file and directory under levels/.
    Keys are posix relative paths from levels/ (root is ".").
    """
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
# Sticky selection helpers
# -----------------------------


def _keep_cached_or_pick_first(
    levels_dir: Path,
    folder_dir: Path,
    cached_rel: Optional[str],
    *,
    suffix: Optional[str] = None,
    predicate=None,
) -> Optional[Path]:
    """
    Sticky behavior:
      - if cached_rel exists and file still exists, keep it
      - else select the first matching file (sorted by name)
    """
    if cached_rel:
        cached_abs = levels_dir / cached_rel
        if cached_abs.exists():
            return cached_abs

    files = [p for p in folder_dir.iterdir() if p.is_file()]
    if suffix is not None:
        files = [p for p in files if p.suffix.lower() == suffix.lower()]
    if predicate is not None:
        files = [p for p in files if predicate(p)]

    files.sort(key=lambda p: p.name.lower())
    return files[0] if files else None


# -----------------------------
# Repo map mutation (your request)
# -----------------------------


def _repo_has_hash(h: Optional[str]) -> bool:
    if not h:
        return False
    m = getattr(repo, "_map", None)
    if m is None:
        return False
    try:
        return h in m
    except TypeError:
        return False


def _repo_is_empty() -> bool:
    m = getattr(repo, "_map", None)
    if m is None:
        return False
    try:
        return len(m) == 0
    except TypeError:
        return False


def _repo_del_hash(h: Optional[str]) -> None:
    """
    Directly delete from repo._map as requested.
    Guarded so restarts / missing keys don't crash.
    """
    if not h:
        return
    m = getattr(repo, "_map", None)
    if m is None:
        return
    try:
        del m[h]
    except KeyError:
        pass


# -----------------------------
# Main loader
# -----------------------------


def load_levels_directory(
    bg_version: str,
    levels_dir: str | Path = "levels",
    levels_cache_dir: str | Path = "levels_cache",
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Returns hashes only, keyed by NORMALIZED folder name:
      {
        "<normalized>": {
          "normalized": "<normalized>",
          "name": "<actual folder name>",
          "score": "<converted_score_hash or None>",
          "cover": "<cover_hash or None>",
          "background": "<background_hash or None>",
          "music": "<music_hash or None>",
        }
      }

    Rules:
      - Sticky selection per folder: keep old chosen file until it is deleted.
      - Score: do NOT add original score; generate `levels_cache/<normalized>/converted_score` (no ext)
        and add THAT to repo.
      - Cover: add original cover to repo. If cover updated, regenerate background at
        `levels_cache/<normalized>/background.png` and add that too.
      - Music: add original mp3 to repo.
      - Restart-safe: if repo._map doesn't contain a cached hash (or repo is empty),
        re-add/regenerate as needed even if folder mtimes didn't change.
      - Duplicate normalized names: last one wins (overwrites), assumed not to happen.
    """
    levels_dir = Path(levels_dir)
    levels_cache_dir = Path(levels_cache_dir)
    levels_dir.mkdir(parents=True, exist_ok=True)
    levels_cache_dir.mkdir(parents=True, exist_ok=True)

    cache_path = _ensure_cache_json(levels_cache_dir)
    cache = _load_cache(cache_path)

    old_mtimes: Dict[str, float] = dict(cache.get("mtimes", {}))
    new_mtimes = _scan_mtimes(levels_dir)

    # cache is now keyed by normalized name
    folders_cache: Dict[str, Any] = cache.get("folders", {})
    out: Dict[str, Dict[str, Optional[str]]] = {}

    repo_empty = _repo_is_empty()

    for folder_dir in sorted(
        (p for p in levels_dir.iterdir() if p.is_dir()), key=lambda p: p.name.lower()
    ):
        actual_name = folder_dir.name
        norm_name = normalize_folder_name(actual_name)

        folder_state: Dict[str, Any] = folders_cache.get(norm_name, {})
        folder_state["name"] = (
            actual_name  # keep latest actual name for this normalized key
        )

        # --- sticky selections in levels/<folder> ---
        score_path = _keep_cached_or_pick_first(
            levels_dir,
            folder_dir,
            folder_state.get("score_rel"),
            suffix=None,
            predicate=is_valid_score_file,
        )
        cover_path = _keep_cached_or_pick_first(
            levels_dir,
            folder_dir,
            folder_state.get("cover_rel"),
            suffix=".png",
        )
        music_path = _keep_cached_or_pick_first(
            levels_dir,
            folder_dir,
            folder_state.get("music_rel"),
            suffix=".mp3",
        )

        rel_score = (
            score_path.relative_to(levels_dir).as_posix() if score_path else None
        )
        rel_cover = (
            cover_path.relative_to(levels_dir).as_posix() if cover_path else None
        )
        rel_music = (
            music_path.relative_to(levels_dir).as_posix() if music_path else None
        )

        # selection changed if rel path differs from cached rel
        score_selection_changed = rel_score != folder_state.get("score_rel")
        cover_selection_changed = rel_cover != folder_state.get("cover_rel")
        music_selection_changed = rel_music != folder_state.get("music_rel")

        # file mtime changed if the selected file's mtime differs from old snapshot
        score_mtime_changed = False
        cover_mtime_changed = False
        music_mtime_changed = False

        if rel_score:
            score_mtime_changed = old_mtimes.get(rel_score) != new_mtimes.get(rel_score)
        if rel_cover:
            cover_mtime_changed = old_mtimes.get(rel_cover) != new_mtimes.get(rel_cover)
        if rel_music:
            music_mtime_changed = old_mtimes.get(rel_music) != new_mtimes.get(rel_music)

        score_updated = score_selection_changed or score_mtime_changed
        cover_updated = cover_selection_changed or cover_mtime_changed
        music_updated = music_selection_changed or music_mtime_changed

        # generated output paths under levels_cache/<normalized>/
        folder_cache_dir = levels_cache_dir / norm_name
        converted_score_path = folder_cache_dir / "converted_score"  # no extension
        background_path = folder_cache_dir / "background.png"

        # cached hashes
        cover_hash = folder_state.get("cover_hash")
        background_hash = folder_state.get("background_hash")
        music_hash = folder_state.get("music_hash")
        converted_score_hash = folder_state.get("converted_score_hash")

        # restart-safety: warm if hash missing from repo._map (or repo is empty)
        cover_needs_warm = (cover_hash is not None) and (
            repo_empty or not _repo_has_hash(cover_hash)
        )
        bg_needs_warm = (background_hash is not None) and (
            repo_empty or not _repo_has_hash(background_hash)
        )
        music_needs_warm = (music_hash is not None) and (
            repo_empty or not _repo_has_hash(music_hash)
        )
        score_needs_warm = (converted_score_hash is not None) and (
            repo_empty or not _repo_has_hash(converted_score_hash)
        )

        # also warm/regenerate if generated files missing
        if cover_path and cover_path.exists() and not background_path.exists():
            cover_updated = True
        if score_path and score_path.exists() and not converted_score_path.exists():
            score_updated = True

        # --- COVER (as-is) ---
        if cover_path and cover_path.exists():
            if cover_updated or cover_needs_warm or cover_hash is None:
                if cover_hash:
                    _repo_del_hash(cover_hash)
                cover_hash = repo.add_file(str(cover_path))
                folder_state["cover_hash"] = cover_hash
            folder_state["cover_rel"] = rel_cover
        else:
            if cover_hash:
                _repo_del_hash(cover_hash)
            folder_state["cover_hash"] = None
            folder_state["cover_rel"] = None
            cover_hash = None

        # --- BACKGROUND (generated from cover) ---
        if cover_path and cover_path.exists():
            if cover_updated:
                folder_cache_dir.mkdir(parents=True, exist_ok=True)
                with Image.open(cover_path) as im:
                    im = im.convert("RGBA")
                    bg = render_png(bg_version, im)
                    bg.save(background_path, format="PNG")

            if cover_updated or bg_needs_warm or background_hash is None:
                if background_hash:
                    _repo_del_hash(background_hash)
                background_hash = (
                    repo.add_file(str(background_path))
                    if background_path.exists()
                    else None
                )
                folder_state["background_hash"] = background_hash
        else:
            if background_hash:
                _repo_del_hash(background_hash)
            folder_state["background_hash"] = None
            background_hash = None

        # --- MUSIC (as-is) ---
        if music_path and music_path.exists():
            if music_updated or music_needs_warm or music_hash is None:
                if music_hash:
                    _repo_del_hash(music_hash)
                music_hash = repo.add_file(str(music_path))
                folder_state["music_hash"] = music_hash
            folder_state["music_rel"] = rel_music
        else:
            if music_hash:
                _repo_del_hash(music_hash)
            folder_state["music_hash"] = None
            folder_state["music_rel"] = None
            music_hash = None

        # --- SCORE (converted file only) ---
        if score_path and score_path.exists():
            if score_updated:
                ok = convert_score_to_cache(score_path, converted_score_path)
                if not ok:
                    # became invalid; keep previous sticky until they delete it
                    score_updated = False

            if score_updated or score_needs_warm or converted_score_hash is None:
                if converted_score_hash:
                    _repo_del_hash(converted_score_hash)
                converted_score_hash = (
                    repo.add_file(str(converted_score_path))
                    if converted_score_path.exists()
                    else None
                )
                folder_state["converted_score_hash"] = converted_score_hash

            folder_state["score_rel"] = rel_score
        else:
            if converted_score_hash:
                _repo_del_hash(converted_score_hash)
            folder_state["converted_score_hash"] = None
            folder_state["score_rel"] = None
            converted_score_hash = None

        # save folder state under normalized key
        folders_cache[norm_name] = folder_state

        # public output = normalized key + hashes + actual name
        out[norm_name] = {
            "normalized": norm_name,
            "name": actual_name,
            "score": converted_score_hash,
            "cover": cover_hash,
            "background": background_hash,
            "music": music_hash,
        }

    # persist new mtimes snapshot + folder states
    cache["mtimes"] = new_mtimes
    cache["folders"] = folders_cache
    _save_cache(cache_path, cache)

    return out
