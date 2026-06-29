from __future__ import annotations

from repoman.source_parse import parse_source_block, uri_to_key_filename, uri_to_source_filename


class TestParseSourceBlockDeb822:
    def test_full_deb822_block(self):
        text = "Types: deb\nURIs: https://packages.example.com/ubuntu\nSuites: noble\nComponents: main restricted\n"
        result = parse_source_block(text)
        assert result is not None
        assert result["types"] == ["deb"]
        assert result["uris"] == ["https://packages.example.com/ubuntu"]
        assert result["suites"] == ["noble"]
        assert result["components"] == ["main", "restricted"]
        assert result["enabled"] is True
        assert result["signed_by"] is None
        assert result["description"] is None

    def test_deb822_with_enabled_no(self):
        text = "Types: deb\nURIs: https://packages.example.com/ubuntu\nSuites: noble\nComponents: main\nEnabled: no\n"
        result = parse_source_block(text)
        assert result is not None
        assert result["enabled"] is False

    def test_deb822_enabled_false_string(self):
        text = (
            "Types: deb\nURIs: https://packages.example.com/ubuntu\nSuites: noble\nComponents: main\nEnabled: false\n"
        )
        result = parse_source_block(text)
        assert result["enabled"] is False

    def test_deb822_with_signed_by(self):
        text = (
            "Types: deb\n"
            "URIs: https://packages.example.com/ubuntu\n"
            "Suites: noble\n"
            "Components: main\n"
            "Signed-By: /usr/share/keyrings/example.gpg\n"
        )
        result = parse_source_block(text)
        assert result["signed_by"] == "/usr/share/keyrings/example.gpg"

    def test_deb822_x_repolib_name_as_description(self):
        text = "Types: deb\nURIs: https://packages.example.com/ubuntu\nSuites: noble\nX-Repolib-Name: My Repository\n"
        result = parse_source_block(text)
        assert result["description"] == "My Repository"

    def test_deb822_description_field(self):
        text = "Types: deb\nURIs: https://packages.example.com/ubuntu\nSuites: noble\nDescription: A repo description\n"
        result = parse_source_block(text)
        assert result["description"] == "A repo description"

    def test_deb822_x_repolib_name_takes_priority_over_description(self):
        text = (
            "Types: deb\n"
            "URIs: https://packages.example.com/ubuntu\n"
            "Suites: noble\n"
            "X-Repolib-Name: Preferred Name\n"
            "Description: Ignored Description\n"
        )
        result = parse_source_block(text)
        assert result["description"] == "Preferred Name"

    def test_deb822_singular_uri_field(self):
        text = "Types: deb\nURI: https://packages.example.com/ubuntu\nSuite: noble\nComponent: main\n"
        result = parse_source_block(text)
        assert result["uris"] == ["https://packages.example.com/ubuntu"]
        assert result["suites"] == ["noble"]
        assert result["components"] == ["main"]

    def test_deb822_multiple_types(self):
        text = "Types: deb deb-src\nURIs: https://packages.example.com/ubuntu\nSuites: noble\nComponents: main\n"
        result = parse_source_block(text)
        assert result["types"] == ["deb", "deb-src"]

    def test_deb822_missing_uri_returns_none(self):
        text = "Types: deb\nSuites: noble\nComponents: main\n"
        assert parse_source_block(text) is None


class TestParseSourceBlockOneLine:
    def test_basic_deb_line(self):
        result = parse_source_block("deb https://packages.example.com/ubuntu noble main")
        assert result is not None
        assert result["types"] == ["deb"]
        assert result["uris"] == ["https://packages.example.com/ubuntu"]
        assert result["suites"] == ["noble"]
        assert result["components"] == ["main"]
        assert result["enabled"] is True
        assert result["signed_by"] is None
        assert result["description"] is None

    def test_deb_src_line(self):
        result = parse_source_block("deb-src https://packages.example.com/ubuntu noble main")
        assert result["types"] == ["deb-src"]

    def test_deb_line_case_insensitive(self):
        result = parse_source_block("DEB https://packages.example.com/ubuntu noble main")
        assert result is not None
        assert result["types"] == ["deb"]

    def test_deb_line_with_signed_by_option(self):
        result = parse_source_block(
            "deb [signed-by=/usr/share/keyrings/example.gpg] https://packages.example.com/ubuntu noble main"
        )
        assert result["signed_by"] == "/usr/share/keyrings/example.gpg"

    def test_deb_line_with_multiple_options(self):
        result = parse_source_block(
            "deb [arch=amd64 signed-by=/usr/share/keyrings/example.gpg] https://packages.example.com/ubuntu noble main"
        )
        assert result["signed_by"] == "/usr/share/keyrings/example.gpg"

    def test_deb_line_no_components(self):
        result = parse_source_block("deb https://packages.example.com/ubuntu noble")
        assert result is not None
        assert result["components"] == []

    def test_deb_line_multiple_components(self):
        result = parse_source_block("deb https://packages.example.com/ubuntu noble main restricted universe")
        assert result["components"] == ["main", "restricted", "universe"]


class TestParseSourceBlockEdgeCases:
    def test_empty_string_returns_none(self):
        assert parse_source_block("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_source_block("   \n  ") is None

    def test_gibberish_returns_none(self):
        assert parse_source_block("not a source line at all!!!") is None

    def test_pure_comment_returns_none(self):
        assert parse_source_block("# this is a comment") is None


class TestUriToSourceFilename:
    def test_basic_hostname(self):
        assert uri_to_source_filename("https://packages.example.com/ubuntu") == "packages-example-com.sources"

    def test_strips_path(self):
        # Only the hostname matters — path is ignored
        assert uri_to_source_filename("https://packages.example.com/some/deep/path") == "packages-example-com.sources"

    def test_lowercase_conversion(self):
        assert uri_to_source_filename("https://PACKAGES.EXAMPLE.COM/ubuntu") == "packages-example-com.sources"

    def test_consecutive_non_alnum_collapsed(self):
        result = uri_to_source_filename("https://my--double.example.com/ubuntu")
        assert "--" not in result
        assert result.endswith(".sources")

    def test_plain_uri_without_scheme(self):
        result = uri_to_source_filename("packages.example.com")
        assert result.endswith(".sources")
        assert result != ".sources"


class TestUriToKeyFilename:
    def test_basic_hostname(self):
        assert uri_to_key_filename("https://packages.example.com/ubuntu") == "packages-example-com.gpg"

    def test_ppa_hostname(self):
        assert (
            uri_to_key_filename("https://ppa.launchpadcontent.net/owner/ppa/ubuntu") == "ppa-launchpadcontent-net.gpg"
        )

    def test_lowercase_conversion(self):
        assert uri_to_key_filename("https://PACKAGES.EXAMPLE.COM/ubuntu") == "packages-example-com.gpg"
