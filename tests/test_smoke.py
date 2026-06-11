"""
Smoke tests for the i-Mars96 toolkit.

Run with:  pytest tests/ -v

No network access required — all HTTP fetchers are monkeypatched with
canned HTML/JSON. PDF content extraction is exercised only at the
page-number-parsing level (no PDF fixture needed).
"""

import json

import pandas as pd
import pytest
from bs4 import BeautifulSoup

import attr_scraper
import csv_transformer
import excel_merge
import generate_docx
import mcp_server
import pdf_extractor
import weather_alert_agent as agent
import web_scraper


SAMPLE_HTML = """
<html><body>
<ul><li>alpha</li><li>beta</li><li>gamma</li></ul>
<table>
  <tr><td>r1c1</td><td>r1c2</td></tr>
  <tr><td>r2c1</td><td>r2c2</td></tr>
</table>
<div class="product">
  <span data-field="title">Widget</span>
  <span data-field="sku">W-1</span>
</div>
<div class="product">
  <span data-field="title">Gadget</span>
  <span data-field="sku">G-2</span>
</div>
<p class="note">first note</p>
<p class="note">second note</p>
</body></html>
"""


@pytest.fixture
def soup():
    return BeautifulSoup(SAMPLE_HTML, "html.parser")


# ---------------------------------------------------------------------------
# web_scraper
# ---------------------------------------------------------------------------

class TestWebScraper:
    def test_scrape_list_items(self, soup):
        assert web_scraper.scrape_list_items(soup) == ["alpha", "beta", "gamma"]

    def test_scrape_table_column(self, soup):
        assert web_scraper.scrape_table_column(soup, 1) == ["r1c2", "r2c2"]

    def test_scrape_table_column_out_of_range(self, soup):
        assert web_scraper.scrape_table_column(soup, 5) == []

    def test_scrape_by_class(self, soup):
        assert web_scraper.scrape_by_class(soup, "p", "note") == ["first note", "second note"]


# ---------------------------------------------------------------------------
# attr_scraper (shared logic for the whole scraper family)
# ---------------------------------------------------------------------------

class TestAttrScraper:
    def test_parse_field_definitions(self):
        fields = attr_scraper.parse_field_definitions(["title:data-field:title"])
        assert fields == [("title", "data-field", "title")]

    def test_attr_value_may_contain_colons(self):
        # split limit of 3 keeps colons inside the attribute value intact
        fields = attr_scraper.parse_field_definitions(["brand:databind:text: name"])
        assert fields == [("brand", "databind", "text: name")]

    def test_malformed_definition_skipped(self, capsys):
        fields = attr_scraper.parse_field_definitions(["nocolons", "ok:attr:val"])
        assert fields == [("ok", "attr", "val")]
        assert "malformed" in capsys.readouterr().out

    def test_scrape_records(self, soup):
        fields = [("title", "data-field", "title"), ("sku", "data-field", "sku")]
        records = attr_scraper.scrape_records(soup, "div", "product", "span", fields)
        assert records == [
            {"title": "Widget", "sku": "W-1"},
            {"title": "Gadget", "sku": "G-2"},
        ]

    def test_scrape_records_no_matches(self, soup):
        fields = [("x", "data-field", "missing")]
        assert attr_scraper.scrape_records(soup, "div", "product", "span", fields) == []


# ---------------------------------------------------------------------------
# excel_merge
# ---------------------------------------------------------------------------

@pytest.fixture
def two_workbooks(tmp_path):
    f1, f2 = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    pd.DataFrame({"id": [1, 2, 3], "val": ["x", "y", "z"]}).to_excel(f1, index=False)
    pd.DataFrame({"id": [2, 3, 4], "val": ["y", "z", "w"]}).to_excel(f2, index=False)
    return str(f1), str(f2)


class TestExcelMerge:
    def test_keyed_merge(self, two_workbooks):
        named = excel_merge.load_files(list(two_workbooks), sheet=0)
        named = excel_merge.reset_indexes(named)
        merged = excel_merge.merge_dataframes(named, "id")
        assert merged.shape[0] == 4
        assert "_merge_1" in merged.columns

    def test_comparison_summary(self, two_workbooks):
        named = excel_merge.load_files(list(two_workbooks), sheet=0)
        merged = excel_merge.merge_dataframes(excel_merge.reset_indexes(named), "id")
        summary = excel_merge.compare_dataframes(merged)
        assert summary["_merge_1"] == {"left_only": 1, "right_only": 1, "both": 2}


