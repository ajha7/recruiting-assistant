import pytest

import generate_data


@pytest.fixture(scope="session")
def db_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("tools") / "recruiting.db"
    generate_data.build(path)
    return path


@pytest.fixture(autouse=False)
def db_env(db_file, monkeypatch):
    monkeypatch.setenv("RECRUITING_DB", str(db_file))
    return db_file
