import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from core.plugins.package_download import install_registry_package_under_plugins
from core.plugins.registry_catalog import RegistryPluginRecord


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _record(url: str, body: bytes, **kwargs) -> RegistryPluginRecord:
    digest = hashlib.sha256(body).hexdigest()
    return RegistryPluginRecord(
        id="demo-plugin",
        name="demo-plugin",
        display_name="Demo Plugin",
        author="Tester",
        repo="owner/demo-plugin",
        description="",
        short_description="",
        entry="plugins.demo_plugin.plugin:DemoPlugin",
        package_source="r2",
        package_url=url,
        package_sha256=kwargs.pop("sha256", digest),
        package_size=kwargs.pop("size", len(body)),
    )


def test_install_registry_package_downloads_verifies_and_flattens_single_root(tmp_path, monkeypatch):
    body = _zip_bytes(
        {
            "demo-root/plugin.py": "class DemoPlugin(PluginBase):\n    pass\n",
            "demo-root/requirements.txt": "",
        }
    )
    monkeypatch.setattr("core.plugins.package_download._read_url", lambda *args, **kwargs: body)

    plugin_root = install_registry_package_under_plugins(
        _record("https://plugins-cdn.shinsekai.end0rph1n.icu/plugins/demo.zip", body),
        plugins_parent=tmp_path,
    )

    assert plugin_root == tmp_path / "demo-plugin"
    assert (plugin_root / "plugin.py").read_text(encoding="utf-8").startswith("class DemoPlugin")
    assert (plugin_root / "requirements.txt").is_file()


def test_install_registry_package_rejects_checksum_mismatch(tmp_path, monkeypatch):
    body = _zip_bytes({"demo-root/plugin.py": "class DemoPlugin(PluginBase):\n    pass\n"})
    monkeypatch.setattr("core.plugins.package_download._read_url", lambda *args, **kwargs: body)

    with pytest.raises(ValueError, match="checksum"):
        install_registry_package_under_plugins(
            _record(
                "https://plugins-cdn.shinsekai.end0rph1n.icu/plugins/demo.zip",
                body,
                sha256="0" * 64,
            ),
            plugins_parent=tmp_path,
        )


def test_install_registry_package_rejects_zip_slip(tmp_path, monkeypatch):
    body = _zip_bytes({"demo-root/../escape.py": "bad"})
    monkeypatch.setattr("core.plugins.package_download._read_url", lambda *args, **kwargs: body)

    with pytest.raises(ValueError, match="unsafe"):
        install_registry_package_under_plugins(
            _record("https://plugins-cdn.shinsekai.end0rph1n.icu/plugins/demo.zip", body),
            plugins_parent=tmp_path,
        )
    assert not (tmp_path.parent / "escape.py").exists()


def test_install_registry_package_enforces_host_allowlist(tmp_path, monkeypatch):
    body = _zip_bytes({"demo-root/plugin.py": "class DemoPlugin(PluginBase):\n    pass\n"})
    monkeypatch.setenv("SHINSEKAI_PLUGIN_PACKAGE_HOSTS", "plugins-cdn.shinsekai.end0rph1n.icu")
    monkeypatch.setattr("core.plugins.package_download._read_url", lambda *args, **kwargs: body)

    with pytest.raises(ValueError, match="not allowed"):
        install_registry_package_under_plugins(
            _record("https://example.com/plugins/demo.zip", body),
            plugins_parent=tmp_path,
        )