# ---------------------------------------------------------------------------
# pdf_extractor (page-number parsing — no PDF fixture required)
# ---------------------------------------------------------------------------

class TestPdfPageNumbers:
    def test_none_returns_all_pages(self):
        assert pdf_extractor.parse_page_numbers(None, 3) == [0, 1, 2]

    def test_singles_and_range(self):
        assert pdf_extractor.parse_page_numbers("1,3,5-7", 10) == [0, 2, 4, 5, 6]

    def test_out_of_range_filtered(self):
        assert pdf_extractor.parse_page_numbers("2-9", 4) == [1, 2, 3]

    def test_fully_out_of_range(self):
        assert pdf_extractor.parse_page_numbers("8-9", 4) == []


# ---------------------------------------------------------------------------
# csv_transformer
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_df():
    return pd.DataFrame(
        {
            "id": [1, 2, 3, 3],
            "name": ["Alice", "Bob", "Carol", "Carol"],
            "status": ["active", "inactive", "active", "active"],
        }
    )


class TestCsvTransformer:
    def test_apply_filter(self, sample_df):
        out = csv_transformer.apply_filter(sample_df, "status == 'active'")
        assert len(out) == 3

    def test_bad_filter_returns_unchanged(self, sample_df, capsys):
        out = csv_transformer.apply_filter(sample_df, "not a valid expr !!!")
        assert len(out) == len(sample_df)
        assert "failed" in capsys.readouterr().out

    def test_dedupe_subset(self, sample_df):
        out = csv_transformer.apply_deduplication(sample_df, ["id"])
        assert list(out["id"]) == [1, 2, 3]

    def test_rename_unknown_column_warns(self, sample_df, capsys):
        out = csv_transformer.apply_rename(sample_df, {"nope": "x", "name": "full_name"})
        assert "full_name" in out.columns
        assert "unknown" in capsys.readouterr().out

    def test_select_missing_column_skipped(self, sample_df, capsys):
        out = csv_transformer.apply_column_selection(sample_df, ["id", "ghost"])
        assert list(out.columns) == ["id"]

    def test_parse_rename_definitions(self):
        assert csv_transformer.parse_rename_definitions(["a:b", "bad"]) == {"a": "b"}


# ---------------------------------------------------------------------------
# mcp_server tool layer (end-to-end, fetchers monkeypatched)
# ---------------------------------------------------------------------------

