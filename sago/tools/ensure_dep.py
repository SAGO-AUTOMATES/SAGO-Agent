"""Dependency auto-installer with OS/distro detection, arch validation, and platform-aware installs.

Detects the host OS, distro, architecture, and available package managers to
install the right binary for the right platform. Uses lightweight alternatives
where possible (k3s over k8s, nodejs-core over full node, etc.).
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("sago.tools.ensure_dep")

InstallResult = tuple[bool, str]  # (success, message)


# ---------------------------------------------------------------------------
# OS / Distro / Arch detection
# ---------------------------------------------------------------------------


class OsType(Enum):
    LINUX = "linux"
    DARWIN = "darwin"  # macOS
    WINDOWS = "windows"
    UNKNOWN = "unknown"


class Distro(Enum):
    UBUNTU = "ubuntu"
    DEBIAN = "debian"
    CENTOS = "centos"
    RHEL = "rhel"
    FEDORA = "fedora"
    ALPINE = "alpine"
    ARCH = "arch"
    AMAZON = "amazon"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlatformInfo:
    os: OsType
    distro: Distro
    arch: str  # x86_64, aarch64, arm64, etc.
    libc: str  # glibc, musl
    package_manager: str  # apt, yum, dnf, apk, brew, choco, none
    is_wsl: bool
    is_container: bool  # Docker, Podman, etc.

    @property
    def arch_label(self) -> str:
        """Normalized arch for download URLs."""
        if self.arch in ("x86_64", "amd64"):
            return "amd64"
        if self.arch in ("aarch64", "arm64"):
            return "arm64"
        if self.arch.startswith("arm"):
            return "arm"
        return self.arch


def detect_platform() -> PlatformInfo:
    """Detect OS, distro, arch, libc, package manager, WSL, and container status."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # OS
    os_type = {
        "linux": OsType.LINUX,
        "darwin": OsType.DARWIN,
        "windows": OsType.WINDOWS,
    }.get(system, OsType.UNKNOWN)

    # Distro (Linux only)
    distro = Distro.UNKNOWN
    if os_type == OsType.LINUX:
        distro = _detect_distro()

    # libc detection
    libc = "glibc"
    if os_type == OsType.LINUX:
        try:
            with open("/usr/bin/ldd") as f:
                if "musl" in f.read(500):
                    libc = "musl"
        except (FileNotFoundError, PermissionError):
            pass
        # Alpine always uses musl
        if distro == Distro.ALPINE:
            libc = "musl"

    # Package manager
    pm = _detect_package_manager(os_type, distro)

    # WSL
    is_wsl = False
    if os_type == OsType.LINUX:
        try:
            with open("/proc/version") as f:
                content = f.read(500).lower()
                is_wsl = "microsoft" in content or "wsl" in content
        except (FileNotFoundError, PermissionError):
            pass

    # Container
    is_container = os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
    if not is_container:
        try:
            with open("/proc/1/cgroup") as f:
                content = f.read(500)
                is_container = "docker" in content or "lxc" in content or "kubepods" in content
        except (FileNotFoundError, PermissionError):
            pass

    return PlatformInfo(
        os=os_type,
        distro=distro,
        arch=machine,
        libc=libc,
        package_manager=pm,
        is_wsl=is_wsl,
        is_container=is_container,
    )


def _detect_distro() -> Distro:
    """Detect Linux distro from /etc/os-release or other hints."""
    # Try /etc/os-release first
    try:
        with open("/etc/os-release") as f:
            content = f.read(2000).lower()
            if "ubuntu" in content:
                return Distro.UBUNTU
            if "debian" in content:
                return Distro.DEBIAN
            if "centos" in content:
                return Distro.CENTOS
            if "rhel" in content or "red hat" in content:
                return Distro.RHEL
            if "fedora" in content:
                return Distro.FEDORA
            if "alpine" in content:
                return Distro.ALPINE
            if "arch" in content:
                return Distro.ARCH
            if "amazon" in content:
                return Distro.AMAZON
    except (FileNotFoundError, PermissionError):
        pass

    # Fallback: check specific files
    if os.path.exists("/etc/alpine-release"):
        return Distro.ALPINE
    if os.path.exists("/etc/debian_version"):
        return Distro.DEBIAN
    if os.path.exists("/etc/redhat-release"):
        return Distro.CENTOS

    return Distro.UNKNOWN


