# mcp-obsidian-plus

Extended MCP server for Obsidian — fork of [MarkusPfundstein/mcp-obsidian](https://github.com/MarkusPfundstein/mcp-obsidian) (v0.2.1) with additional tools and fixes for heavier knowledge-base operations.

## What's added on top of upstream

**Core extensions** — expose the rest of the Obsidian Local REST API
- `obsidian_get_server_info` — `GET /` (vault name, Obsidian/REST version, cert status)
- `obsidian_get_active_file` / `obsidian_update_active_file` / `obsidian_delete_active_file` — `/active/`
- `obsidian_open_file` — `POST /open/{path}` (reveal file in GUI)
- `obsidian_list_commands` — `GET /commands/` with optional regex filter
- `obsidian_execute_command` — `POST /commands/{id}/` (reload app, force Dataview refresh, export PDF, any Obsidian command)

**Knowledge ops**
- `obsidian_list_files_recursive` — full vault tree with depth limit
- `obsidian_get_file_metadata` — frontmatter, tags, links, backlinks via `Accept: application/vnd.olrapi.note+json`
- `obsidian_find_backlinks` — all files linking to a target
- `obsidian_refactor_links` — atomic `[[old]]` → `[[new]]` across the vault
- `obsidian_add_tags` / `obsidian_remove_tags` — frontmatter tag manipulation
- `obsidian_generate_moc` — Map of Content for a folder

**File ops**
- `obsidian_rename_file` — rename with backlink refactoring
- `obsidian_move_file` — move between folders
- `obsidian_batch_rename` — transactional multi-file rename

**Meta / UX**
- `obsidian_health_check` — capability probe (Dataview present? writable? cert days left?)
- `obsidian_list_plugins` / `obsidian_toggle_plugin` — manage community plugins

**Fixes over upstream**
- `ensure_ascii=False` in all JSON responses (no more `ęż` for Polish / non-ASCII diacritics)
- `obsidian_get_recent_changes` falls back to per-file metadata read when Dataview is not installed (was returning Error 40070)
- Error 40070 mapped to a human-readable "Dataview plugin required" message

## Configuration

Install via `uvx`:

```json
{
  "mcpServers": {
    "obsidian-plus": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/ak6616/mcp-obsidian-plus", "mcp-obsidian-plus"],
      "env": {
        "OBSIDIAN_API_KEY": "<paste from Obsidian → Settings → Local REST API>",
        "OBSIDIAN_HOST": "127.0.0.1",
        "OBSIDIAN_PORT": "27124"
      }
    }
  }
}
```

Prerequisites:
- [Obsidian Local REST API plugin](https://github.com/coddingtonbear/obsidian-local-rest-api) installed and enabled
- `uv` / `uvx` available (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

## Original upstream tools (unchanged)

All tools from `mcp-obsidian` 0.2.1 are preserved: `obsidian_list_files_in_vault`, `obsidian_list_files_in_dir`, `obsidian_get_file_contents`, `obsidian_simple_search`, `obsidian_complex_search`, `obsidian_patch_content`, `obsidian_append_content`, `obsidian_put_content`, `obsidian_delete_file`, `obsidian_batch_get_file_contents`, `obsidian_get_periodic_note`, `obsidian_get_recent_periodic_notes`, `obsidian_get_recent_changes`.

## License

MIT, inherited from upstream. See `LICENSE`.
