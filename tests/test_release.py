"""Verify the HACS release asset without publishing a release."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent


def test_release_archive():
    config = json.loads(subprocess.check_output(
        ["node", "-e", "console.log(JSON.stringify(require('./release.config.cjs')))"],
        cwd=ROOT,
        text=True,
    ))
    plugins = dict(plugin if isinstance(plugin, list) else (plugin, {}) for plugin in config["plugins"])
    assert "@semantic-release/git" not in plugins
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["zip_release"] is True
    assert plugins["@semantic-release/github"]["assets"] == [hacs["filename"]]
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        shutil.copytree(ROOT / "custom_components" / "myki", work / "custom_components" / "myki")
        command = plugins["@semantic-release/exec"]["prepareCmd"].replace("${nextRelease.version}", "1.2.3")
        subprocess.run(command, cwd=work, shell=True, check=True)
        with ZipFile(work / hacs["filename"]) as archive:
            assert json.loads(archive.read("manifest.json"))["version"] == "1.2.3"
            assert "__init__.py" in archive.namelist()
            assert "translations/en.json" in archive.namelist()
