from unittest.mock import MagicMock, patch

from sago.tools.ensure_dep import (
    Distro,
    OsType,
    PlatformInfo,
    _detect_distro,
    _detect_js_installer,
    _detect_package_manager,
    _detect_python_installer,
    _get_total_memory_mb,
    _install_chromium,
    _install_docker,
    _install_k3s,
    _install_kubectl,
    _install_node,
    _install_via_pm,
    detect_platform,
    ensure_binary,
    ensure_pip_package,
    install_httpx,
    install_pip_package,
    install_playwright,
    is_available,
    which,
)


def test_platform_info_arch_label():
    p1 = PlatformInfo(
        os=OsType.LINUX,
        distro=Distro.UBUNTU,
        distro_version="22.04",
        arch="x86_64",
        libc="glibc",
        package_manager="apt",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=4,
        total_memory_mb=8192,
    )
    assert p1.arch_label == "amd64"

    p2 = PlatformInfo(
        os=OsType.DARWIN,
        distro=Distro.UNKNOWN,
        distro_version="",
        arch="arm64",
        libc="glibc",
        package_manager="brew",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=8,
        total_memory_mb=16384,
    )
    assert p2.arch_label == "arm64"

    p3 = PlatformInfo(
        os=OsType.LINUX,
        distro=Distro.DEBIAN,
        distro_version="",
        arch="armv7l",
        libc="glibc",
        package_manager="apt",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=2,
        total_memory_mb=2048,
    )
    assert p3.arch_label == "arm"


def test_detect_platform():
    plat = detect_platform()
    assert plat.os in (OsType.LINUX, OsType.DARWIN, OsType.WINDOWS, OsType.UNKNOWN)
    assert plat.cpu_count >= 1


def test_get_total_memory_mb():
    mem = _get_total_memory_mb()
    assert mem >= 0


def test_detect_distro():
    distro, ver = _detect_distro()
    assert isinstance(distro, Distro)


def test_detect_package_manager():
    assert _detect_package_manager(OsType.DARWIN, Distro.UNKNOWN) in ("brew", "none")

    def mock_which(name):
        return (
            f"/bin/{name}"
            if name in ("choco", "pacman", "dnf", "apk", "zypper", "emerge", "xbps-install")
            else None
        )

    with patch("shutil.which", side_effect=lambda n: "/bin/winget" if n == "winget" else None):
        assert _detect_package_manager(OsType.WINDOWS, Distro.UNKNOWN) == "winget"

    with patch("shutil.which", side_effect=lambda n: "/bin/choco" if n == "choco" else None):
        assert _detect_package_manager(OsType.WINDOWS, Distro.UNKNOWN) == "choco"

    with patch("shutil.which", return_value=None):
        assert _detect_package_manager(OsType.WINDOWS, Distro.UNKNOWN) == "none"

    with patch(
        "shutil.which", side_effect=lambda n: "/usr/bin/apt-get" if n == "apt-get" else None
    ):
        assert _detect_package_manager(OsType.LINUX, Distro.UBUNTU) == "apt"

    with patch("shutil.which", side_effect=lambda n: "/usr/bin/dnf" if n == "dnf" else None):
        assert _detect_package_manager(OsType.LINUX, Distro.FEDORA) == "dnf"

    with patch("shutil.which", side_effect=lambda n: "/sbin/apk" if n == "apk" else None):
        assert _detect_package_manager(OsType.LINUX, Distro.ALPINE) == "apk"

    with patch("shutil.which", side_effect=lambda n: "/usr/bin/pacman" if n == "pacman" else None):
        assert _detect_package_manager(OsType.LINUX, Distro.ARCH) == "pacman"

    with patch("shutil.which", side_effect=lambda n: "/usr/bin/zypper" if n == "zypper" else None):
        assert _detect_package_manager(OsType.LINUX, Distro.OPENSUSE) == "zypper"

    with patch("shutil.which", side_effect=lambda n: "/usr/bin/emerge" if n == "emerge" else None):
        assert _detect_package_manager(OsType.LINUX, Distro.GENTOO) == "portage"

    with patch(
        "shutil.which",
        side_effect=lambda n: "/usr/bin/xbps-install" if n == "xbps-install" else None,
    ):
        assert _detect_package_manager(OsType.LINUX, Distro.VOID) == "xbps"


def test_which_and_is_available():
    assert is_available("python3") or is_available("pytest")
    assert which("completely_nonexistent_binary_xyz_12345") is None


def test_detect_python_installer(tmp_path):
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        (tmp_path / "uv.lock").touch()
        with patch("sago.tools.ensure_dep.is_available", return_value=True):
            assert _detect_python_installer() == "uv"


