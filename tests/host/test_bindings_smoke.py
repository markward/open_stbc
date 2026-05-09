"""Smoke test: _open_stbc_host module imports and exposes init/shutdown."""


def test_module_imports():
    import _open_stbc_host
    assert hasattr(_open_stbc_host, "init")
    assert hasattr(_open_stbc_host, "shutdown")


def test_init_shutdown_round_trip():
    import _open_stbc_host
    _open_stbc_host.init(640, 480, "test")
    _open_stbc_host.shutdown()
