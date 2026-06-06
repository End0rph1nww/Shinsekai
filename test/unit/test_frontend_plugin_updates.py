from types import SimpleNamespace

from core.plugins.registry_catalog import RegistryPluginRecord
from frontend_bridge_core.state import BridgeState
from frontend_bridge_core.plugin_updates import (
    _infer_plugin_entry,
    _install_plugin_source,
    _is_repo_source,
    _lookup_registry_plugin,
    _plugin_class_from_file,
    _repo_slug_from_source,
    _synthetic_plugin_result,
)


def test_registry_download_state_persists_package_install_metadata(tmp_path, monkeypatch):
    from core.plugins import registry_download

    monkeypatch.setattr(registry_download, "_DOWNLOAD_STATE_PATH", tmp_path / "downloads.json")

    registry_download.mark_repo_downloaded(
        "owner/demo",
        manifest_entry="demo.plugin:DemoPlugin",
        install_metadata={
            "packageSha256": "abc123",
            "packageUrl": "https://cdn.example.com/demo.zip",
            "sourceType": "official-package",
        },
    )

    assert registry_download.load_plugin_install_metadata("plugins.demo.plugin:DemoPlugin") == {
        "packageSha256": "abc123",
        "packageUrl": "https://cdn.example.com/demo.zip",
        "sourceType": "official-package",
    }


def test_repo_slug_from_source_accepts_common_github_forms():
    assert _repo_slug_from_source("owner/repo") == "owner/repo"
    assert _repo_slug_from_source("https://github.com/owner/repo.git") == "owner/repo"
    assert _repo_slug_from_source("github.com/owner/repo/tree/main") == "owner/repo"
    assert _repo_slug_from_source("git@github.com:owner/repo.git") == "owner/repo"
    assert _repo_slug_from_source("http://github.com/owner/repo/tree/main?x=1#readme") == "owner/repo"
    assert _repo_slug_from_source("owner") == ""


def test_repo_source_rejects_manifest_entries():
    assert _is_repo_source("owner/repo") is True
    assert _is_repo_source("https://github.com/owner/repo.git") is True
    assert _is_repo_source("git@github.com:owner/repo.git") is True
    assert _is_repo_source("plugins.demo.plugin:DemoPlugin") is False
    assert _is_repo_source("not-enough") is False


def test_plugin_class_from_file_detects_pluginbase_subclasses(tmp_path):
    plugin_py = tmp_path / "plugin.py"
    plugin_py.write_text(
        "\n".join(
            [
                "class Helper:",
                "    pass",
                "class DemoPlugin(PluginBase):",
                "    pass",
            ]
        ),
        encoding="utf-8",
    )

    assert _plugin_class_from_file(plugin_py) == "DemoPlugin"

    plugin_py.write_text("class Broken(:\n", encoding="utf-8")
    assert _plugin_class_from_file(plugin_py) == ""


def test_infer_plugin_entry_uses_top_level_or_nested_plugin_file(tmp_path):
    plugin_root = tmp_path / "demo_plugin"
    plugin_root.mkdir()
    (plugin_root / "plugin.py").write_text("class DemoPlugin(PluginBase):\n    pass\n", encoding="utf-8")

    assert _infer_plugin_entry(plugin_root) == "plugins.demo_plugin.plugin:DemoPlugin"

    nested_root = tmp_path / "nested_plugin"
    nested = nested_root / "package"
    nested.mkdir(parents=True)
    (nested / "plugin.py").write_text("class NestedPlugin(shin.PluginBase):\n    pass\n", encoding="utf-8")

    assert _infer_plugin_entry(nested_root) == "plugins.nested_plugin.package.plugin:NestedPlugin"