def test_detect_js_installer(tmp_path):
    (tmp_path / "bun.lockb").touch()
    with patch("sago.tools.ensure_dep.is_available", return_value=True):
        assert _detect_js_installer(tmp_path) == "bun"

    (tmp_path / "bun.lockb").unlink()
    (tmp_path / "pnpm-lock.yaml").touch()
    with patch("sago.tools.ensure_dep.is_available", return_value=True):
        assert _detect_js_installer(tmp_path) == "pnpm"

    (tmp_path / "pnpm-lock.yaml").unlink()
    (tmp_path / "yarn.lock").touch()
    with patch("sago.tools.ensure_dep.is_available", return_value=True):
        assert _detect_js_installer(tmp_path) == "yarn"

    (tmp_path / "yarn.lock").unlink()
    (tmp_path / "package-lock.json").touch()
    with patch("sago.tools.ensure_dep.is_available", return_value=True):
        assert _detect_js_installer(tmp_path) == "npm"


def test_install_pip_package():
    with patch("sago.tools.ensure_dep._run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        ok, msg = install_pip_package("requests")
        assert ok is True
        assert "Installed" in msg

        # Failure case
        mock_proc.returncode = 1
        mock_proc.stderr = "No matching distribution"
        ok, msg = install_pip_package("requests")
        assert ok is False


def test_install_via_pm():
    # Unsupported
    ok, msg = _install_via_pm("unsupported_pm", "some-pkg")
    assert ok is False
    assert "No supported package manager" in msg

    # Supported
    with patch("sago.tools.ensure_dep._run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        ok, msg = _install_via_pm("apt", "curl")
        assert ok is True

        mock_proc.returncode = 1
        mock_proc.stderr = "E: Unable to locate package"
        ok, msg = _install_via_pm("apt", "curl")
        assert ok is False


def test_install_playwright_and_httpx():
    with (
        patch(
            "sago.tools.ensure_dep.install_pip_package",
            return_value=(True, "ok"),
        ),
        patch("sago.tools.ensure_dep._run") as mock_run,
    ):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        ok, msg = install_playwright()
        assert ok is True

        ok_h, msg_h = install_httpx()
        assert ok_h is True


def test_ensure_pip_package():
    # Already installed
    ok, msg = ensure_pip_package("sys")
    assert ok is True
    assert "already installed" in msg

    # Missing
    with patch(
        "sago.tools.ensure_dep.install_pip_package",
        return_value=(True, "Installed"),
    ):
        ok, msg = ensure_pip_package("nonexistent_package_12345")
        assert ok is True


def test_ensure_binary():
    # Found
    with patch("sago.tools.ensure_dep.which", return_value="/usr/bin/git"):
        ok, msg = ensure_binary("git")
        assert ok is True

    # Not found, auto_install=False
    with patch("sago.tools.ensure_dep.which", return_value=None):
        ok, msg = ensure_binary("nonexistent", auto_install=False)
        assert ok is False

        # No installer available
        ok, msg = ensure_binary("nonexistent", auto_install=True)
        assert ok is False
        assert "No auto-installer available" in msg


def test_docker_installer_branches():
    p_mac = PlatformInfo(
        os=OsType.DARWIN,
        distro=Distro.UNKNOWN,
        distro_version="",
        arch="arm64",
        libc="glibc",
        package_manager="brew",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=8,
        total_memory_mb=16384,
    )
    ok, msg = _install_docker(p_mac)
    assert ok is False
    assert "Docker Desktop for Mac" in msg

    p_win = PlatformInfo(
        os=OsType.WINDOWS,
        distro=Distro.UNKNOWN,
        distro_version="",
        arch="x86_64",
        libc="glibc",
        package_manager="winget",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=8,
        total_memory_mb=16384,
    )
    ok, msg = _install_docker(p_win)
    assert ok is False
    assert "Docker Desktop for Windows" in msg


def test_k3s_installer_branches():
    p_mac = PlatformInfo(
        os=OsType.DARWIN,
        distro=Distro.UNKNOWN,
        distro_version="",
        arch="arm64",
        libc="glibc",
        package_manager="brew",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=8,
        total_memory_mb=16384,
    )
    ok, msg = _install_k3s(p_mac)
    assert ok is False
    assert "only runs on Linux" in msg

    p_linux = PlatformInfo(
        os=OsType.LINUX,
        distro=Distro.UBUNTU,
        distro_version="22.04",
        arch="x86_64",
        libc="glibc",
        package_manager="apt",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=4,
        total_memory_mb=8192,
    )
    with (
        patch("sago.tools.ensure_dep._run"),
        patch("sago.tools.ensure_dep.is_available", return_value=True),
    ):
        ok, msg = _install_k3s(p_linux)
        assert ok is True
        assert "k3s installed" in msg


def test_kubectl_installer_branches():
    p_linux = PlatformInfo(
        os=OsType.LINUX,
        distro=Distro.UBUNTU,
        distro_version="22.04",
        arch="x86_64",
        libc="glibc",
        package_manager="apt",
        is_wsl=False,
        is_container=True,  # is_container=True skips k3s branch and goes straight to kubectl!
        python_version="3.11",
        cpu_count=4,
        total_memory_mb=8192,
    )
    with (
        patch("sago.tools.ensure_dep._run"),
        patch("sago.tools.ensure_dep.is_available", return_value=True),
    ):
        ok, msg = _install_kubectl(p_linux)
        assert ok is True
        assert "kubectl installed successfully" in msg


def test_node_installer_branches():
    p_linux = PlatformInfo(
        os=OsType.LINUX,
        distro=Distro.UBUNTU,
        distro_version="22.04",
        arch="x86_64",
        libc="glibc",
        package_manager="apt",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=4,
        total_memory_mb=8192,
    )
    with (
        patch("sago.tools.ensure_dep._run"),
        patch("sago.tools.ensure_dep._install_via_pm", return_value=(True, "Installed nodejs")),
        patch("sago.tools.ensure_dep.is_available", return_value=True),
    ):
        ok, msg = _install_node(p_linux)
        assert ok is True


def test_chromium_installer_branches():
    p_linux = PlatformInfo(
        os=OsType.LINUX,
        distro=Distro.UBUNTU,
        distro_version="22.04",
        arch="x86_64",
        libc="glibc",
        package_manager="apt",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=4,
        total_memory_mb=8192,
    )
    # Case 1: Playwright succeeds
    with patch("sago.tools.ensure_dep.install_playwright", return_value=(True, "Playwright ready")):
        ok, msg = _install_chromium(p_linux)
        assert ok is True

    # Case 2: Playwright fails, system pm succeeds
    with (
        patch("sago.tools.ensure_dep.install_playwright", return_value=(False, "failed")),
        patch("sago.tools.ensure_dep._install_via_pm", return_value=(True, "Installed chromium")),
    ):
        ok, msg = _install_chromium(p_linux)
        assert ok is True


def test_docker_linux_branches():
    p_ubuntu = PlatformInfo(
        os=OsType.LINUX,
        distro=Distro.UBUNTU,
        distro_version="22.04",
        arch="x86_64",
        libc="glibc",
        package_manager="apt",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=4,
        total_memory_mb=8192,
    )
    with (
        patch("sago.tools.ensure_dep._run") as mock_run,
        patch("sago.tools.ensure_dep.is_available", return_value=True),
    ):
        mock_run.return_value = MagicMock(returncode=0)
        ok, msg = _install_docker(p_ubuntu)
        assert ok is True
        assert "Docker Engine installed" in msg

    p_centos = PlatformInfo(
        os=OsType.LINUX,
        distro=Distro.CENTOS,
        distro_version="7",
        arch="x86_64",
        libc="glibc",
        package_manager="yum",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=4,
        total_memory_mb=8192,
    )
    with (
        patch("sago.tools.ensure_dep._run") as mock_run,
        patch("sago.tools.ensure_dep.is_available", return_value=True),
    ):
        mock_run.return_value = MagicMock(returncode=0)
        ok, msg = _install_docker(p_centos)
        assert ok is True


def test_kubectl_darwin_and_fallback():
    p_mac = PlatformInfo(
        os=OsType.DARWIN,
        distro=Distro.UNKNOWN,
        distro_version="",
        arch="arm64",
        libc="glibc",
        package_manager="brew",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=8,
        total_memory_mb=16384,
    )
    with patch("sago.tools.ensure_dep._install_via_pm", return_value=(True, "Installed kubectl")):
        ok, msg = _install_kubectl(p_mac)
        assert ok is True


def test_node_darwin_and_windows():
    p_mac = PlatformInfo(
        os=OsType.DARWIN,
        distro=Distro.UNKNOWN,
        distro_version="",
        arch="arm64",
        libc="glibc",
        package_manager="brew",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=8,
        total_memory_mb=16384,
    )
    with patch("sago.tools.ensure_dep._install_via_pm", return_value=(True, "Installed node")):
        ok, msg = _install_node(p_mac)
        assert ok is True

    p_win = PlatformInfo(
        os=OsType.WINDOWS,
        distro=Distro.UNKNOWN,
        distro_version="",
        arch="x86_64",
        libc="glibc",
        package_manager="winget",
        is_wsl=False,
        is_container=False,
        python_version="3.11",
        cpu_count=8,
        total_memory_mb=16384,
    )
    ok, msg = _install_node(p_win)
    assert ok is False
    assert "Install Node.js: winget" in msg
