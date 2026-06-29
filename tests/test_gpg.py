from __future__ import annotations

import requests

from repoman import gpg


class TestIsPpaUri:
    def test_launchpadcontent_is_ppa(self):
        assert gpg.is_ppa_uri("https://ppa.launchpadcontent.net/owner/ppa/ubuntu") is True

    def test_launchpad_net_is_ppa(self):
        assert gpg.is_ppa_uri("https://ppa.launchpad.net/owner/ppa/ubuntu") is True

    def test_other_host_is_not_ppa(self):
        assert gpg.is_ppa_uri("https://packages.example.com/ubuntu") is False

    def test_empty_string_is_not_ppa(self):
        assert gpg.is_ppa_uri("") is False


class TestKeyToB64:
    def test_encodes_bytes(self):
        import base64

        result = gpg.key_to_b64(b"hello")
        assert result == base64.b64encode(b"hello").decode("ascii")

    def test_returns_ascii_string(self):
        result = gpg.key_to_b64(b"\x00\x01\xff")
        assert isinstance(result, str)
        result.encode("ascii")  # should not raise


class TestFetchKey:
    def test_success_returns_bytes(self, mocker):
        mock_resp = mocker.MagicMock()
        mock_resp.content = b"-----BEGIN PGP PUBLIC KEY BLOCK-----"
        mock_resp.raise_for_status = mocker.MagicMock()
        mocker.patch("repoman.gpg.requests.get", return_value=mock_resp)

        data, err = gpg.fetch_key("https://example.com/key.gpg")
        assert data == b"-----BEGIN PGP PUBLIC KEY BLOCK-----"
        assert err is None

    def test_raises_for_status_on_error(self, mocker):
        mock_resp = mocker.MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("404")
        mocker.patch("repoman.gpg.requests.get", return_value=mock_resp)

        data, err = gpg.fetch_key("https://example.com/key.gpg")
        assert data is None
        assert err is not None

    def test_connection_error(self, mocker):
        mocker.patch(
            "repoman.gpg.requests.get",
            side_effect=requests.ConnectionError("refused"),
        )
        data, err = gpg.fetch_key("https://example.com/key.gpg")
        assert data is None
        assert "refused" in err

    def test_timeout_error(self, mocker):
        mocker.patch(
            "repoman.gpg.requests.get",
            side_effect=requests.Timeout("timed out"),
        )
        data, err = gpg.fetch_key("https://example.com/key.gpg")
        assert data is None
        assert err is not None


class TestFetchPpaKey:
    def _mock_lp(self, mocker, fingerprint="AABBCCDD"):
        mock_lp_module = mocker.MagicMock()
        mock_lp = mocker.MagicMock()
        mock_lp_module.Launchpad.login_anonymously.return_value = mock_lp
        mock_archive = mocker.MagicMock()
        mock_archive.signing_key_fingerprint = fingerprint
        mock_lp.people.__getitem__.return_value.getPPAByName.return_value = mock_archive
        mocker.patch.dict(
            "sys.modules",
            {"launchpadlib": mock_lp_module, "launchpadlib.launchpad": mock_lp_module},
        )
        return mock_lp

    def test_fetches_key_on_success(self, mocker):
        self._mock_lp(mocker, fingerprint="DEADBEEF")
        mocker.patch(
            "repoman.gpg.fetch_key",
            return_value=(b"key-bytes", None),
        )
        data, err = gpg.fetch_ppa_key("testowner", "testppa")
        assert data == b"key-bytes"
        assert err is None

    def test_returns_error_when_no_fingerprint(self, mocker):
        self._mock_lp(mocker, fingerprint=None)
        data, err = gpg.fetch_ppa_key("testowner", "testppa")
        assert data is None
        assert err is not None

    def test_returns_error_on_exception(self, mocker):
        mock_lp_module = mocker.MagicMock()
        mock_lp_module.Launchpad.login_anonymously.side_effect = Exception("network error")
        mocker.patch.dict(
            "sys.modules",
            {"launchpadlib": mock_lp_module, "launchpadlib.launchpad": mock_lp_module},
        )
        data, err = gpg.fetch_ppa_key("testowner", "testppa")
        assert data is None
        assert err is not None