def test_synthetic_plugin_result_uses_safe_defaults():
    assert _synthetic_plugin_result(
        description="Downloaded but not enabled",
        enabled=False,
        plugin_id="plugins.demo.plugin:Demo",
        title="Demo",
        version="1.0",
    ) == {
        "author": "",
        "description": "Downloaded but not enabled",
        "directory": "",
        "enabled": False,
        "entry": "plugins.demo.plugin:Demo",
        "id": "plugins.demo.plugin:Demo",
        "loadError": "",
        "loaded": False,
        "permissions": [],
        "settingsPages": [],
        "slots": ["settings-extension"],
        "title": "Demo",
        "toolsTabs": [],
        "version": "1.0",
    }


def test_infer_plugin_entry_ignores_non_identifier_module_parts(tmp_path):
    plugin_root = tmp_path / "bad-name"
    plugin_root.mkdir()
    (plugin_root / "plugin.py").write_text("class DemoPlugin(PluginBase):\n    pass\n", encoding="utf-8")

    assert _infer_plugin_entry(plugin_root) == ""


def test_lookup_registry_plugin_matches_catalog_id(monkeypatch):
    record = RegistryPluginRecord(
        id="vision-demo",
        name="legacy-vision-name",
        display_name="Vision Demo",
        author="Tester",
        repo="owner/vision-demo",
        description="Packaged plugin",
        short_description="Packaged plugin",
        entry="plugins.vision_demo.plugin:VisionDemoPlugin",
        package_url="https://plugins-cdn.shinsekai.end0rph1n.icu/plugins/vision.zip",
        package_sha256="abc123",
    )

    monkeypatch.setattr("core.plugins.registry_catalog.fetch_registry_plugins", lambda timeout_sec=12: [record])

    assert _lookup_registry_plugin("vision-demo") is record


def test_install_plugin_source_prefers_registry_package_for_catalog_id(tmp_path, monkeypatch):
    plugin_root = tmp_path / "demo-plugin"
    plugin_root.mkdir()
    (plugin_root / "plugin.py").write_text("class DemoPlugin(PluginBase):\n    pass\n", encoding="utf-8")
    record = RegistryPluginRecord(
        id="demo-plugin",
        name="demo-plugin",
        display_name="Demo Plugin",
        author="Tester",
        repo="owner/demo-plugin",
        description="Packaged plugin",
        short_description="Packaged plugin",
        entry="plugins.demo_plugin.plugin:DemoPlugin",
        package_source="r2",
        package_url="https://plugins-cdn.shinsekai.end0rph1n.icu/plugins/demo.zip",
        package_sha256="abc123",
        package_size=128,
    )
    state = BridgeState(None, None, None, None)
    state.tasks["task"] = {}
    installed: list[tuple[RegistryPluginRecord, bool]] = []
    marked: list[tuple[str, str | None, dict[str, object] | None]] = []

    monkeypatch.setattr("frontend_bridge_core.plugin_updates._lookup_registry_plugin", lambda source: record)
    monkeypatch.setattr(
        "core.plugins.package_download.install_registry_package_under_plugins",
        lambda rec, plugins_parent, overwrite=False: installed.append((rec, overwrite)) or plugin_root,
    )
    monkeypatch.setattr(
        "core.plugins.plugin_requirements_install.install_plugin_requirements_txt",
        lambda root, on_output_line=None: ("ok", ""),
    )
    monkeypatch.setattr(
        "core.plugins.registry_download.mark_repo_downloaded",
        lambda repo, manifest_entry=None, install_metadata=None: marked.append((repo, manifest_entry, install_metadata)),
    )
    monkeypatch.setattr(
        "frontend_bridge_core.plugin_updates._plugin_result_from_manifest",
        lambda entry: {"entry": entry, "title": "Demo Plugin"},
    )

    result = _install_plugin_source(state, "task", "demo-plugin")

    assert result["entry"] == "plugins.demo_plugin.plugin:DemoPlugin"
    assert result["title"] == "Demo Plugin"
    assert result["install"] == {
        "dependencyDetail": "",
        "dependencyStatus": "ok",
        "entry": "plugins.demo_plugin.plugin:DemoPlugin",
        "packageSha256": "abc123",
        "packageSize": 128,
        "packageSource": "r2",
        "packageStatus": "installed",
        "packageUrl": "https://plugins-cdn.shinsekai.end0rph1n.icu/plugins/demo.zip",
        "repo": "owner/demo-plugin",
        "sourceLabel": "Official package (R2)",
        "sourceType": "official-package",
    }
    assert state.tasks["task"]["installSource"] == "official-package"
    assert state.tasks["task"]["packageStatus"] == "installed"
    assert state.tasks["task"]["dependencyInstallStatus"] == "ok"
    assert "Source: Official package (R2)" in state.tasks["task"]["logs"]
    assert installed == [(record, False)]
    assert marked == [
        (
            "owner/demo-plugin",
            "plugins.demo_plugin.plugin:DemoPlugin",
            {
                "dependencyDetail": "",
                "dependencyStatus": "ok",
                "entry": "plugins.demo_plugin.plugin:DemoPlugin",
                "packageSha256": "abc123",
                "packageSize": 128,
                "packageSource": "r2",
                "packageStatus": "installed",
                "packageUrl": "https://plugins-cdn.shinsekai.end0rph1n.icu/plugins/demo.zip",
                "repo": "owner/demo-plugin",
                "sourceLabel": "Official package (R2)",
                "sourceType": "official-package",
            },
        )
    ]


