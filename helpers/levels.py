# lazy so i vibecoded this file quite a bit

from __future__ import annotations

import gzip
import json
import os
import uuid
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image

import sonolus_converters

from helpers.background import render_png
from helpers.repository import repo


# -----------------------------
# Score handling (single pass)
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
    """
    Only consider these extensions for chart/score files:
      sus, usc, .json, .gz, .mmws, .ccmmws, .unchmmws, NO EXTENSION
    """
    if not path.is_file():
        return False
    # suffix includes the dot; for no-extension it's ""
    return path.suffix.lower() in _SCORE_EXTS


def convert_score_to_cache(score_path: Path, out_path_no_ext: Path) -> bool:
    """
    Convert `score_path` into NextSekai LevelData and write to `out_path_no_ext`
    (NO extension). Returns True if conversion succeeded, else False.

    Special cases for lvd:
      - ("lvd", "compress_pysekai") -> write raw bytes as-is (already compressed)
      - ("lvd", "pysekai")          -> gzip the raw bytes and write to out_path_no_ext

    IMPORTANT: opens score file in read mode (file object), not read_bytes().
    """
    out_path_no_ext.parent.mkdir(parents=True, exist_ok=True)

    try:
        with score_path.open("rb") as f:
            data = f.read()
    except Exception as e:
        print("".join(traceback.format_exception(e, e, e.__traceback__)))
        return False

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
            with score_path.open("r") as fp:
                score = sonolus_converters.sus.load(fp)
            sonolus_converters.LevelData.next_sekai.export(
                out_path_no_ext, score, as_compressed=True
            )
            return True

        if kind == "mmw":
            with score_path.open("r") as fp:
                score = sonolus_converters.mmws.load(fp)
            sonolus_converters.LevelData.next_sekai.export(
                out_path_no_ext, score, as_compressed=True
            )
            return True

        if kind == "usc":
            with score_path.open("r") as fp:
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
        print("".join(traceback.format_exception(e, e, e.__traceback__)))
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
                {"mtimes": {}, "folders": {}, "folder_ids": {}},
                indent=2,
                sort_keys=True,
            ),
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
    data.setdefault("folder_ids", {})  # actual folder name -> uuid string
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
    suffixes: Optional[set[str]] = None,
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
    if suffixes is not None:
        files = [p for p in files if p.suffix.lower() in suffixes]
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
    Returns hashes only, keyed by *actual folder name*, but also includes a stable UUID id
    so any folder name is allowed (no normalization, no conflicts):

      {
        "<folder name>": {
          "id": "<uuid>",
          "score": "<converted_score_hash or None>",
          "cover": "<cover_hash or None>",
          "background": "<background_hash or None>",
          "music": "<music_hash or None>",
        }
      }

    Rules:
      - Sticky selection per folder: keep old chosen file until it is deleted.
      - Score: do NOT add original score; convert to `levels_cache/<id>/converted_score` (no ext)
        and add THAT to repo.
      - Cover: accept .png/.jpg/.jpeg; add original cover to repo. If cover updated,
        regenerate background at `levels_cache/<id>/background.png` and add that too.
      - Music: accept .mp3/.ogg; add original to repo.
      - Restart-safe: if repo._map doesn't contain a cached hash (or repo is empty),
        re-add/regenerate as needed even if folder mtimes didn't change.
      - Score selection does NOT do a separate "is_valid" pass; conversion is attempted only
        when needed and success determines validity.
    """
    levels_dir = Path(levels_dir)
    levels_cache_dir = Path(levels_cache_dir)

    cache_path = _ensure_cache_json(levels_cache_dir)
    cache = _load_cache(cache_path)

    old_mtimes: Dict[str, float] = dict(cache.get("mtimes", {}))
    new_mtimes = _scan_mtimes(levels_dir)

    # folders state keyed by UUID
    folders_cache: Dict[str, Any] = cache.get("folders", {})
    # mapping from actual folder name -> uuid string
    folder_ids: Dict[str, str] = cache.get("folder_ids", {})

    out: Dict[str, Dict[str, Optional[str]]] = {}
    repo_empty = _repo_is_empty()

    cover_suffixes = {".png", ".jpg", ".jpeg"}
    music_suffixes = {".mp3", ".ogg"}

    for folder_dir in sorted(
        (p for p in levels_dir.iterdir() if p.is_dir()), key=lambda p: p.name.lower()
    ):
        folder_name = folder_dir.name

        # assign stable UUID per folder name (persisted)
        folder_id = folder_ids.get(folder_name)
        if not folder_id:
            folder_id = str(uuid.uuid4())
            folder_ids[folder_name] = folder_id

        folder_state: Dict[str, Any] = folders_cache.get(folder_id, {})
        folder_state["name"] = folder_name  # for debugging / traceability

        # --- sticky selections in levels/<folder> ---
        # Score: pick by cached rel or first file whose extension is in _SCORE_EXTS
        score_path = _keep_cached_or_pick_first(
            levels_dir,
            folder_dir,
            folder_state.get("score_rel"),
            suffixes=None,
            predicate=_is_candidate_score_file,
        )
        cover_path = _keep_cached_or_pick_first(
            levels_dir,
            folder_dir,
            folder_state.get("cover_rel"),
            suffixes=cover_suffixes,
        )
        music_path = _keep_cached_or_pick_first(
            levels_dir,
            folder_dir,
            folder_state.get("music_rel"),
            suffixes=music_suffixes,
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

        # generated output paths under levels_cache/<id>/
        folder_cache_dir = levels_cache_dir / folder_id
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

        # --- BACKGROUND (generated from cover; accepts png/jpg/jpeg) ---
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

        # --- MUSIC (as-is; mp3/ogg) ---
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

        # --- SCORE (convert+hash in one step; no separate validity check) ---
        if score_path and score_path.exists():
            if score_updated:
                ok = convert_score_to_cache(score_path, converted_score_path)
                if not ok:
                    # invalid; keep previous sticky choice until they delete it
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

        # save folder state under UUID
        folders_cache[folder_id] = folder_state

        # public output = actual folder name key + stable id + hashes
        out[folder_name] = {
            "id": folder_id,
            "score": converted_score_hash,
            "cover": cover_hash,
            "background": background_hash,
            "music": music_hash,
        }

    # persist new mtimes snapshot + folder states + name->id map
    cache["mtimes"] = new_mtimes
    cache["folders"] = folders_cache
    cache["folder_ids"] = folder_ids
    _save_cache(cache_path, cache)

    return out