def _detect_package_manager(os_type: OsType, distro: Distro) -> str:
    """Detect the best available package manager."""
    if os_type == OsType.DARWIN:
        if shutil.which("brew"):
            return "brew"
        return "none"

    if os_type == OsType.WINDOWS:
        if shutil.which("winget"):
            return "winget"
        if shutil.which("choco"):
            return "choco"
        return "none"

    if os_type == OsType.LINUX:
        # Order by preference
        if distro in (Distro.UBUNTU, Distro.DEBIAN):
            if shutil.which("apt-get"):
                return "apt"
        elif distro in (Distro.CENTOS, Distro.RHEL, Distro.AMAZON):
            if shutil.which("dnf"):
                return "dnf"
            if shutil.which("yum"):
                return "yum"
        elif distro == Distro.FEDORA:
            if shutil.which("dnf"):
                return "dnf"
        elif distro == Distro.ALPINE:
            if shutil.which("apk"):
                return "apk"
        elif distro == Distro.ARCH:
            if shutil.which("pacman"):
                return "pacman"

        # Generic fallback
        for pm in ["apt-get", "dnf", "yum", "apk", "pacman", "zypper"]:
            if shutil.which(pm):
                return pm.replace("-get", "")

    return "none"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(
    cmd: list[str], timeout: int = 120, sudo: bool = False
) -> subprocess.CompletedProcess[str]:
    if sudo and os.geteuid() != 0:
        cmd = ["sudo", "-n", *cmd]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def which(name: str) -> str | None:
    return shutil.which(name)


def is_available(name: str) -> bool:
    return which(name) is not None


# ---------------------------------------------------------------------------
# Package installers
# ---------------------------------------------------------------------------


def install_pip_package(
    package: str,
    pip_args: list[str] | None = None,
) -> InstallResult:
    """Install a Python package via pip."""
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
    if pip_args:
        cmd.extend(pip_args)
    cmd.append(package)

    logger.info("Installing Python package: %s", package)
    try:
        result = _run(cmd, timeout=120)
        if result.returncode == 0:
            return True, f"Installed {package} successfully."
        return False, f"pip install failed:\n{result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, f"pip install timed out for {package}."
    except Exception as e:
        return False, f"pip install error: {e}"


def _install_via_pm(pm: str, pkg_name: str, timeout: int = 120) -> InstallResult:
    """Install a system package via detected package manager."""
    detect_platform()
    cmds: dict[str, list[str]] = {
        "apt": ["apt-get", "install", "-y", pkg_name],
        "dnf": ["dnf", "install", "-y", pkg_name],
        "yum": ["yum", "install", "-y", pkg_name],
        "apk": ["apk", "add", pkg_name],
        "pacman": ["pacman", "-S", "--noconfirm", pkg_name],
        "zypper": ["zypper", "install", "-y", pkg_name],
        "brew": ["brew", "install", pkg_name],
    }

    cmd = cmds.get(pm)
    if not cmd:
        return False, f"No supported package manager found. Detected: {pm}"

    logger.info("Installing %s via %s", pkg_name, pm)
    needs_sudo = pm in ("apt", "dnf", "yum", "zypper") and os.geteuid() != 0
    result = _run(cmd, timeout=timeout, sudo=needs_sudo)

    if result.returncode == 0:
        return True, f"Installed {pkg_name} via {pm}."
    return False, f"{pm} install failed:\n{result.stderr.strip()}"