def test_install_plugin_source_falls_back_to_github_when_registry_package_fails(tmp_path, monkeypatch):
    plugin_root = tmp_path / "demo-plugin"
    plugin_root.mkdir()
    (plugin_root / "plugin.py").write_text("class DemoPlugin(PluginBase):\n    pass\n", encoding="utf-8")
    record = RegistryPluginRecord(
        id="demo-plugin",
        name="demo-plugin",
        display_name="Demo Plugin",
        author="Tester",
        repo="owner/demo-plugin",
        description="Packaged plugin",
        short_description="Packaged plugin",
        entry="plugins.demo_plugin.plugin:DemoPlugin",
        package_source="r2",
        package_url="https://plugins-cdn.shinsekai.end0rph1n.icu/plugins/demo.zip",
        package_sha256="abc123",
    )
    state = BridgeState(None, None, None, None)
    state.tasks["task"] = {}
    github_installs: list[tuple[str, str]] = []

    monkeypatch.setattr("frontend_bridge_core.plugin_updates._lookup_registry_plugin", lambda source: record)
    monkeypatch.setattr(
        "core.plugins.package_download.install_registry_package_under_plugins",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("r2 unavailable")),
    )

    def fake_install_github(repo_slug, **kwargs):
        github_installs.append((repo_slug, kwargs.get("ref_kind")))
        return plugin_root

    monkeypatch.setattr("core.plugins.github_bundle_update.install_github_plugin_under_plugins", fake_install_github)
    monkeypatch.setattr(
        "core.plugins.plugin_requirements_install.install_plugin_requirements_txt",
        lambda root, on_output_line=None: ("pip_ok", ""),
    )
    monkeypatch.setattr("core.plugins.registry_download.mark_repo_downloaded", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "frontend_bridge_core.plugin_updates._plugin_result_from_manifest",
        lambda entry: {"entry": entry, "title": "Demo Plugin"},
    )

    result = _install_plugin_source(state, "task", "demo-plugin")

    assert result["install"]["sourceType"] == "github-source"
    assert result["install"]["sourceLabel"] == "GitHub source fallback"
    assert result["install"]["dependencyStatus"] == "pip_ok"
    assert state.tasks["task"]["installSourceLabel"] == "GitHub source fallback"
    assert state.tasks["task"]["dependencyInstallStatus"] == "pip_ok"
    assert github_installs == [("owner/demo-plugin", "latest")]
    assert any("falling back to GitHub" in line for line in state.tasks["task"]["logs"])