class TestVerifyKey:
    def test_valid_key_returns_true(self, mocker):
        mock_run = mocker.patch("repoman.gpg.subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = b""
        ok, err = gpg.verify_key(b"-----BEGIN PGP PUBLIC KEY BLOCK-----")
        assert ok is True
        assert err == ""

    def test_invalid_key_returns_false_with_stderr(self, mocker):
        mock_run = mocker.patch("repoman.gpg.subprocess.run")
        mock_run.return_value.returncode = 2
        mock_run.return_value.stderr = b"gpg: no valid OpenPGP data found"
        ok, err = gpg.verify_key(b"garbage")
        assert ok is False
        assert "no valid OpenPGP data found" in err

    def test_accepts_string_input(self, mocker):
        mock_run = mocker.patch("repoman.gpg.subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = b""
        ok, _ = gpg.verify_key("-----BEGIN PGP PUBLIC KEY BLOCK-----")
        assert ok is True
        call_input = mock_run.call_args[1]["input"]
        assert isinstance(call_input, bytes)

    def test_oserror_returns_false(self, mocker):
        mocker.patch("repoman.gpg.subprocess.run", side_effect=OSError("gpg not found"))
        ok, err = gpg.verify_key(b"data")
        assert ok is False
        assert "gpg not found" in err


class TestReadKeyText:
    def test_ascii_armored_file_returned(self, tmp_path):
        key_file = tmp_path / "test.asc"
        content = "-----BEGIN PGP PUBLIC KEY BLOCK-----\ndata\n-----END PGP PUBLIC KEY BLOCK-----\n"
        key_file.write_text(content, encoding="ascii")
        result = gpg.read_key_text(key_file)
        assert result == content

    def test_binary_file_returns_none(self, tmp_path):
        key_file = tmp_path / "test.gpg"
        key_file.write_bytes(b"\x99\x01\xd2\x04")
        result = gpg.read_key_text(key_file)
        assert result is None

    def test_missing_file_returns_none(self, tmp_path):
        result = gpg.read_key_text(tmp_path / "nonexistent.gpg")
        assert result is None

    def test_ascii_without_pgp_header_returns_none(self, tmp_path):
        key_file = tmp_path / "test.txt"
        key_file.write_text("just some text", encoding="ascii")
        result = gpg.read_key_text(key_file)
        assert result is None


class TestReadKeyContent:
    def test_ascii_armored_file_returned_directly(self, tmp_path):
        key_file = tmp_path / "test.asc"
        content = "-----BEGIN PGP PUBLIC KEY BLOCK-----\ndata\n-----END PGP PUBLIC KEY BLOCK-----\n"
        key_file.write_bytes(content.encode("ascii"))
        result = gpg.read_key_content(key_file)
        assert result == content

    def test_missing_file_returns_none(self, tmp_path):
        result = gpg.read_key_content(tmp_path / "nonexistent.gpg")
        assert result is None

    def test_empty_file_returns_none(self, tmp_path):
        key_file = tmp_path / "empty.gpg"
        key_file.write_bytes(b"")
        result = gpg.read_key_content(key_file)
        assert result is None

    def test_binary_file_converted_via_gpg_enarmor(self, tmp_path, mocker):
        key_file = tmp_path / "test.gpg"
        key_file.write_bytes(b"\x99\x01\xd2binary-key-data")
        armored = b"-----BEGIN PGP ARMORED FILE-----\ndata\n-----END PGP ARMORED FILE-----\n"
        mock_run = mocker.patch("repoman.gpg.subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = armored
        result = gpg.read_key_content(key_file)
        assert result == armored.decode("ascii")
        args = mock_run.call_args[0][0]
        assert "--enarmor" in args

    def test_binary_file_gpg_fails_returns_none(self, tmp_path, mocker):
        key_file = tmp_path / "test.gpg"
        key_file.write_bytes(b"\x99\x01bad")
        mock_run = mocker.patch("repoman.gpg.subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = b""
        result = gpg.read_key_content(key_file)
        assert result is None

    def test_binary_file_gpg_oserror_returns_none(self, tmp_path, mocker):
        key_file = tmp_path / "test.gpg"
        key_file.write_bytes(b"\x99\x01bad")
        mocker.patch("repoman.gpg.subprocess.run", side_effect=OSError("gpg not found"))
        result = gpg.read_key_content(key_file)
        assert result is None
