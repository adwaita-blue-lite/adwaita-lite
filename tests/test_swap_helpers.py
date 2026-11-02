import os
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SWAP_INIT = _REPO / "files/usr/libexec/adwaita-lite-swap-init"


def _run_swap_init(tmp_path, size_text=None):
    size_file = tmp_path / "swap-size"
    if size_text is not None:
        size_file.write_text(size_text, encoding="utf-8")
    env = os.environ.copy()
    env["SIZE_FILE"] = str(size_file)
    env["SWAPFILE"] = str(tmp_path / "swap")
    return subprocess.run(
        ["bash", str(_SWAP_INIT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("size_text", ["", "abc", "0", "257", "1000"])
def test_swap_init_rejects_invalid_or_excessive_sizes(tmp_path, size_text):
    result = _run_swap_init(tmp_path, size_text)

    assert result.returncode == 1
    assert "swap size must be a whole number from 1 to 256 GB" in result.stderr
    assert not (tmp_path / "swap").exists()


def test_swap_init_reports_missing_size_file(tmp_path):
    result = _run_swap_init(tmp_path)

    assert result.returncode == 1
    assert "missing swap size file" in result.stderr
    assert not (tmp_path / "swap").exists()
