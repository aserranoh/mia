from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    # src/mia/_lib/build.py -> repository root
    return Path(__file__).resolve().parents[3]


def _run(command: list[str], cwd: Path) -> None:
    printable = " ".join(command)
    print(f"[run] ({cwd}) $ {printable}")
    subprocess.run(command, cwd=str(cwd), check=True)


def _require_tool(tool_name: str) -> None:
    if shutil.which(tool_name) is None:
        raise SystemExit(f"[error] Required tool not found in PATH: {tool_name}")


def _build_face(
    repo_root: Path,
    build_type: str,
    jobs: int,
) -> Path:
    _require_tool("cmake")

    face_source_dir = repo_root / "src" / "face"
    face_build_dir = face_source_dir / "build"

    if not face_source_dir.is_dir():
        raise SystemExit(f"[error] Face source directory not found: {face_source_dir}")

    configure_command = [
        "cmake",
        "-S",
        str(face_source_dir),
        "-B",
        str(face_build_dir),
        f"-DCMAKE_BUILD_TYPE={build_type}",
    ]
    try:
        _run(configure_command, cwd=repo_root)
    except subprocess.CalledProcessError as exc:
        # A stale CMake cache from a different source/build path is a common issue.
        # Remove generated CMake state and retry configuration once.
        if face_build_dir.exists():
            shutil.rmtree(face_build_dir)
        _run(configure_command, cwd=repo_root)
    _run(
        ["cmake", "--build", str(face_build_dir), "--parallel", str(jobs)],
        cwd=repo_root,
    )

    face_binary = face_build_dir / "face"
    if not face_binary.exists():
        raise SystemExit(f"[error] Face binary was not produced: {face_binary}")
    return face_binary


def _build_frontend(repo_root: Path, install_deps: bool) -> Path:
    _require_tool("npm")

    frontend_dir = repo_root / "src" / "frontend"
    if not frontend_dir.is_dir():
        raise SystemExit(f"[error] Frontend directory not found: {frontend_dir}")

    node_modules_dir = frontend_dir / "node_modules"
    if install_deps or not node_modules_dir.is_dir():
        _run(["npm", "ci"], cwd=frontend_dir)

    _run(["npm", "run", "build"], cwd=frontend_dir)

    dist_dir = frontend_dir / "dist"
    if not dist_dir.is_dir():
        raise SystemExit(f"[error] Frontend dist directory was not produced: {dist_dir}")
    return dist_dir


def _install_artifacts(
    install_prefix: Path,
    face_binary: Path | None,
    frontend_dist_dir: Path | None,
) -> None:
    print(f"[install] staging artifacts under: {install_prefix}")

    if face_binary is not None:
        bin_dir = install_prefix / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)

        target_face_binary = bin_dir / "face"
        shutil.copy2(face_binary, target_face_binary)
        target_face_binary.chmod(0o755)
        print(f"[install] face binary -> {target_face_binary}")

    if frontend_dist_dir is not None:
        target_ui_dir = install_prefix / "ui"
        if target_ui_dir.exists():
            shutil.rmtree(target_ui_dir)
        shutil.copytree(frontend_dist_dir, target_ui_dir)
        print(f"[install] frontend dist -> {target_ui_dir}")


def _load_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Maia application components (face + frontend).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_repo_root(),
        help="Repository root path.",
    )
    parser.add_argument(
        "--mode",
        choices=("dev", "install"),
        default="dev",
        help="'dev' only builds; 'install' builds and stages artifacts under --install-prefix.",
    )
    parser.add_argument(
        "--install-prefix",
        type=Path,
        default=Path("/var/lib/maia"),
        help="Install target prefix used when --mode install.",
    )
    parser.add_argument(
        "--skip-face",
        action="store_true",
        help="Skip building the face C++ binary.",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip building the frontend assets.",
    )
    parser.add_argument(
        "--frontend-install-deps",
        action="store_true",
        help="Force frontend dependency installation using npm ci before build.",
    )
    parser.add_argument(
        "--face-build-type",
        default="Release",
        help="CMake build type for face binary (for example: Debug, Release).",
    )
    parser.add_argument(
        "--face-jobs",
        type=int,
        default=max(1, os.cpu_count() or 1),
        help="Parallel jobs for CMake build.",
    )
    return parser.parse_args()


def main() -> int:
    args = _load_args()
    repo_root: Path = args.repo_root.resolve()

    face_binary: Path | None = None
    frontend_dist_dir: Path | None = None

    try:
        if args.skip_face and args.skip_frontend:
            print("[warn] Nothing to build: both --skip-face and --skip-frontend were provided.")
            return 0

        if not args.skip_face:
            face_binary = _build_face(
                repo_root=repo_root,
                build_type=args.face_build_type,
                jobs=args.face_jobs,
            )
            print(f"[ok] face binary: {face_binary}")

        if not args.skip_frontend:
            frontend_dist_dir = _build_frontend(
                repo_root=repo_root,
                install_deps=args.frontend_install_deps,
            )
            print(f"[ok] frontend dist: {frontend_dist_dir}")

        if args.mode == "install":
            _install_artifacts(
                install_prefix=args.install_prefix.resolve(),
                face_binary=face_binary,
                frontend_dist_dir=frontend_dist_dir,
            )

        print("[done] build completed successfully")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"[error] command failed with exit code {exc.returncode}: {exc.cmd}", file=sys.stderr)
        return exc.returncode


if __name__ == "__main__":
    raise SystemExit(main())