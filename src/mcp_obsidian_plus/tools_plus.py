"""Extended tool handlers (the 'plus' in mcp-obsidian-plus).

These are additive to the upstream tools in tools.py — new capabilities that
were missing: server info, active file, execute command, file metadata,
recursive listing, plugin management, health check.
"""
from collections.abc import Sequence
import json
import os
import re
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

from . import obsidian
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