class TestMcpServer:
    def test_scrape_web(self, monkeypatch):
        monkeypatch.setattr(mcp_server, "fetch_page_web", lambda url: SAMPLE_HTML.encode())
        data = json.loads(mcp_server.scrape_web("http://test", tag="td"))
        assert data["record_count"] == 4
        assert data["records"][0] == {"value": "r1c1"}

    def test_scrape_web_list_mode(self, monkeypatch):
        monkeypatch.setattr(mcp_server, "fetch_page_web", lambda url: SAMPLE_HTML.encode())
        data = json.loads(mcp_server.scrape_web("http://test", scrape_list=True))
        assert [r["value"] for r in data["records"]] == ["alpha", "beta", "gamma"]

    def test_scrape_attributes(self, monkeypatch):
        monkeypatch.setattr(mcp_server, "fetch_page_static", lambda url: SAMPLE_HTML.encode())
        data = json.loads(
            mcp_server.scrape_attributes(
                "http://test",
                fields=["title:data-field:title", "sku:data-field:sku"],
                parent_tag="div",
                parent_class="product",
            )
        )
        assert data["record_count"] == 2
        assert data["records"][1]["sku"] == "G-2"

    def test_fetch_json(self, monkeypatch):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"hello": "world"}

        monkeypatch.setattr(mcp_server.requests, "get", lambda *a, **k: FakeResponse())
        data = json.loads(mcp_server.fetch_json("http://test/api"))
        assert data["data"] == {"hello": "world"}

    def test_transform_csv_end_to_end(self, tmp_path):
        src = tmp_path / "in.csv"
        pd.DataFrame(
            {"id": [1, 2, 2], "name": ["a", "b", "b"], "status": ["active", "active", "active"]}
        ).to_csv(src, index=False)
        data = json.loads(
            mcp_server.transform_csv(
                str(src), dedupe=True, rename=["name:label"], select=["id", "label"]
            )
        )
        assert data["initial_row_count"] == 3
        assert data["record_count"] == 2
        assert data["columns"] == ["id", "label"]

    def test_merge_excel_end_to_end(self, two_workbooks):
        data = json.loads(mcp_server.merge_excel(list(two_workbooks), merge_key="id"))
        assert data["record_count"] == 4
        assert data["comparison_summary"]["_merge_1"]["both"] == 2
        # Categorical indicator column must serialize as plain strings
        assert data["records"][0]["_merge_1"] in ("left_only", "right_only", "both")

    def test_extract_pdf_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            mcp_server.extract_pdf("/nonexistent/file.pdf")

    def test_extract_pdf_bad_mode_raises(self):
        with pytest.raises(ValueError, match="'text' or 'table'"):
            mcp_server.extract_pdf("/nonexistent/file.pdf", mode="xml")

    def test_list_directory(self, tmp_path):
        (tmp_path / "a.csv").write_text("id\n1")
        (tmp_path / "b.xlsx").write_text("")
        data = json.loads(mcp_server.list_directory(str(tmp_path), pattern="*.csv"))
        assert data["file_count"] == 1
        assert data["files"][0]["name"] == "a.csv"
        assert "size_bytes" in data["files"][0]
        assert "modified" in data["files"][0]

    def test_list_directory_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            mcp_server.list_directory("/no/such/dir")

    def test_list_directory_file_not_dir_raises(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hello")
        with pytest.raises(NotADirectoryError):
            mcp_server.list_directory(str(f))

    def test_describe_dataset_csv(self, tmp_path):
        src = tmp_path / "data.csv"
        pd.DataFrame({"x": [1, 2, None], "label": ["a", "b", "c"]}).to_csv(src, index=False)
        data = json.loads(mcp_server.describe_dataset(str(src)))
        assert data["shape"] == {"rows": 3, "columns": 2}
        assert "x" in data["columns"]
        assert data["null_counts"]["x"] == 1
        assert len(data["sample"]) == 3

    def test_describe_dataset_bad_extension_raises(self, tmp_path):
        f = tmp_path / "file.json"
        f.write_text("{}")
        with pytest.raises(ValueError, match="Unsupported file type"):
            mcp_server.describe_dataset(str(f))

    def test_describe_dataset_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            mcp_server.describe_dataset("/no/such/file.csv")


# ---------------------------------------------------------------------------
# weather_alert_agent
# ---------------------------------------------------------------------------

class TestWeatherAgent:
    def test_average_three_sources(self):
        readings = [
            {"temp_f": 98.0, "apparent_temp_f": 105.0, "conditions": "Sunny", "source": "nws"},
            {"temp_f": 97.0, "apparent_temp_f": 104.0, "conditions": "", "source": "open_meteo"},
            {"temp_f": 99.0, "apparent_temp_f": 106.0, "conditions": "clear", "source": "owm"},
        ]
        out = agent.average_conditions(readings)
        assert out["temp_f"] == 98.0
        assert out["apparent_temp_f"] == 105.0
        assert out["sources"] == ["nws", "open_meteo", "owm"]

    def test_average_skips_failed_sources(self):
        readings = [
            {"temp_f": 90.0, "apparent_temp_f": 92.0, "conditions": "", "source": "nws"},
            None,
            None,
        ]
        out = agent.average_conditions(readings)
        assert out["sources"] == ["nws"]

    def test_all_sources_failed_raises(self):
        with pytest.raises(RuntimeError, match="All weather sources failed"):
            agent.average_conditions([None, None, None])

    @pytest.mark.parametrize(
        "hi,expected",
        [
            (90.9, "low"),
            (91.0, "moderate"),
            (102.9, "moderate"),
            (103.0, "high"),
            (114.9, "high"),
            (115.0, "very_high"),
            (129.9, "very_high"),
            (130.0, "extreme"),
        ],
    )
    def test_osha_thresholds(self, hi, expected):
        risk = agent.classify_risk(
            {"temp_f": hi, "apparent_temp_f": hi, "conditions": "", "sources": []}
        )
        assert risk["level"] == expected

    def test_fetch_nws_normalizes(self, monkeypatch):
        def fake_fetch_json(url, headers=None):
            if "points" in url:
                return json.dumps(
                    {"data": {"properties": {"forecastHourly": "http://fake/hourly"}}}
                )
            return json.dumps(
                {
                    "data": {
                        "properties": {
                            "periods": [{"temperature": 95, "shortForecast": "Hot"}]
                        }
                    }
                }
            )

        monkeypatch.setattr(mcp_server, "fetch_json", fake_fetch_json)
        reading = agent.fetch_nws(30.0, -97.0)
        assert reading == {
            "temp_f": 95.0,
            "apparent_temp_f": 95.0,
            "conditions": "Hot",
            "source": "nws",
        }

    def test_fetch_nws_failure_returns_none(self, monkeypatch, capsys):
        def boom(url, headers=None):
            raise ConnectionError("no network")

        monkeypatch.setattr(mcp_server, "fetch_json", boom)
        assert agent.fetch_nws(30.0, -97.0) is None
        assert "unavailable" in capsys.readouterr().out

    def test_generate_alert_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        risk = {
            "level": "high",
            "color": "orange",
            "temp_f": 100,
            "apparent_temp_f": 105,
            "conditions": "",
            "sources": ["nws"],
        }
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            agent.generate_alert(risk, 30.0, -97.0)

    def test_send_alert_stdout(self, capsys):
        agent.send_alert("stay hydrated", {"level": "high"}, 30.0, -97.0, "stdout")
        out = capsys.readouterr().out
        assert "[HEAT ALERT] HIGH" in out
        assert "stay hydrated" in out

    def test_send_alert_unknown_channel(self):
        with pytest.raises(ValueError, match="Unknown channel"):
            agent.send_alert("msg", {"level": "low"}, 0.0, 0.0, "carrier_pigeon")

    def test_validate_delivery_email_missing_vars(self, monkeypatch):
        for v in ("SMTP_USER", "SMTP_PASS", "ALERT_TO"):
            monkeypatch.delenv(v, raising=False)
        with pytest.raises(RuntimeError, match="Missing env vars"):
            agent.validate_delivery_config("email")

    def test_validate_delivery_slack_missing_webhook(self, monkeypatch):
        monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
        with pytest.raises(RuntimeError, match="SLACK_WEBHOOK_URL"):
            agent.validate_delivery_config("slack")

    def test_validate_delivery_stdout_always_passes(self):
        agent.validate_delivery_config("stdout")  # must not raise

    def test_owm_failure_hides_key(self, monkeypatch, capsys):
        def boom(url, headers=None):
            raise ConnectionError("connection refused")
        monkeypatch.setattr(mcp_server, "fetch_json", boom)
        result = agent.fetch_openweathermap(30.0, -97.0, "SECRET_KEY_XYZ")
        assert result is None
        out = capsys.readouterr().out
        assert "SECRET_KEY_XYZ" not in out
        assert "unavailable" in out


# ---------------------------------------------------------------------------
# generate_docx
# ---------------------------------------------------------------------------

class TestGenerateDocx:
    SAMPLE_MD = (
        "# Title\n"
        "\n"
        "## Section\n"
        "\n"
        "- item one\n"
        "\n"
        "```\n"
        "code line\n"
        "```\n"
    )

    def test_headings_and_lists(self):
        doc = generate_docx.build_docx(self.SAMPLE_MD)
        styles = [(p.style.name, p.text) for p in doc.paragraphs]
        assert ("Heading 1", "Title") in styles
        assert ("Heading 2", "Section") in styles
        assert ("List Bullet", "item one") in styles

    def test_code_block_monospace(self):
        doc = generate_docx.build_docx(self.SAMPLE_MD)
        code_paras = [p for p in doc.paragraphs if p.text == "code line"]
        assert len(code_paras) == 1
        assert code_paras[0].runs[0].font.name == "Courier New"
