import json

import pytest

from seriousdb import api
from seriousdb.cache import Cache
from seriousdb.exceptions import ResourceNotFoundError


@pytest.fixture
def python_module_api(tmp_path, monkeypatch):
    db_file = tmp_path / ".sdb"
    monkeypatch.setattr(api, "DB_FILE", str(db_file))
    monkeypatch.setattr(api, "_cache", Cache())
    return api

def test_set_stores_value(python_module_api):
    assert python_module_api.set("name", "Alice") == "Alice"

def test_get_returns_stored_value(python_module_api):
    python_module_api.set("name", "Alice")

    assert python_module_api.get("name") == "Alice"

def test_get_missing_key_raises_resource_not_found(python_module_api):
    with pytest.raises(ResourceNotFoundError):
        python_module_api.get("does_not_exist")

def test_delete_removes_key_and_returns_previous_value(python_module_api):
    python_module_api.set("name", "Alice")

    assert python_module_api.delete("name") == "Alice"
    with pytest.raises(ResourceNotFoundError):
        python_module_api.get("name")

def test_delete_missing_key_raises_resource_not_found(python_module_api):
    with pytest.raises(ResourceNotFoundError):
        python_module_api.delete("does_not_exist")

def test_set_persist_to_disk_immediatly(python_module_api, tmp_path):
    python_module_api.set("name", "Alice")

    saved = json.loads((tmp_path / ".sdb").read_text())
    assert saved["name"] == "Alice"

def test_auto_load_without_an_explicit_load_call(python_module_api, tmp_path):
    db_file = tmp_path / ".sdb"
    assert not db_file.exists()

    python_module_api.set("first", "value")

    assert db_file.exists()
