# i-Mars96 Toolkit

A collection of standalone Python CLI tools for web scraping, PDF extraction, CSV transformation, and Excel data manipulation — plus an MCP server that exposes all of them to Claude Desktop, and a weather alert agent built on top.

## Tools

### Web Scrapers

| Script | Description |
|---|---|
| `web_scraper.py` | Static HTML scraper — extracts table cells, list items, or class-filtered tags via requests + BeautifulSoup |
| `attr_scraper.py` | Multi-field attribute scraper for structured records (static pages) |
| `attr_scraper_playwright.py` | Same as above for JavaScript-rendered pages — uses Playwright (preferred, no ChromeDriver needed) |
| `attr_scraper_selenium.py` | Same as above using Selenium + Chrome (requires ChromeDriver on PATH) |

### Data Tools

| Script | Description |
|---|---|
| `excel_merge.py` | Outer-merge 2+ Excel files in order with per-step comparison summary |
| `pdf_extractor.py` | Extract raw text or structured tables from PDFs using pdfplumber |
| `csv_transformer.py` | Filter → dedupe → rename → select pipeline for CSV files |

### MCP Server

`mcp_server.py` exposes **10 tools** to Claude Desktop via the Model Context Protocol:

| Tool | What it does |
|---|---|
| `scrape_web` | Static HTML scraping |
| `scrape_attributes` | Multi-field attribute scraping (static) |
| `scrape_attributes_playwright` | Multi-field scraping on JS-rendered pages (Playwright) |
| `scrape_attributes_selenium` | Multi-field scraping on JS-rendered pages (Selenium) |
| `fetch_json` | Fetch any JSON REST API endpoint |
| `merge_excel` | Outer-merge 2+ Excel files |
| `extract_pdf` | Extract text or tables from a PDF |
| `transform_csv` | Filter/dedupe/rename/select on a CSV |
| `list_directory` | List files in a directory (supports glob patterns) |
| `describe_dataset` | Column names, dtypes, null counts, and sample rows for CSV/Excel |

### Agents

`weather_alert_agent.py` — Heat safety alert agent for outdoor work crews. Fetches current conditions from **NWS, Open-Meteo, and OpenWeatherMap** (3-source average), classifies heat risk using OSHA thresholds, and uses the Claude API to generate a natural-language alert with supply and scheduling recommendations. Delivers via Gmail, Slack, or stdout.

## Quick Start

```bash
git clone https://github.com/i-Mars96/i-Mars96.git
cd i-Mars96
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Copy `.env.example` to `.env` and fill in your credentials before running the agent or MCP server.

## Usage Examples

```bash
# Static HTML scraper
python web_scraper.py --url "https://example.com" --tag td --output out.csv

# Multi-field attribute scraper (Playwright)
python attr_scraper_playwright.py --url "https://example.com" \
    --wait-for "span[databind='text: name']" \
    --fields "brand:databind:text: name" "reg:databind:text: regNumber" \
    --output out.csv

# Excel merge
python excel_merge.py --files a.xlsx b.xlsx --merge-key ID --output merged.xlsx

# PDF extractor
python pdf_extractor.py --input report.pdf --mode text --output pages.csv

# CSV transformer
python csv_transformer.py --input data.csv --filter "status == 'active'" \
    --dedupe --rename "product_name:name" --select id name price --output clean.csv

# Weather alert agent (stdout dry run)
python weather_alert_agent.py --lat 30.26 --lon -97.74 --channel stdout
```

## MCP Server (Claude Desktop)

```bash
python mcp_server.py   # starts the server — blocks on stdin
```

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "i-mars96-toolkit": {
      "command": "/path/to/python",
      "args": ["/path/to/i-Mars96/mcp_server.py"],
      "env": {}
    }
  }
}
```

See `MCP_SETUP_GUIDE.md` for the full setup walkthrough.

## Tests

```bash
python -m pytest tests/ -v
```

57 tests, zero network required — all HTTP fetchers are monkeypatched.

## Dependencies

```bash
pip install -r requirements.txt
playwright install chromium   # required for attr_scraper_playwright
```

`attr_scraper_selenium` also requires Chrome and ChromeDriver on PATH.
