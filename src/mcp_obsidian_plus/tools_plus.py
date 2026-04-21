"""Extended tool handlers (the 'plus' in mcp-obsidian-plus).

These are additive to the upstream tools in tools.py — new capabilities that
were missing: server info, active file, execute command, file metadata,
recursive listing, plugin management, health check, knowledge ops, file ops.
"""
from collections.abc import Sequence
import json
import os
import re
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

from . import obsidian, knowledge, file_ops
from .tools import ToolHandler, api_key, obsidian_host


def _json(value) -> str:
    """Dump JSON with Polish-friendly encoding (no \\uXXXX)."""
    return json.dumps(value, indent=2, ensure_ascii=False)


def _client() -> obsidian.Obsidian:
    return obsidian.Obsidian(api_key=api_key, host=obsidian_host)


# ── Server info ──────────────────────────────────────────────────────────

class GetServerInfoToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_server_info")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Get Obsidian + Local REST API server metadata: authenticated status, "
                "Obsidian version, REST plugin version, certificate info, active API extensions."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        info = _client().get_server_info()
        return [TextContent(type="text", text=_json(info))]


# ── Active file ──────────────────────────────────────────────────────────

class GetActiveFileToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_active_file")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Return the file currently open/focused in the Obsidian GUI. "
                "With as_metadata=true, returns JSON with tags, links, frontmatter, stat. "
                "Without, returns raw markdown text."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "as_metadata": {
                        "type": "boolean",
                        "description": "If true, return note metadata object. If false (default), return raw markdown.",
                        "default": False,
                    }
                },
                "required": [],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        as_metadata = bool(args.get("as_metadata", False))
        result = _client().get_active_file(as_metadata=as_metadata)
        if as_metadata:
            return [TextContent(type="text", text=_json(result))]
        return [TextContent(type="text", text=result)]


class UpdateActiveFileToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_update_active_file")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Overwrite the content of the currently-open file in Obsidian GUI.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "New markdown content"}
                },
                "required": ["content"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "content" not in args:
            raise RuntimeError("content argument required")
        _client().update_active_file(args["content"])
        return [TextContent(type="text", text="Active file updated")]


class DeleteActiveFileToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_delete_active_file")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Delete the currently-open file. Requires confirm=true.",
            inputSchema={
                "type": "object",
                "properties": {
                    "confirm": {"type": "boolean", "description": "Must be true to delete."}
                },
                "required": ["confirm"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if not args.get("confirm", False):
            raise RuntimeError("confirm must be true to delete the active file")
        _client().delete_active_file()
        return [TextContent(type="text", text="Active file deleted")]


# ── Open file in GUI ────────────────────────────────────────────────────

class OpenFileToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_open_file")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Open a file in the Obsidian GUI. Useful to 'reveal' a note to the user "
                "after finding it programmatically. Use new_leaf=true to open in a new tab."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path relative to vault root", "format": "path"},
                    "new_leaf": {"type": "boolean", "description": "Open in a new tab (default: false)", "default": False},
                },
                "required": ["filepath"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepath" not in args:
            raise RuntimeError("filepath argument required")
        _client().open_file(args["filepath"], new_leaf=bool(args.get("new_leaf", False)))
        return [TextContent(type="text", text=f"Opened {args['filepath']} in Obsidian")]


# ── Commands ─────────────────────────────────────────────────────────────

class ListCommandsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_list_commands")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "List all Obsidian commands (id + human name). Optionally filter by regex on id or name. "
                "Use this to discover what `obsidian_execute_command` can invoke — Obsidian typically "
                "exposes ~200 commands covering editor, workspace, plugins, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Optional case-insensitive regex matched against command id and name",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default: 50)",
                        "default": 50,
                    },
                },
                "required": [],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        cmds = _client().list_commands()
        pattern = args.get("filter")
        if pattern:
            rx = re.compile(pattern, re.IGNORECASE)
            cmds = [c for c in cmds if rx.search(c.get("id", "")) or rx.search(c.get("name", ""))]
        limit = int(args.get("limit", 50))
        return [TextContent(type="text", text=_json({"count": len(cmds), "commands": cmds[:limit]}))]


class ExecuteCommandToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_execute_command")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Execute an Obsidian command by id (as from the command palette). "
                "Use `obsidian_list_commands` first to find the id. Useful ids: "
                "`app:reload` (reload app), `dataview:dataview-force-refresh-views` (refresh Dataview), "
                "`workspace:export-pdf` (export PDF), `app:delete-file` (delete active file)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command_id": {"type": "string", "description": "Command id like 'app:reload'"}
                },
                "required": ["command_id"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "command_id" not in args:
            raise RuntimeError("command_id argument required")
        _client().execute_command(args["command_id"])
        return [TextContent(type="text", text=f"Executed command: {args['command_id']}")]


# ── File metadata ───────────────────────────────────────────────────────

class GetFileMetadataToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_file_metadata")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Get a file's content AND rich metadata: tags, links (outgoing), "
                "frontmatter, stat (ctime/mtime in ms). Uses Accept: application/vnd.olrapi.note+json. "
                "Prefer this over `obsidian_get_file_contents` when you need to reason about tags or links."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path relative to vault root", "format": "path"}
                },
                "required": ["filepath"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepath" not in args:
            raise RuntimeError("filepath argument required")
        meta = _client().get_file_metadata(args["filepath"])
        return [TextContent(type="text", text=_json(meta))]


# ── Recursive list ──────────────────────────────────────────────────────

class ListFilesRecursiveToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_list_files_recursive")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Walk the vault recursively and return all file paths. "
                "Pass dirpath='' for the whole vault. Respects max_depth. "
                "No Dataview required — uses /vault/ endpoints."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dirpath": {"type": "string", "description": "Directory to walk (empty = vault root)", "default": ""},
                    "max_depth": {"type": "integer", "description": "Max recursion depth (default: 10)", "default": 10},
                },
                "required": [],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        dirpath = args.get("dirpath", "")
        max_depth = int(args.get("max_depth", 10))
        files = _client().list_files_recursive(dirpath, max_depth=max_depth)
        return [TextContent(type="text", text=_json({"count": len(files), "files": files}))]


# ── Health check ────────────────────────────────────────────────────────

class HealthCheckToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_health_check")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Probe the Obsidian setup and return a capability map: "
                "REST API version, Obsidian version, auth ok, certificate days left, "
                "Dataview installed, Periodic Notes installed, writable, active file present. "
                "Use this at the start of a session to know which tools are safe to call."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        api = _client()
        report: dict = {}

        try:
            info = api.get_server_info()
            report["authenticated"] = bool(info.get("authenticated"))
            report["rest_api_version"] = info.get("versions", {}).get("self")
            report["obsidian_version"] = info.get("versions", {}).get("obsidian")
            cert = info.get("certificateInfo") or {}
            report["cert_validity_days"] = cert.get("validityDays")
            report["cert_regenerate_recommended"] = cert.get("regenerateRecommended")
            report["active_api_extensions"] = info.get("apiExtensions", [])
        except Exception as e:
            report["server_info_error"] = str(e)

        # Dataview probe — try a minimal DQL
        try:
            api._get_recent_changes_dataview(1, 1)
            report["dataview_installed"] = True
        except obsidian.ObsidianCapabilityError:
            report["dataview_installed"] = False
        except Exception as e:
            report["dataview_probe_error"] = str(e)

        # Periodic notes probe — try daily (will 404 or 40461 if no daily plugin config)
        try:
            api.get_periodic_note("daily")
            report["periodic_daily_available"] = True
        except Exception as e:
            msg = str(e)
            # 40461 = "Periodic note does not exist for the specified period" — plugin is fine, just no note today
            report["periodic_daily_available"] = "40461" in msg
            if not report["periodic_daily_available"] and "404" not in msg and "40461" not in msg:
                report["periodic_probe_error"] = msg

        # Active file probe
        try:
            active = api.get_active_file()
            report["active_file_present"] = bool(active)
            report["active_file_size_chars"] = len(active) if active else 0
        except Exception:
            report["active_file_present"] = False

        # Commands count (fast check)
        try:
            cmds = api.list_commands()
            report["commands_count"] = len(cmds)
        except Exception as e:
            report["commands_error"] = str(e)

        return [TextContent(type="text", text=_json(report))]


