from nlweb_widget.cli import main


def test_cli_module_is_framework_neutral() -> None:
    assert callable(main)
