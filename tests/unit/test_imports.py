"""Test objects are importable that should be importable."""


import skywriter


def test_skyreader_imports() -> None:
    """Test importing from 'skyreader'."""
    assert hasattr(skywriter, "i3_to_json")