# ── Community plugins list / toggle ─────────────────────────────────────

class ListPluginsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_list_plugins")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "List community plugins installed in the vault (read from .obsidian/community-plugins.json "
                "via the REST API). Returns both enabled and installed-but-disabled plugins when available."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        api = _client()
        result: dict = {}
        try:
            enabled_raw = api.get_file_contents(".obsidian/community-plugins.json")
            result["enabled"] = json.loads(enabled_raw)
        except Exception as e:
            result["enabled_error"] = str(e)
        # There's no canonical "installed but disabled" list via REST without directory listing dot-folders.
        # Many REST API configs block dot-folders; try once and report gracefully.
        try:
            installed = api.list_files_in_dir(".obsidian/plugins")
            result["installed_dirs"] = installed
        except Exception as e:
            result["installed_dirs_error"] = str(e)
        return [TextContent(type="text", text=_json(result))]


class TogglePluginToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_toggle_plugin")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Enable or disable a community plugin. Edits "
                "`.obsidian/community-plugins.json` (the list of enabled plugin ids) "
                "and then triggers `app:reload` so the change takes effect. "
                "Plugin files must already be present in `.obsidian/plugins/<id>/`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "plugin_id": {"type": "string", "description": "Plugin id (e.g. 'dataview')"},
                    "enable": {"type": "boolean", "description": "True = add to enabled list; False = remove"},
                    "reload_app": {"type": "boolean", "description": "Run app:reload after edit (default: true)", "default": True},
                },
                "required": ["plugin_id", "enable"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "plugin_id" not in args or "enable" not in args:
            raise RuntimeError("plugin_id and enable required")
        api = _client()
        enabled_path = ".obsidian/community-plugins.json"
        try:
            raw = api.get_file_contents(enabled_path)
            current = json.loads(raw) if raw.strip() else []
        except Exception:
            current = []
        if not isinstance(current, list):
            current = []

        plugin_id = args["plugin_id"]
        enable = bool(args["enable"])
        before = list(current)
        if enable and plugin_id not in current:
            current.append(plugin_id)
        elif not enable and plugin_id in current:
            current.remove(plugin_id)

        new_content = json.dumps(current, indent=2, ensure_ascii=False)
        api.put_content(enabled_path, new_content)

        reloaded = False
        if args.get("reload_app", True):
            try:
                api.execute_command("app:reload")
                reloaded = True
            except Exception as e:
                return [TextContent(type="text", text=_json({
                    "plugin_id": plugin_id, "enable": enable, "before": before, "after": current,
                    "reload_error": str(e),
                }))]
        return [TextContent(type="text", text=_json({
            "plugin_id": plugin_id, "enable": enable, "before": before, "after": current, "reloaded": reloaded,
        }))]


# ── Knowledge ops ────────────────────────────────────────────────────────

class AddTagsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_add_tags")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Add tags to a file's YAML frontmatter. Creates the frontmatter block if missing. "
                "Tags are deduplicated. Accepts tags with or without leading '#'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "format": "path"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "e.g. ['security', '#portfolio']"},
                },
                "required": ["filepath", "tags"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepath" not in args or "tags" not in args:
            raise RuntimeError("filepath and tags required")
        report = knowledge.add_tags(_client(), args["filepath"], args["tags"])
        return [TextContent(type="text", text=_json(report))]


class RemoveTagsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_remove_tags")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Remove tags from a file's YAML frontmatter. No-op if tag absent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "format": "path"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["filepath", "tags"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepath" not in args or "tags" not in args:
            raise RuntimeError("filepath and tags required")
        report = knowledge.remove_tags(_client(), args["filepath"], args["tags"])
        return [TextContent(type="text", text=_json(report))]


class FindBacklinksToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_find_backlinks")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Find all files containing a wikilink to `target`. Matches "
                "`[[target]]`, `[[target.md]]`, `[[target|alias]]`, `[[target#heading]]`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target path or name (with or without .md)"}
                },
                "required": ["target"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "target" not in args:
            raise RuntimeError("target required")
        results = knowledge.find_backlinks(_client(), args["target"])
        return [TextContent(type="text", text=_json({"count": len(results), "results": results}))]


class RefactorLinksToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_refactor_links")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Replace all `[[old_path]]` with `[[new_path]]` across the vault. "
                "Preserves aliases and heading suffixes (e.g. `[[old|alias]]` → `[[new|alias]]`). "
                "Use dry_run=true to preview changes without writing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "old_path": {"type": "string"},
                    "new_path": {"type": "string"},
                    "dry_run": {"type": "boolean", "default": False},
                },
                "required": ["old_path", "new_path"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "old_path" not in args or "new_path" not in args:
            raise RuntimeError("old_path and new_path required")
        report = knowledge.refactor_links(
            _client(),
            args["old_path"],
            args["new_path"],
            dry_run=bool(args.get("dry_run", False)),
        )
        return [TextContent(type="text", text=_json(report))]


class GenerateMocToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_generate_moc")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Generate a Map of Content markdown file listing all notes in `folder`, "
                "grouped by immediate subfolder. If out_path is provided, writes the MoC there; "
                "otherwise returns the content in the response."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "folder": {"type": "string", "description": "Folder to index (empty = vault root)"},
                    "title": {"type": "string", "description": "Heading for the MoC (default: auto)"},
                    "include_subfolders": {"type": "boolean", "default": True},
                    "out_path": {"type": "string", "description": "Where to write the MoC (optional)"},
                },
                "required": ["folder"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        report = knowledge.generate_moc(
            _client(),
            args.get("folder", ""),
            title=args.get("title", ""),
            include_subfolders=bool(args.get("include_subfolders", True)),
            out_path=args.get("out_path"),
        )
        return [TextContent(type="text", text=_json(report))]


# ── File ops ─────────────────────────────────────────────────────────────

class RenameFileToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_rename_file")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Rename a file: copy to new path, optionally rewrite backlinks, delete old. "
                "Not transactional — if backlink refactor fails mid-way, leaves files in inconsistent state."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "from_path": {"type": "string"},
                    "to_path": {"type": "string"},
                    "update_backlinks": {"type": "boolean", "default": True},
                },
                "required": ["from_path", "to_path"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "from_path" not in args or "to_path" not in args:
            raise RuntimeError("from_path and to_path required")
        report = file_ops.rename_file(
            _client(),
            args["from_path"],
            args["to_path"],
            update_backlinks=bool(args.get("update_backlinks", True)),
        )
        return [TextContent(type="text", text=_json(report))]


class MoveFileToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_move_file")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Move a file to a new folder, preserving filename. Updates backlinks by default.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_path": {"type": "string"},
                    "to_folder": {"type": "string"},
                    "update_backlinks": {"type": "boolean", "default": True},
                },
                "required": ["from_path", "to_folder"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "from_path" not in args or "to_folder" not in args:
            raise RuntimeError("from_path and to_folder required")
        report = file_ops.move_file(
            _client(),
            args["from_path"],
            args["to_folder"],
            update_backlinks=bool(args.get("update_backlinks", True)),
        )
        return [TextContent(type="text", text=_json(report))]


class BatchRenameToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_batch_rename")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description=(
                "Rename multiple files. Per-item errors are reported but don't abort the batch. "
                "Backlinks are updated after each rename to keep them consistent as paths shift."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "renames": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                            },
                            "required": ["from", "to"],
                        },
                    },
                    "update_backlinks": {"type": "boolean", "default": True},
                },
                "required": ["renames"],
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "renames" not in args:
            raise RuntimeError("renames required")
        report = file_ops.batch_rename(
            _client(),
            args["renames"],
            update_backlinks=bool(args.get("update_backlinks", True)),
        )
        return [TextContent(type="text", text=_json(report))]
