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
    OPENSUSE = "opensuse"
    SLES = "sles"
    ROCKY = "rocky"
    ALMA = "alma"
    GENTOO = "gentoo"
    NIXOS = "nixos"
    VOID = "void"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlatformInfo:
    os: OsType
    distro: Distro
    distro_version: str  # e.g. "22.04", "9.3", ""
    arch: str  # x86_64, aarch64, arm64, etc.
    libc: str  # glibc, musl
    package_manager: str  # apt, yum, dnf, apk, brew, choco, nix, zypper, none
    is_wsl: bool
    is_container: bool  # Docker, Podman, etc.
    python_version: str  # e.g. "3.11.16"
    cpu_count: int
    total_memory_mb: int

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
    distro, distro_version = _detect_distro()

    # libc detection
    libc = "glibc"
    if os_type == OsType.LINUX:
        try:
            with open("/usr/bin/ldd") as f:
                if "musl" in f.read(500):
                    libc = "musl"
        except (FileNotFoundError, PermissionError):
            pass
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

    # System info
    python_version = platform.python_version()
    cpu_count = os.cpu_count() or 1
    total_memory_mb = _get_total_memory_mb()

    return PlatformInfo(
        os=os_type,
        distro=distro,
        distro_version=distro_version,
        arch=machine,
        libc=libc,
        package_manager=pm,
        is_wsl=is_wsl,
        is_container=is_container,
        python_version=python_version,
        cpu_count=cpu_count,
        total_memory_mb=total_memory_mb,
    )


