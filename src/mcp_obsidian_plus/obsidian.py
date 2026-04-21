import requests
import urllib.parse
import os
from typing import Any


class ObsidianCapabilityError(Exception):
    """Raised when an operation requires an Obsidian plugin that isn't installed/enabled."""
    def __init__(self, message: str, error_code: int = -1):
        super().__init__(message)
        self.error_code = error_code


class Obsidian():
    def __init__(
            self,
            api_key: str,
            protocol: str = os.getenv('OBSIDIAN_PROTOCOL', 'https').lower(),
            host: str = str(os.getenv('OBSIDIAN_HOST', '127.0.0.1')),
            port: int = int(os.getenv('OBSIDIAN_PORT', '27124')),
            verify_ssl: bool = False,
        ):
        self.api_key = api_key

        if protocol == 'http':
            self.protocol = 'http'
        else:
            self.protocol = 'https'

        self.host = host
        self.port = port
        self.verify_ssl = verify_ssl
        self.timeout = (3, 6)

    def get_base_url(self) -> str:
        return f'{self.protocol}://{self.host}:{self.port}'

    def _get_headers(self) -> dict:
        return {'Authorization': f'Bearer {self.api_key}'}

    def _safe_call(self, f) -> Any:
        try:
            return f()
        except requests.HTTPError as e:
            error_data = e.response.json() if e.response.content else {}
            code = error_data.get('errorCode', -1)
            message = error_data.get('message', '<unknown>')
            if code == 40070 or (isinstance(message, str) and "tryQuery" in message):
                raise ObsidianCapabilityError(
                    "Dataview plugin is required for this operation but is not installed or enabled. "
                    "Install it in Obsidian Settings → Community plugins.",
                    error_code=code,
                )
            raise Exception(f"Error {code}: {message}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    # ── Server info ──────────────────────────────────────────────────────

    def get_server_info(self) -> dict:
        url = f"{self.get_base_url()}/"

        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    # ── Vault file CRUD ──────────────────────────────────────────────────

    def list_files_in_vault(self) -> Any:
        url = f"{self.get_base_url()}/vault/"

        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()['files']

        return self._safe_call(call_fn)

    def list_files_in_dir(self, dirpath: str) -> Any:
        url = f"{self.get_base_url()}/vault/{dirpath}/"

        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()['files']

        return self._safe_call(call_fn)

    def list_files_recursive(self, dirpath: str = "", max_depth: int = 10) -> list[str]:
        """Walk vault recursively; returns all file paths (skips empty dirs).
        No Dataview needed — uses /vault/ endpoints only.
        """
        results: list[str] = []

        def walk(current: str, depth: int):
            if depth > max_depth:
                return
            try:
                entries = self.list_files_in_vault() if current == "" else self.list_files_in_dir(current)
            except Exception:
                return
            for entry in entries:
                if current == "":
                    path = entry
                else:
                    path = f"{current}/{entry}" if not current.endswith("/") else f"{current}{entry}"
                path = path.replace("//", "/")
                if entry.endswith("/"):
                    walk(path.rstrip("/"), depth + 1)
                else:
                    results.append(path)

        walk(dirpath.rstrip("/"), 0)
        return results

    def get_file_contents(self, filepath: str) -> Any:
        url = f"{self.get_base_url()}/vault/{filepath}"

        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.text

        return self._safe_call(call_fn)

    def get_file_metadata(self, filepath: str) -> dict:
        """File content + tags/links/frontmatter/stat via Accept: olrapi.note+json."""
        url = f"{self.get_base_url()}/vault/{filepath}"
        headers = self._get_headers() | {'Accept': 'application/vnd.olrapi.note+json'}

        def call_fn():
            response = requests.get(url, headers=headers, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    def get_batch_file_contents(self, filepaths: list[str]) -> str:
        result = []
        for filepath in filepaths:
            try:
                content = self.get_file_contents(filepath)
                result.append(f"# {filepath}\n\n{content}\n\n---\n\n")
            except Exception as e:
                result.append(f"# {filepath}\n\nError reading file: {str(e)}\n\n---\n\n")
        return "".join(result)

    def append_content(self, filepath: str, content: str) -> Any:
        url = f"{self.get_base_url()}/vault/{filepath}"

        def call_fn():
            response = requests.post(
                url,
                headers=self._get_headers() | {'Content-Type': 'text/markdown'},
                data=content.encode('utf-8'),
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)

    def patch_content(self, filepath: str, operation: str, target_type: str, target: str, content: str) -> Any:
        url = f"{self.get_base_url()}/vault/{filepath}"
        headers = self._get_headers() | {
            'Content-Type': 'text/markdown',
            'Operation': operation,
            'Target-Type': target_type,
            'Target': urllib.parse.quote(target)
        }

        def call_fn():
            response = requests.patch(url, headers=headers, data=content.encode('utf-8'), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)

    def put_content(self, filepath: str, content: str) -> Any:
        url = f"{self.get_base_url()}/vault/{filepath}"

        def call_fn():
            response = requests.put(
                url,
                headers=self._get_headers() | {'Content-Type': 'text/markdown'},
                data=content.encode('utf-8'),
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)

    def delete_file(self, filepath: str) -> Any:
        url = f"{self.get_base_url()}/vault/{filepath}"

        def call_fn():
            response = requests.delete(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)

    # ── Active file (currently focused in Obsidian GUI) ─────────────────

    def get_active_file(self, as_metadata: bool = False) -> Any:
        url = f"{self.get_base_url()}/active/"
        headers = self._get_headers()
        if as_metadata:
            headers = headers | {'Accept': 'application/vnd.olrapi.note+json'}

        def call_fn():
            response = requests.get(url, headers=headers, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json() if as_metadata else response.text

        return self._safe_call(call_fn)

    def update_active_file(self, content: str) -> None:
        url = f"{self.get_base_url()}/active/"

        def call_fn():
            response = requests.put(
                url,
                headers=self._get_headers() | {'Content-Type': 'text/markdown'},
                data=content.encode('utf-8'),
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)

    def delete_active_file(self) -> None:
        url = f"{self.get_base_url()}/active/"

        def call_fn():
            response = requests.delete(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)

    # ── Open file in GUI ─────────────────────────────────────────────────

    def open_file(self, filepath: str, new_leaf: bool = False) -> None:
        url = f"{self.get_base_url()}/open/{filepath}"
        params = {'newLeaf': 'true'} if new_leaf else {}

        def call_fn():
            response = requests.post(url, headers=self._get_headers(), params=params, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)

    # ── Commands ─────────────────────────────────────────────────────────

    def list_commands(self) -> list[dict]:
        url = f"{self.get_base_url()}/commands/"

        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json().get('commands', [])

        return self._safe_call(call_fn)

    def execute_command(self, command_id: str) -> None:
        url = f"{self.get_base_url()}/commands/{command_id}/"

        def call_fn():
            response = requests.post(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)

    # ── Search ───────────────────────────────────────────────────────────

    def search(self, query: str, context_length: int = 100) -> Any:
        url = f"{self.get_base_url()}/search/simple/"
        params = {'query': query, 'contextLength': context_length}

        def call_fn():
            response = requests.post(url, headers=self._get_headers(), params=params, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    def search_json(self, query: dict) -> Any:
        url = f"{self.get_base_url()}/search/"
        headers = self._get_headers() | {'Content-Type': 'application/vnd.olrapi.jsonlogic+json'}

        def call_fn():
            response = requests.post(url, headers=headers, json=query, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    # ── Periodic notes ───────────────────────────────────────────────────

    def get_periodic_note(self, period: str, type: str = "content") -> Any:
        url = f"{self.get_base_url()}/periodic/{period}/"

        def call_fn():
            headers = self._get_headers()
            if type == "metadata":
                headers['Accept'] = 'application/vnd.olrapi.note+json'
            response = requests.get(url, headers=headers, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.text

        return self._safe_call(call_fn)

    def get_recent_periodic_notes(self, period: str, limit: int = 5, include_content: bool = False) -> Any:
        url = f"{self.get_base_url()}/periodic/{period}/recent"
        params = {"limit": limit, "includeContent": include_content}

        def call_fn():
            response = requests.get(url, headers=self._get_headers(), params=params, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    # ── Recent changes (Dataview preferred, FS fallback) ─────────────────

    def get_recent_changes(self, limit: int = 10, days: int = 90) -> list[dict]:
        try:
            return self._get_recent_changes_dataview(limit, days)
        except ObsidianCapabilityError:
            return self._get_recent_changes_fallback(limit, days)

    def _get_recent_changes_dataview(self, limit: int, days: int) -> list[dict]:
        query_lines = [
            "TABLE file.mtime",
            f"WHERE file.mtime >= date(today) - dur({days} days)",
            "SORT file.mtime DESC",
            f"LIMIT {limit}",
        ]
        dql_query = "\n".join(query_lines)
        url = f"{self.get_base_url()}/search/"
        headers = self._get_headers() | {'Content-Type': 'application/vnd.olrapi.dataview.dql+txt'}

        def call_fn():
            response = requests.post(url, headers=headers, data=dql_query.encode('utf-8'), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    def _get_recent_changes_fallback(self, limit: int, days: int) -> list[dict]:
        """FS-based fallback when Dataview is unavailable. Output shape matches Dataview path."""
        import datetime
        import time
        cutoff_ms = int((time.time() - days * 86400) * 1000)
        candidates: list[tuple[int, str]] = []

        for filepath in self.list_files_recursive("", max_depth=20):
            if not filepath.endswith(".md"):
                continue
            try:
                meta = self.get_file_metadata(filepath)
            except Exception:
                continue
            stat = meta.get('stat') or {}
            mtime_ms = stat.get('mtime')
            if not isinstance(mtime_ms, (int, float)) or mtime_ms < cutoff_ms:
                continue
            candidates.append((int(mtime_ms), filepath))

        candidates.sort(reverse=True)
        top = candidates[:limit]
        return [
            {
                "filename": path,
                "result": {
                    "file.mtime": datetime.datetime.fromtimestamp(mtime_ms / 1000, tz=datetime.timezone.utc).isoformat()
                },
            }
            for mtime_ms, path in top
        ]
