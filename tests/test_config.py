from unittest.mock import patch

from PySide6.QtCore import QSettings

from comicdesk.config import TaggerSettings


def make_settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


def test_save_and_load_roundtrip_without_keyring(tmp_path):
    with patch("deskkit.secrets.available", return_value=False):
        settings = make_settings(tmp_path)
        cfg = TaggerSettings(comicvine_key="abc123")
        cfg.save(settings)

        settings2 = make_settings(tmp_path)
        loaded = TaggerSettings.load(settings2)
    assert loaded.comicvine_key == "abc123"


def test_save_does_not_store_key_in_plaintext_when_keyring_available(tmp_path):
    with patch("deskkit.secrets.available", return_value=True), \
         patch("deskkit.secrets.keyring") as mock_keyring:
        settings = make_settings(tmp_path)
        cfg = TaggerSettings(comicvine_key="abc123")
        cfg.save(settings)

    settings.beginGroup("tagger")
    stored_plaintext = settings.value("comicvine_key")
    settings.endGroup()
    assert stored_plaintext is None
    mock_keyring.set_password.assert_any_call("comicdesk", "comicvine_key", "abc123")


def test_load_migrates_legacy_plaintext_key_into_keyring(tmp_path):
    settings = make_settings(tmp_path)
    settings.beginGroup("tagger")
    settings.setValue("comicvine_key", "legacy-key")
    settings.endGroup()

    with patch("deskkit.secrets.available", return_value=True), \
         patch("deskkit.secrets.keyring") as mock_keyring:
        mock_keyring.get_password.return_value = None
        loaded = TaggerSettings.load(settings)

    assert loaded.comicvine_key == "legacy-key"
    mock_keyring.set_password.assert_any_call("comicdesk", "comicvine_key", "legacy-key")