def _get_total_memory_mb() -> int:
    """Get total system memory in MB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    # Format: "MemTotal:   16384000 kB"
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) // 1024
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    # macOS fallback
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return int(result.stdout.strip()) // (1024 * 1024)
    except Exception:
        pass
    # Windows fallback
    if platform.system().lower() == "windows":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            c_ulonglong = ctypes.c_ulonglong

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", c_ulonglong),
                ]

            mem = MEMORYSTATUSEX()
            mem.dwLength = ctypes.sizeof(mem)
            kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
            return mem.ullTotalPhys // (1024 * 1024)
        except Exception:
            pass
    return 0


def _detect_distro() -> tuple[Distro, str]:
    """Detect Linux distro from /etc/os-release or other hints. Returns (distro, version)."""
    distro = Distro.UNKNOWN
    version = ""

    # Try /etc/os-release first
    try:
        with open("/etc/os-release") as f:
            content = f.read(2000).lower()
            # Extract version_id
            for line in content.splitlines():
                if line.startswith("version_id="):
                    version = line.split("=", 1)[1].strip().strip('"')
                    break

            if "ubuntu" in content:
                distro = Distro.UBUNTU
            elif "debian" in content:
                distro = Distro.DEBIAN
            elif "centos" in content:
                distro = Distro.CENTOS
            elif "rhel" in content or "red hat" in content:
                distro = Distro.RHEL
            elif "fedora" in content:
                distro = Distro.FEDORA
            elif "alpine" in content:
                distro = Distro.ALPINE
            elif "arch" in content:
                distro = Distro.ARCH
            elif "amazon" in content:
                distro = Distro.AMAZON
            elif "opensuse" in content or "suse" in content:
                distro = Distro.OPENSUSE
            elif "sles" in content:
                distro = Distro.SLES
            elif "rocky" in content:
                distro = Distro.ROCKY
            elif "almalinux" in content or "alma" in content:
                distro = Distro.ALMA
            elif "gentoo" in content:
                distro = Distro.GENTOO
            elif "nixos" in content:
                distro = Distro.NIXOS
            elif "void" in content:
                distro = Distro.VOID
    except (FileNotFoundError, PermissionError):
        pass

    # Fallback: check specific files
    if distro == Distro.UNKNOWN:
        if os.path.exists("/etc/alpine-release"):
            distro = Distro.ALPINE
            try:
                version = open("/etc/alpine-release").read().strip()
            except Exception:
                pass
        elif os.path.exists("/etc/debian_version"):
            distro = Distro.DEBIAN
            try:
                version = open("/etc/debian_version").read().strip()
            except Exception:
                pass
        elif os.path.exists("/etc/redhat-release"):
            distro = Distro.CENTOS
        elif os.path.exists("/etc/gentoo-release"):
            distro = Distro.GENTOO
        elif os.path.exists("/etc/NIXOS"):
            distro = Distro.NIXOS

    return distro, version


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
        if shutil.which("scoop"):
            return "scoop"
        return "none"

    if os_type == OsType.LINUX:
        # NixOS
        if distro == Distro.NIXOS:
            if shutil.which("nix-env"):
                return "nix"

        # Distro-specific preference
        if distro in (Distro.UBUNTU, Distro.DEBIAN):
            if shutil.which("apt-get"):
                return "apt"
        elif distro in (Distro.CENTOS, Distro.RHEL, Distro.AMAZON, Distro.ROCKY, Distro.ALMA):
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
        elif distro in (Distro.OPENSUSE, Distro.SLES):
            if shutil.which("zypper"):
                return "zypper"
        elif distro == Distro.GENTOO:
            if shutil.which("emerge"):
                return "portage"
        elif distro == Distro.VOID:
            if shutil.which("xbps-install"):
                return "xbps"

        # Generic fallback
        for pm in ["apt-get", "dnf", "yum", "apk", "pacman", "zypper", "xbps-install"]:
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
    """Find a binary by checking PATH and common installation directories.

    Checks standard PATH first, then expands search to common user-local
    installation directories that may not be in PATH (e.g. ~/.local/bin,
    ~/.cargo/bin, NVM, pyenv, Go, etc.).
    """
    # Standard PATH check first
    path = shutil.which(name)
    if path:
        return path

    # Common installation directories to search
    home = os.path.expanduser("~")
    search_dirs = [
        os.path.join(home, ".local", "bin"),
        os.path.join(home, ".cargo", "bin"),
        os.path.join(home, "go", "bin"),
        os.path.join(home, ".pyenv", "shims"),
        os.path.join(home, ".npm-global", "bin"),
        os.path.join(home, ".yarn", "bin"),
        os.path.join(home, ".local", "share", "nvim", "mason", "bin"),
        os.path.join(home, ".kube", "bin"),
    ]

    # NVM: check all installed node versions
    nvm_dir = os.path.join(home, ".nvm", "versions", "node")
    if os.path.isdir(nvm_dir):
        try:
            for node_dir in sorted(os.listdir(nvm_dir), reverse=True):
                search_dirs.append(os.path.join(nvm_dir, node_dir, "bin"))
        except OSError:
            pass

    # System-local dirs
    search_dirs.extend(
        [
            "/usr/local/bin",
            "/usr/local/sbin",
            "/opt/homebrew/bin",
            "/snap/bin",
        ]
    )

    for d in search_dirs:
        candidate = os.path.join(d, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        # Windows: check for .exe/.cmd/.bat
        if platform.system().lower() == "windows":
            for ext in (".exe", ".cmd", ".bat"):
                candidate_ext = candidate + ext
                if os.path.isfile(candidate_ext) and os.access(candidate_ext, os.X_OK):
                    return candidate_ext

    return None


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
    cmds: dict[str, list[str]] = {
        "apt": ["apt-get", "install", "-y", pkg_name],
        "dnf": ["dnf", "install", "-y", pkg_name],
        "yum": ["yum", "install", "-y", pkg_name],
        "apk": ["apk", "add", pkg_name],
        "pacman": ["pacman", "-S", "--noconfirm", pkg_name],
        "zypper": ["zypper", "install", "-y", pkg_name],
        "brew": ["brew", "install", pkg_name],
        "nix": ["nix-env", "-iA", f"nixpkgs.{pkg_name}"],
        "xbps": ["xbps-install", "-Sy", pkg_name],
        "portage": ["emerge", pkg_name],
        "winget": ["winget", "install", "--id", pkg_name, "--accept-package-agreements"],
        "choco": ["choco", "install", pkg_name, "-y"],
        "scoop": ["scoop", "install", pkg_name],
    }

    cmd = cmds.get(pm)
    if not cmd:
        return False, f"No supported package manager found. Detected: {pm}"

    logger.info("Installing %s via %s", pkg_name, pm)
    needs_sudo = pm in ("apt", "dnf", "yum", "zypper", "xbps", "portage") and os.geteuid() != 0
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
    force_reinstall: bool = False,
) -> InstallResult:
    """Ensure a binary is available. Auto-installs where possible with correct OS packages.

    Before installing, checks:
    1. Standard PATH
    2. Common user-local directories (~/.local/bin, ~/.cargo/bin, NVM, etc.)

    Returns (found, message). found=True if binary is on PATH after install attempt.
    """
    if not force_reinstall:
        path = which(name)
        if path:
            # Check if it's in a non-standard location
            standard_paths = os.environ.get("PATH", "").split(os.pathsep)
            if not any(os.path.normpath(p) in os.path.normpath(path) for p in standard_paths):
                return True, f"{name} found at {path} (non-standard location)"
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
            ["curl", "-LO", url],
            timeout=60,
            sudo=True,
        )
        _run(
            ["chmod", "+x", "kubectl"],
            timeout=10,
            sudo=True,
        )
        _run(
            ["mv", "kubectl", "/usr/local/bin/"],
            timeout=10,
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
