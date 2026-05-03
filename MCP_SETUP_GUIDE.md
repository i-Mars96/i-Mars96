# MCP Setup Guide — i-Mars96 Toolkit

A complete reference for setting up the i-Mars96 CLI tools on a new laptop and wiring them into Claude Desktop as an MCP server.

---

## Part 1 — Laptop Prerequisites & Repo Setup

Steps to run once when starting fresh on a new machine. All commands run in your **terminal** (macOS Terminal / Windows PowerShell / Linux bash) unless noted otherwise.

**API keys required: None.** All tools in this repo (requests, BeautifulSoup, Playwright, Selenium, pdfplumber, pandas, MCP SDK) are local libraries. Playwright manages its own browser binary — it does not call any Playwright cloud API and requires no key. The MCP server communicates locally with Claude Desktop over stdin/stdout.

1. **[Terminal]** Verify Python 3.11+ is installed:
   ```
   python3 --version
   ```

2. **[Terminal]** Verify pip is available:
   ```
   pip --version
   ```

3. **[Terminal]** Clone the repo:
   ```
   git clone https://github.com/i-Mars96/i-Mars96.git
   cd i-Mars96
   ```

4. **[Terminal]** Create a virtual environment (recommended):
   - macOS / Linux:
     ```
     python3 -m venv .venv
     source .venv/bin/activate
     ```
   - Windows PowerShell:
     ```
     python -m venv .venv
     .venv\Scripts\activate
     ```

5. **[Terminal]** Install all dependencies:
   ```
   pip install -r requirements.txt
   ```

6. **[Terminal]** Install Playwright's Chromium browser:
   ```
   playwright install chromium
   ```
   This downloads a local Chromium binary. No API key needed, no Chrome installation required.

7. **[Terminal]** Selenium only (optional) — verify Chrome and ChromeDriver are on PATH. Skip if not using `attr_scraper_selenium.py`.

8. **[Terminal]** Smoke-test one script:
   ```
   python web_scraper.py --url "https://example.com" --tag p --output test.csv
   ```

---

## Part 2 — MCP Server Implementation Steps

All editing in your **code editor** (VS Code or any IDE). All install/run commands in **Terminal/PowerShell**.

### 2.1 Install the MCP SDK

**[Terminal]**
```
pip install mcp==1.27.0
```

### 2.2 Update requirements.txt

**[Editor]** Add `mcp==1.27.0` to `requirements.txt` in alphabetical order:

```
beautifulsoup4
mcp==1.27.0
openpyxl
pandas
pdfplumber
playwright
python-docx
requests
selenium
```

### 2.3 Create mcp_server.py

**[Editor]** Create `mcp_server.py` in the repo root with this top-level structure:

```python
"""MCP server exposing the i-Mars96 toolkit as Claude Desktop tools."""
import json
import pathlib

from mcp.server.fastmcp import FastMCP

# domain imports (one block per source module)
from web_scraper import ...
from attr_scraper import ...
# etc.

mcp = FastMCP("i-mars96-toolkit")

# 7 @mcp.tool() functions (see Section 2.4)

if __name__ == "__main__":
    mcp.run()
```

### 2.4 Implement the 7 Tool Functions

Each tool returns:
```python
json.dumps({"record_count": N, "records": [...]}, ensure_ascii=False)
```

#### scrape_web
Imports from `web_scraper`. Wraps `fetch_page`, `extract_data`, and `build_records`.

#### scrape_attributes
Imports from `attr_scraper`. Alias `fetch_page` as `fetch_page_static` to avoid collision with other scrapers.

