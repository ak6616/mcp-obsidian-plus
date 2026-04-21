"""Knowledge-base operations built on top of the REST client.

These compose multiple REST calls into higher-level workflows:
- tag add/remove via frontmatter rewrite
- backlink search
- link refactoring
- Map of Content generation
"""
from __future__ import annotations

import re
import yaml
from typing import Any

from . import obsidian


_FRONTMATTER_DELIM = "---"


def _split_frontmatter(markdown: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a markdown string. Returns (frontmatter_dict, body).

    Empty frontmatter dict if none present.
    """
    if not markdown.startswith(_FRONTMATTER_DELIM):
        return {}, markdown
    # Find the closing delimiter
    rest = markdown[len(_FRONTMATTER_DELIM):]
    # Must be followed by newline
    if not rest.startswith("\n"):
        return {}, markdown
    rest = rest[1:]  # consume the \n
    end = rest.find(f"\n{_FRONTMATTER_DELIM}\n")
    if end < 0:
        # Last line could be just ---
        end = rest.find(f"\n{_FRONTMATTER_DELIM}")
        if end < 0 or rest[end + len(_FRONTMATTER_DELIM) + 1:].strip():
            return {}, markdown
    yaml_text = rest[:end]
    body = rest[end + len(f"\n{_FRONTMATTER_DELIM}") :]
    # body may or may not start with \n
    if body.startswith("\n"):
        body = body[1:]
    try:
        fm = yaml.safe_load(yaml_text) or {}
        if not isinstance(fm, dict):
            return {}, markdown
        return fm, body
    except yaml.YAMLError:
        return {}, markdown


def _compose_markdown(frontmatter: dict, body: str) -> str:
    """Inverse of _split_frontmatter. If frontmatter is empty, emit body only."""
    if not frontmatter:
        return body
    yaml_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).rstrip()
    return f"{_FRONTMATTER_DELIM}\n{yaml_text}\n{_FRONTMATTER_DELIM}\n{body}"


def _normalize_tag(tag: str) -> str:
    """Strip leading # and whitespace."""
    return tag.lstrip("#").strip()


def add_tags(api: obsidian.Obsidian, filepath: str, tags: list[str]) -> dict:
    """Add tags to a file's YAML frontmatter. Creates frontmatter if missing. Deduplicates."""
    content = api.get_file_contents(filepath)
    fm, body = _split_frontmatter(content)
    existing = fm.get("tags") or []
    if isinstance(existing, str):
        existing = [existing]
    existing_set = {_normalize_tag(t) for t in existing}
    added = []
    for t in tags:
        n = _normalize_tag(t)
        if not n or n in existing_set:
            continue
        existing_set.add(n)
        existing.append(n)
        added.append(n)
    fm["tags"] = existing
    new_content = _compose_markdown(fm, body)
    api.put_content(filepath, new_content)
    return {"filepath": filepath, "added": added, "final_tags": existing}


def remove_tags(api: obsidian.Obsidian, filepath: str, tags: list[str]) -> dict:
    """Remove tags from frontmatter. No-op if tag absent."""
    content = api.get_file_contents(filepath)
    fm, body = _split_frontmatter(content)
    existing = fm.get("tags") or []
    if isinstance(existing, str):
        existing = [existing]
    to_remove = {_normalize_tag(t) for t in tags}
    kept = [t for t in existing if _normalize_tag(t) not in to_remove]
    removed = [t for t in existing if _normalize_tag(t) in to_remove]
    if kept:
        fm["tags"] = kept
    else:
        fm.pop("tags", None)
    new_content = _compose_markdown(fm, body)
    api.put_content(filepath, new_content)
    return {"filepath": filepath, "removed": removed, "final_tags": kept}


def find_backlinks(api: obsidian.Obsidian, target: str) -> list[dict]:
    """Find all files containing a wikilink to `target`.

    Matches `[[target]]`, `[[target|alias]]`, `[[target.md]]`, `[[target#heading]]`.
    Uses search_json with regexp + glob *.md on the content variable.
    """
    # Build regex that matches [[target or [[target.md or [[target|... or [[target#...
    target_bare = target.removesuffix(".md")
    # Escape for regex
    esc = re.escape(target_bare)
    # Match [[<target>(|alias)?(\.md)?(#heading)?]]
    pattern = rf"\[\[{esc}(\.md)?(\|[^\]]*)?(#[^\]]*)?\]\]"
    query = {
        "and": [
            {"glob": ["*.md", {"var": "path"}]},
            {"regexp": [pattern, {"var": "content"}]},
        ]
    }
    results = api.search_json(query)
    return results


def refactor_links(api: obsidian.Obsidian, old_path: str, new_path: str, dry_run: bool = False) -> dict:
    """Replace all `[[old_path]]` with `[[new_path]]` across the vault.

    Handles forms: [[old]], [[old.md]], [[old|alias]], [[old#heading]], [[old.md#heading]].
    Preserves alias/heading suffixes.
    """
    old_bare = old_path.removesuffix(".md")
    new_bare = new_path.removesuffix(".md")
    esc = re.escape(old_bare)
    pattern = re.compile(rf"\[\[{esc}(\.md)?((?:\|[^\]]*)?)((?:#[^\]]*)?)\]\]")

    changed_files = []
    backlinks = find_backlinks(api, old_path)
    for result in backlinks:
        filepath = result.get("filename") if isinstance(result, dict) else None
        if not filepath:
            continue
        try:
            content = api.get_file_contents(filepath)
        except Exception as e:
            changed_files.append({"filepath": filepath, "error": str(e)})
            continue

        def replacer(m: re.Match) -> str:
            had_md = bool(m.group(1))
            alias = m.group(2) or ""
            heading = m.group(3) or ""
            target = f"{new_bare}.md" if had_md else new_bare
            return f"[[{target}{alias}{heading}]]"

        new_content, n = pattern.subn(replacer, content)
        if n > 0:
            if not dry_run:
                try:
                    api.put_content(filepath, new_content)
                except Exception as e:
                    changed_files.append({"filepath": filepath, "error": str(e), "replacements": n})
                    continue
            changed_files.append({"filepath": filepath, "replacements": n})
    return {
        "old_path": old_path,
        "new_path": new_path,
        "dry_run": dry_run,
        "files_changed": len(changed_files),
        "details": changed_files,
    }


def generate_moc(api: obsidian.Obsidian, folder: str, title: str = "", include_subfolders: bool = True, out_path: str | None = None) -> dict:
    """Generate a Map of Content markdown file listing all notes in `folder`.

    If out_path is None, returns the markdown content without writing.
    """
    files = api.list_files_recursive(folder, max_depth=20 if include_subfolders else 1)
    md_files = [f for f in files if f.endswith(".md")]
    title = title or f"MoC — {folder or 'Vault'}"

    # Group by immediate subfolder
    from collections import defaultdict
    buckets: dict[str, list[str]] = defaultdict(list)
    prefix = folder.rstrip("/") + "/" if folder else ""
    for f in md_files:
        rel = f[len(prefix):] if f.startswith(prefix) else f
        if "/" in rel:
            bucket, rest = rel.split("/", 1)
        else:
            bucket = "."
            rest = rel
        buckets[bucket].append(f)

    lines = [f"# {title}", "", f"*Wygenerowane przez `obsidian_generate_moc`.*", ""]
    for bucket in sorted(buckets.keys()):
        if bucket != ".":
            lines.append(f"## {bucket}")
            lines.append("")
        for filepath in sorted(buckets[bucket]):
            # Link using vault-relative path, strip .md for display
            display = filepath.rsplit("/", 1)[-1].removesuffix(".md")
            lines.append(f"- [[{filepath}|{display}]]")
        lines.append("")
    content = "\n".join(lines)

    result: dict = {"folder": folder, "file_count": len(md_files), "bucket_count": len(buckets)}
    if out_path:
        api.put_content(out_path, content)
        result["written_to"] = out_path
    else:
        result["content"] = content
    return result
