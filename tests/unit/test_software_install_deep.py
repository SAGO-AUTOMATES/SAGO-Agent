from unittest.mock import MagicMock, patch

from sago.tools.admin.software_install import SoftwareInstallArgs, SoftwareInstallTool


def test_software_install_args():
    args = SoftwareInstallArgs(package="requests", manager="pip", version="2.31.0", sudo=False)
    assert args.package == "requests"
    assert args.manager == "pip"
    assert args.version == "2.31.0"
    assert args.sudo is False


def test_software_install_tool_basics():
    tool = SoftwareInstallTool()
    assert tool.name == "software_install"
    assert "package" in tool.description.lower()


def test_software_install_unknown_manager():
    tool = SoftwareInstallTool()
    res = tool._run(package="my-pkg", manager="unknown_mgr_xyz")
    assert "Error: Unknown package manager" in res


def test_software_install_not_in_path():
    tool = SoftwareInstallTool()
    with patch("shutil.which", return_value=None):
        with patch("sago.tools.ensure_dep.which", return_value=None):
            res = tool._run(package="my-pkg", manager="apt")
            assert "is not installed or not in PATH" in res


def test_software_install_version_specs():
    tool = SoftwareInstallTool()

    with (
        patch("shutil.which", return_value="/usr/bin/pip"),
        patch.object(tool, "_run_command") as mock_run_cmd,
    ):
        mock_proc = MagicMock(returncode=0, stdout="Successfully installed", stderr="")
        mock_run_cmd.return_value = mock_proc

        # pip version
        tool._run(package="requests", manager="pip", version="2.31.0")
        mock_run_cmd.assert_called_with(["pip", "install", "requests==2.31.0"], timeout=300)

        # poetry version
        tool._run(package="flask", manager="poetry", version="3.0.0")
        mock_run_cmd.assert_called_with(["poetry", "add", "flask@3.0.0"], timeout=300)

        # apt version with sudo
        tool._run(package="curl", manager="apt", version="7.88.1", sudo=True)
        mock_run_cmd.assert_called_with(
            ["sudo", "apt-get", "install", "-y", "curl=7.88.1"], timeout=300
        )

        # npm version
        tool._run(package="typescript", manager="npm", version="5.0.0")
        mock_run_cmd.assert_called_with(["npm", "install", "-g", "typescript@5.0.0"], timeout=300)


def test_software_install_failure():
    tool = SoftwareInstallTool()
    with (
        patch("shutil.which", return_value="/usr/bin/pip"),
        patch.object(tool, "_run_command") as mock_run_cmd,
    ):
        mock_proc = MagicMock(returncode=1, stdout="", stderr="Could not find package")
        mock_run_cmd.return_value = mock_proc

        res = tool._run(package="nonexistent_pkg", manager="pip")
        assert "Failed to install" in res
        assert "exit code: 1" in res


def test_detect_manager_python_and_js(tmp_path):
    tool = SoftwareInstallTool()
    with patch("shutil.which", side_effect=lambda c: f"/usr/bin/{c}"):
        # Python package heuristic
        py_mgr = tool._detect_manager("pytest")
        assert py_mgr in ("uv", "poetry", "pip", "pipx")

        # JS package heuristic
        js_mgr = tool._detect_manager("typescript")
        assert js_mgr in ("bun", "pnpm", "yarn", "npm")


def test_detect_manager_os_fallbacks(tmp_path):
    tool = SoftwareInstallTool()
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        with (
            patch.object(tool, "_is_windows", return_value=True),
            patch.object(tool, "_is_macos", return_value=False),
            patch("shutil.which", return_value="/bin/choco"),
        ):
            assert tool._detect_manager("curl") == "choco"

        with (
            patch.object(tool, "_is_windows", return_value=False),
            patch.object(tool, "_is_macos", return_value=True),
            patch("shutil.which", return_value="/bin/brew"),
        ):
            assert tool._detect_manager("curl") == "brew"

        with (
            patch.object(tool, "_is_windows", return_value=False),
            patch.object(tool, "_is_macos", return_value=False),
            patch("shutil.which", side_effect=lambda c: "/bin/dnf" if c == "dnf" else None),
        ):
            assert tool._detect_manager("curl") == "dnf"


def test_detect_compat_methods():
    tool = SoftwareInstallTool()
    assert tool._detect_python_manager() in ("uv", "poetry", "pip", "pipx")
    assert tool._detect_js_manager() in ("bun", "pnpm", "yarn", "npm")


def test_software_install_auto_flow(tmp_path):
    tool = SoftwareInstallTool()
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        (tmp_path / "uv.lock").touch()
        with (
            patch("shutil.which", return_value="/bin/uv"),
            patch.object(tool, "_run_command") as mock_run_cmd,
        ):
            mock_proc = MagicMock(returncode=0, stdout="Installed via uv", stderr="")
            mock_run_cmd.return_value = mock_proc

            res = tool._run(package="pydantic")
            assert "Successfully installed" in res
            mock_run_cmd.assert_called_with(["uv", "pip", "install", "pydantic"], timeout=300)


def test_detect_manager_js_lockfiles(tmp_path):
    tool = SoftwareInstallTool()
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        (tmp_path / "package-lock.json").touch()
        with patch("shutil.which", side_effect=lambda c: f"/bin/{c}" if c == "npm" else None):
            assert tool._detect_manager("lodash") == "npm"