#### scrape_attributes_playwright
Imports from `attr_scraper_playwright` with `_pw` aliases. The wait timeout parameter is named **`timeout_ms`** (milliseconds, to match Playwright's native unit).

#### scrape_attributes_selenium
Imports from `attr_scraper_selenium` with `_sel` aliases. The wait timeout parameter is named **`timeout_seconds`** (seconds, to match Selenium's native unit).

#### merge_excel
Imports from `excel_merge`. Use `default=str` in `json.dumps` to handle pandas `CategoricalDtype` in `_merge_N` indicator columns. Returns an extra key `comparison_summary` with per-column match counts.

#### extract_pdf
Do **not** import `load_pdf` — it calls `sys.exit()` on error, which would kill the MCP server. Instead open the file directly:
```python
import pdfplumber
with pdfplumber.open(pdf_path) as pdf:
    ...
```

#### transform_csv
Do **not** import `load_csv` — same `sys.exit()` issue. Read directly:
```python
import pandas as pd
df = pd.read_csv(csv_path)
```
Returns extra keys `columns` (list of output column names) and `initial_row_count` (row count before transformations).

---

## Part 3 — Testing the Server

### 3.1 Verify Startup

**[Terminal]**
```
python mcp_server.py
```
The server blocks on stdin with no output. Press **Ctrl-C** to stop. Any import error will appear here.

### 3.2 MCP Inspector (interactive UI)

**[Terminal]**
```
mcp dev mcp_server.py
```

**[Browser — Chrome / Safari / Edge]** Open:
```
http://localhost:5173
```

Verify all 7 tool names appear under the **Tools** tab with correct parameter names and docstrings.

### 3.3 Run a Tool in the Inspector

In the Inspector UI, select `scrape_web`, set `url` to `https://example.com`, and click **Run**. Verify the response contains `record_count` and `records`.

### 3.4 CLI Smoke Test

**[Terminal — macOS / Linux]**
```
echo '{"url":"https://example.com","tag":"p"}' | mcp call mcp_server.py scrape_web
```

**[Terminal — Windows PowerShell]**
```
'{"url":"https://example.com","tag":"p"}' | mcp call mcp_server.py scrape_web
```

### 3.5 Error Handling Test

**[Terminal]**
```
echo '{"pdf_path":"/nonexistent.pdf"}' | mcp call mcp_server.py extract_pdf
```
Expected: a `FileNotFoundError` message in the JSON response. The server process should stay alive.

---

## Part 4 — Claude Desktop Config

### 4.1 Find Your Python Path

**[Terminal — macOS / Linux]**
```
which python3
```

**[Terminal — Windows PowerShell]**
```
where python
```

Copy the full path (e.g. `/usr/local/bin/python3` or `C:\Python311\python.exe`). If using a virtual environment, use the venv Python instead:
- macOS/Linux: `/path/to/i-Mars96/.venv/bin/python`
- Windows: `\path\to\i-Mars96\.venv\Scripts\python.exe`

### 4.2 Open the Config File

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` (paste into File Explorer address bar) |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

Open the file in **VS Code** or any text editor.

### 4.3 Add the MCP Server Entry

Merge the following into the existing `mcpServers` object (create the file with this content if it does not yet exist):

```json
{
  "mcpServers": {
    "i-mars96-toolkit": {
      "command": "/usr/local/bin/python3",
      "args": ["/full/path/to/i-Mars96/mcp_server.py"],
      "env": {}
    }
  }
}
```

Replace `command` with the Python path from Step 4.1. Replace `args[0]` with the absolute path to `mcp_server.py` on your machine.

### 4.4 Restart Claude Desktop

**[Claude Desktop app]** Fully quit:
- macOS: **Cmd+Q**
- Windows: right-click the tray icon → **Quit**

Relaunch Claude Desktop. The MCP server starts fresh on each launch. The 7 tools will appear in the Claude Desktop tool picker when you start a new conversation.

---

## Part 5 — Retrospective: What Was Difficult

Honest notes on friction points from planning this integration, with suggestions for next time.

### 1. `sys.exit()` in loader functions

`load_pdf` and `load_csv` call `sys.exit()` on bad input, which would kill the MCP server process. Caught during code review, but it would have been a silent runtime bug.

**Improvement:** Add a codebase convention in `CLAUDE.md` — functions intended for MCP use must never call `sys.exit()`. Use `raise ValueError` instead and let the MCP framework return the error to the client.

### 2. Timeout unit inconsistency

Playwright uses **milliseconds**; Selenium uses **seconds**. No convention in the codebase signals this.

**Improvement:** Standardize on milliseconds across the toolkit, or document the unit explicitly in each function's docstring.

### 3. Pandas Categorical not JSON-serializable

The `_merge_N` indicator columns from `excel_merge` are `CategoricalDtype` and break `json.dumps`. Required the `default=str` workaround in the MCP tool.

**Improvement:** Convert indicator columns to plain strings inside `merge_dataframes` before returning, so callers don't need to know about the Categorical type.

### 4. Duplicate function names across modules

`parse_field_definitions`, `scrape_records`, and `write_csv` exist identically in three scraper files. Importing all three in one file requires aliases.

**Improvement:** Extract shared scraper logic into a `scraper_utils.py` module and import from there.

### 5. No existing test suite

Validation required manual reasoning about each function's behavior. No automated safety net.

**Improvement:** Add a `tests/` directory with at least smoke tests for each tool's core functions.
