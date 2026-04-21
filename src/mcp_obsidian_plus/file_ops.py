"""File operations: rename, move, batch-rename — composed on top of REST CRUD."""
from __future__ import annotations

from typing import Any

from . import obsidian, knowledge


def rename_file(api: obsidian.Obsidian, from_path: str, to_path: str, update_backlinks: bool = True) -> dict:
    """Rename a file atomically:
    1. Copy content to new path
    2. (Optional) rewrite all `[[from]]` → `[[to]]` in other notes
    3. Delete old file

    If step 2 fails mid-way, files are left in inconsistent state (no transactions in REST API).
    """
    content = api.get_file_contents(from_path)
    api.put_content(to_path, content)
    refactor_report: dict | None = None
    if update_backlinks:
        try:
            refactor_report = knowledge.refactor_links(api, from_path, to_path)
        except Exception as e:
            refactor_report = {"error": str(e)}
    api.delete_file(from_path)
    return {
        "from": from_path,
        "to": to_path,
        "update_backlinks": update_backlinks,
        "refactor_report": refactor_report,
    }


def move_file(api: obsidian.Obsidian, from_path: str, to_folder: str, update_backlinks: bool = True) -> dict:
    """Move a file to a new folder, preserving filename."""
    filename = from_path.rsplit("/", 1)[-1]
    to_path = f"{to_folder.rstrip('/')}/{filename}"
    return rename_file(api, from_path, to_path, update_backlinks=update_backlinks)


def batch_rename(api: obsidian.Obsidian, renames: list[dict], update_backlinks: bool = True) -> dict:
    """Rename multiple files. `renames` is a list of {from, to} pairs.

    Per-item errors don't abort; each gets its own result. Backlink updates are done after
    each rename to keep links consistent through the batch.
    """
    results = []
    for item in renames:
        f = item.get("from")
        t = item.get("to")
        if not f or not t:
            results.append({"error": "each item must have 'from' and 'to'", "item": item})
            continue
        try:
            r = rename_file(api, f, t, update_backlinks=update_backlinks)
            results.append(r)
        except Exception as e:
            results.append({"from": f, "to": t, "error": str(e)})
    return {"count": len(renames), "results": results}
