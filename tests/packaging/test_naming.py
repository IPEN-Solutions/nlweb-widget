from pathlib import Path


def test_no_framework_shadowing_modules() -> None:
    forbidden = {
        "fastapi.py",
        "flask.py",
        "django.py",
        "starlette.py",
        "asyncio.py",
        "typing.py",
        "http.py",
    }
    root = Path("src/nlweb_widget")
    assert not any(path.name in forbidden for path in root.rglob("*.py"))


def test_examples_are_not_packaged() -> None:
    assert not Path("examples").exists()