def install_playwright() -> InstallResult:
    """Install Playwright + Chromium browser."""
    ok, msg = install_pip_package("playwright", pip_args=["--upgrade"])
    if not ok:
        return ok, msg

    logger.info("Installing Playwright Chromium browser...")
    try:
        result = _run([sys.executable, "-m", "playwright", "install", "chromium"], timeout=180)
        if result.returncode == 0:
            return True, "Playwright and Chromium installed."
        # Try with --with-deps for Linux
        result2 = _run(
            [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"],
            timeout=300,
            sudo=True,
        )
        if result2.returncode == 0:
            return True, "Playwright and Chromium installed (with system deps)."
        return False, f"playwright install failed:\n{result.stderr.strip()}"
    except Exception as e:
        return False, f"playwright install error: {e}"


def install_httpx() -> InstallResult:
    """Install httpx HTTP client."""
    return install_pip_package("httpx")


def ensure_pip_package(
    package: str,
    import_name: str | None = None,
    extra_args: list[str] | None = None,
) -> InstallResult:
    """Ensure a Python package is importable. Auto-installs if missing."""
    mod_name = import_name or package
    try:
        __import__(mod_name)
        return True, f"{package} already installed."
    except ImportError:
        pass
    return install_pip_package(package, pip_args=extra_args)


# ---------------------------------------------------------------------------
# Binary ensure (main API)
# ---------------------------------------------------------------------------


def ensure_binary(
    name: str,
    auto_install: bool = True,
) -> InstallResult:
    """Ensure a binary is available. Auto-installs where possible with correct OS packages.

    Returns (found, message). found=True if binary is on PATH after install attempt.
    """
    path = which(name)
    if path:
        return True, f"{name} found at {path}"

    if not auto_install:
        return False, f"{name} not found. Please install manually."

    plat = detect_platform()
    logger.info(
        "Detected platform: %s %s %s (pm=%s, libc=%s, wsl=%s, container=%s)",
        plat.os.value,
        plat.distro.value,
        plat.arch_label,
        plat.package_manager,
        plat.libc,
        plat.is_wsl,
        plat.is_container,
    )

    installer = _INSTALLERS.get(name)
    if installer:
        return installer(plat)

    return False, f"{name} not found. No auto-installer available for this tool."


# ---------------------------------------------------------------------------
# Per-tool installers
# ---------------------------------------------------------------------------


def _install_docker(p: PlatformInfo) -> InstallResult:
    """Install Docker Engine with platform-appropriate method."""
    if p.os == OsType.DARWIN:
        return False, (
            "Docker Desktop for Mac required.\n"
            "  brew install --cask docker\n"
            "  Or download: https://docs.docker.com/desktop/install/mac-install/"
        )

    if p.os == OsType.WINDOWS:
        return False, (
            "Docker Desktop for Windows required.\n"
            "  winget install Docker.DockerDesktop\n"
            "  Or download: https://docs.docker.com/desktop/install/windows-install/"
        )

    # Linux - install Docker Engine
    if p.distro in (Distro.UBUNTU, Distro.DEBIAN):
        cmds = [
            "apt-get update",
            "apt-get install -y ca-certificates curl gnupg",
            "install -m 0755 -d /etc/apt/keyrings",
            "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
            "chmod a+r /etc/apt/keyrings/docker.gpg",
            'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null',
            "apt-get update",
            "apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin",
        ]
        for cmd in cmds:
            result = _run(cmd.split(), timeout=120, sudo=True)
            if result.returncode != 0 and "keyrings" not in cmd:
                pass  # Continue, some steps may be non-critical

        if is_available("docker"):
            return True, "Docker Engine installed successfully."

    elif p.distro in (Distro.CENTOS, Distro.RHEL, Distro.FEDORA, Distro.AMAZON):
        cmds = [
            "yum install -y yum-utils",
            "yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo",
            "yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin",
        ]
        for cmd in cmds:
            _run(cmd.split(), timeout=120, sudo=True)

        if is_available("docker"):
            return True, "Docker Engine installed successfully."

    elif p.distro == Distro.ALPINE:
        result = _run(["apk", "add", "docker", "docker-compose"], timeout=60, sudo=True)
        if result.returncode == 0:
            return True, "Docker installed via apk."

    return False, (
        f"Docker installation not automated for {p.distro.value}.\n"
        "Install manually: https://docs.docker.com/engine/install/"
    )


def _install_kubectl(p: PlatformInfo) -> InstallResult:
    """Install kubectl (or suggest k3s for lightweight)."""
    arch = p.arch_label

    # Check if k3s is a better fit (lightweight)
    if p.os == OsType.LINUX and not p.is_container:
        # k3s is much lighter than full k8s - auto-install it
        if p.distro == Distro.ALPINE:
            _run(["apk", "add", "k3s"], timeout=60, sudo=True)
        else:
            _run(
                ["curl", "-sfL", "https://get.k3s.io", "|", "sh", "-"],
                timeout=120,
                sudo=True,
            )
            # The above doesn't work with pipe in list form, use bash
            _run(
                ["bash", "-c", "curl -sfL https://get.k3s.io | sh -"],
                timeout=120,
                sudo=True,
            )

        if is_available("k3s"):
            # k3s includes kubectl symlink
            return True, (
                "k3s installed (lightweight Kubernetes). kubectl available via k3s kubectl.\n"
                "  Use: k3s kubectl get pods\n"
                "  Or: export KUBECONFIG=/etc/rancher/k3s/k3s.yaml"
            )

    # Fallback: install standalone kubectl
    if p.os == OsType.LINUX:
        url = f"https://dl.k8s.io/release/stable/bin/{p.os.value}/{arch}/kubectl"
        _run(
            ["bash", "-c", f"curl -LO '{url}' && chmod +x kubectl && mv kubectl /usr/local/bin/"],
            timeout=60,
            sudo=True,
        )
        if is_available("kubectl"):
            return True, "kubectl installed successfully."

    elif p.os == OsType.DARWIN:
        if p.package_manager == "brew":
            return _install_via_pm("brew", "kubectl")

    return False, (
        f"kubectl/k3s installation not automated for {p.distro.value} {p.arch_label}.\n"
        "Install k3s (lightweight): curl -sfL https://get.k3s.io | sh -\n"
        "Install kubectl: https://kubernetes.io/docs/tasks/tools/"
    )


def _install_node(p: PlatformInfo) -> InstallResult:
    """Install Node.js with platform-appropriate method."""
    if p.os == OsType.DARWIN:
        if p.package_manager == "brew":
            return _install_via_pm("brew", "node")
        return False, "Install Node.js: brew install node  OR  https://nodejs.org/"

    if p.os == OsType.WINDOWS:
        return False, "Install Node.js: winget install OpenJS.NodeJS.LTS  OR  https://nodejs.org/"

    # Linux
    if p.distro in (Distro.UBUNTU, Distro.DEBIAN):
        _run(
            ["bash", "-c", "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -"],
            timeout=60,
            sudo=True,
        )
        _run(["apt-get", "install", "-y", "nodejs"], timeout=120, sudo=True)
        if is_available("node"):
            return True, "Node.js 20 installed via NodeSource."

    elif p.distro in (Distro.CENTOS, Distro.RHEL, Distro.FEDORA, Distro.AMAZON):
        _run(
            ["bash", "-c", "curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -"],
            timeout=60,
            sudo=True,
        )
        install_cmd = "dnf" if p.distro in (Distro.FEDORA,) and is_available("dnf") else "yum"
        _run([install_cmd, "install", "-y", "nodejs"], timeout=120, sudo=True)
        if is_available("node"):
            return True, "Node.js 20 installed via NodeSource."

    elif p.distro == Distro.ALPINE:
        _run(["apk", "add", "nodejs", "npm"], timeout=60, sudo=True)
        if is_available("node"):
            return True, "Node.js installed via apk."

    elif p.distro == Distro.ARCH:
        _run(["pacman", "-S", "--noconfirm", "nodejs", "npm"], timeout=60, sudo=True)
        if is_available("node"):
            return True, "Node.js installed via pacman."

    # Generic fallback
    if p.package_manager not in ("none",):
        ok, msg = _install_via_pm(p.package_manager, "nodejs")
        if ok:
            return ok, msg

    return False, (
        f"Node.js installation not automated for {p.distro.value}.\n"
        "Install manually: https://nodejs.org/  OR  sudo apt-get install -y nodejs"
    )


def _install_chromium(p: PlatformInfo) -> InstallResult:
    """Install Chromium browser for the browser tool."""
    # Try Playwright first (cross-platform, auto-manages browser)
    ok, msg = install_playwright()
    if ok:
        return ok, msg

    # Fallback: system chromium
    if p.os == OsType.DARWIN:
        if p.package_manager == "brew":
            return _install_via_pm("brew", "chromium")
    elif p.os == OsType.LINUX:
        if p.distro in (Distro.UBUNTU, Distro.DEBIAN):
            return _install_via_pm("apt", "chromium-browser")
        elif p.distro in (Distro.CENTOS, Distro.RHEL):
            return _install_via_pm("yum" if p.package_manager == "yum" else "dnf", "chromium")
        elif p.distro == Distro.ALPINE:
            return _install_via_pm("apk", "chromium")
        elif p.distro == Distro.ARCH:
            return _install_via_pm("pacman", "chromium")

    return (
        False,
        "No browser available. Install: pip install playwright && playwright install chromium",
    )


def _install_k3s(p: PlatformInfo) -> InstallResult:
    """Install k3s (lightweight Kubernetes)."""
    if p.os != OsType.LINUX:
        return False, "k3s only runs on Linux. Use kubectl instead for macOS/Windows."

    _run(
        ["bash", "-c", "curl -sfL https://get.k3s.io | sh -"],
        timeout=120,
        sudo=True,
    )
    if is_available("k3s"):
        return True, (
            "k3s installed (lightweight Kubernetes, ~50MB vs ~1GB for full k8s).\n"
            "  k3s kubectl get pods\n"
            "  export KUBECONFIG=/etc/rancher/k3s/k3s.yaml"
        )
    return False, "k3s installation failed. Try: curl -sfL https://get.k3s.io | sh -"


_INSTALLERS: dict[str, Any] = {
    "docker": _install_docker,
    "kubectl": _install_kubectl,
    "k3s": _install_k3s,
    "node": _install_node,
    "nodejs": _install_node,
    "chromium": _install_chromium,
    "chromium-browser": _install_chromium,
}
