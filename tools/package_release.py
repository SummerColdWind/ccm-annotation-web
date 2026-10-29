"""Build a source-only archive suitable for GitHub or server upload."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("app", "static", "design", "tests", "deploy", ".github", "tools")
FILES = (".gitignore", ".dockerignore", ".env.example", "Dockerfile", "compose.yaml", "requirements.txt", "requirements-dev.txt", "README.md")


def main():
    output = ROOT / "dist" / "ccm-annotation-web.zip"
    output.parent.mkdir(exist_ok=True)
    files = [ROOT / name for name in FILES]
    for directory in DIRECTORIES:
        files.extend(p for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            relative = path.relative_to(ROOT)
            if path.name == ".env" or ".sqlite" in path.name or relative.parts[0] in {"data", "output"}:
                raise ValueError(f"Runtime file cannot be packaged: {relative}")
            archive.write(path, "ccm-annotation-web/" + relative.as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive verification failed")
    print(f"Source files: {len(files)}")
    print(f"Archive: {output}")
    print(f"Size: {output.stat().st_size / 1024 / 1024:.2f} MiB")


if __name__ == "__main__":
    main()
