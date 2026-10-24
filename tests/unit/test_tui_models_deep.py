"""Deep tests for sago/tui/models.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from sago.tui import models


def test_models_file_load_save(tmp_path, monkeypatch) -> None:
    models_file = tmp_path / "models.json"
    monkeypatch.setattr(models, "MODELS_FILE", models_file)

    # Empty/not existing
    data = models._load_models_data()
    assert data["custom"] == []

    # Corrupt file
    models_file.write_text("invalid json")
    data_corrupt = models._load_models_data()
    assert data_corrupt["custom"] == []

    # Save and reload
    models._save_models_data(
        {"custom": ["my-model"], "fetched": [], "costs": {}, "fetched_at": 100}
    )
    data_saved = models._load_models_data()
    assert data_saved["custom"] == ["my-model"]


def test_get_all_models_and_costs(tmp_path, monkeypatch) -> None:
    models_file = tmp_path / "models.json"
    monkeypatch.setattr(models, "MODELS_FILE", models_file)

    models_file.write_text(
        json.dumps(
            {
                "custom": ["custom/model-1"],
                "fetched": ["fetched/model-2"],
                "costs": {"custom/model-1": {"input": 1.0, "output": 2.0}},
                "fetched_at": 500,
            }
        )
    )

    all_models = models.get_all_models()
    assert "custom/model-1" in all_models
    assert "fetched/model-2" in all_models
    assert "openai/gpt-4o" in all_models

    costs = models.get_model_costs()
    assert costs["custom/model-1"] == {"input": 1.0, "output": 2.0}
    assert "openrouter/free" in costs


def test_add_and_remove_custom_model(tmp_path, monkeypatch) -> None:
    models_file = tmp_path / "models.json"
    monkeypatch.setattr(models, "MODELS_FILE", models_file)

    msg1 = models.add_custom_model("openai/gpt-4o")
    assert "Already exists" in msg1

    msg2 = models.add_custom_model("my-org/custom-llm")
    assert "Added: my-org/custom-llm" in msg2

    msg_dup = models.add_custom_model("my-org/custom-llm")
    assert "Already exists" in msg_dup

    msg_rem = models.remove_custom_model("my-org/custom-llm")
    assert "Removed: my-org/custom-llm" in msg_rem

    msg_rem_nf = models.remove_custom_model("nonexistent")
    assert "Not found" in msg_rem_nf


def test_refresh_models_from_openrouter(tmp_path, monkeypatch) -> None:
    models_file = tmp_path / "models.json"
    monkeypatch.setattr(models, "MODELS_FILE", models_file)

    # Empty key
    res_no_key = models.refresh_models_from_openrouter("")
    assert "No API key" in res_no_key

    # Mock openrouter API failure
    monkeypatch.setattr(
        "urllib.request.urlopen",
        MagicMock(side_effect=Exception("Network error")),
    )
    res_err = models.refresh_models_from_openrouter("fake_key")
    assert "Fetch failed" in res_err

    # Mock success empty data
    mock_resp_empty = MagicMock()
    mock_resp_empty.__enter__.return_value.read.return_value = json.dumps({"data": []}).encode()
    monkeypatch.setattr("urllib.request.urlopen", MagicMock(return_value=mock_resp_empty))
    res_empty = models.refresh_models_from_openrouter("fake_key")
    assert "No models returned" in res_empty

    # Mock success with models
    mock_resp_models = MagicMock()
    mock_resp_models.__enter__.return_value.read.return_value = json.dumps(
        {
            "data": [
                {
                    "id": "openrouter/free-model:free",
                    "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                },
                {
                    "id": "openrouter/cheap-model",
                    "pricing": {"prompt": "0.000005", "completion": "0.000010"},
                },
                {"id": ""},  # empty id skipped
            ]
        }
    ).encode()
    monkeypatch.setattr("urllib.request.urlopen", MagicMock(return_value=mock_resp_models))

    res_success = models.refresh_models_from_openrouter("fake_key")
    assert "Fetched 2 models from OpenRouter (1 free)" in res_success

    # Auto refresh if stale check
    # Fresh cache returns None
    res_fresh = models.auto_refresh_if_stale("fake_key")
    assert res_fresh is None

    # Stale cache triggers refresh
    data = models._load_models_data()
    data["fetched_at"] = 1000
    models._save_models_data(data)
    res_stale = models.auto_refresh_if_stale("fake_key")
    assert "Fetched 2 models" in res_stale

    # Stale cache without key returns None
    res_stale_no_key = models.auto_refresh_if_stale("")
    assert res_stale_no_key is None
