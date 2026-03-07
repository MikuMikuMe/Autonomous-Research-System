# Setup Guide

## Run the Unified Agentic System

With venv activated:
```bash
python orchestrator.py
```

Runs Detection → Mitigation → Auditing automatically. The **Judge Agent** evaluates each output; failed agents are retried (up to 3 times) with different seeds. See [.cursor/skills/qmind-agentic-system/SKILL.md](.cursor/skills/qmind-agentic-system/SKILL.md) for details.

### GUI Dashboard

For a web-based dashboard with live logs, metrics, figures, and paper viewer:

```bash
python run_gui.py
```

Open http://127.0.0.1:8000 in your browser. When the pipeline finishes successfully, the research paper (PDF or Markdown) opens automatically.

---

## Virtual Environment

Create and activate the venv:

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
.venv\Scripts\activate.bat
```

Then install dependencies:
```bash
pip install -r requirements.txt
```

## Kaggle Credentials (if needed)

The Credit Card Fraud dataset (`mlg-ulb/creditcardfraud`) is public and often works without credentials. If you get authentication errors:

1. Go to [Kaggle Account Settings → API](https://www.kaggle.com/settings/account) and click **Create New Token** to download `kaggle.json`.

2. Copy the template and add your credentials:
   ```powershell
   mkdir $env:USERPROFILE\.kaggle -ErrorAction SilentlyContinue
   Copy-Item kaggle.json.example $env:USERPROFILE\.kaggle\kaggle.json
   ```
   Then edit `C:\Users\<YourUsername>\.kaggle\kaggle.json` and replace:
   - `YOUR_KAGGLE_USERNAME` with your Kaggle username
   - `YOUR_KAGGLE_API_KEY` with the key from the downloaded file

3. Or manually place your downloaded `kaggle.json` at:
   ```
   C:\Users\<YourUsername>\.kaggle\kaggle.json
   ```

The file format:
```json
{
  "username": "your_kaggle_username",
  "key": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

**Security:** Never commit `kaggle.json` to git. It is listed in `.gitignore`.

---

## LaTeX (Optional — for PDF Paper)

The Auditing Agent generates a LaTeX paper in **IEEE/CUCAI 2026 format** (`outputs/paper/paper.tex`) and attempts to compile it to PDF. The paper uses the IEEEtran document class (two-column, IEEE-style numbered citations). If `pdflatex` is not installed, the LaTeX source is still produced; you can compile it manually.

**Note:** The LaTeX step can take 1–2 minutes (Gemini API for Markdown→LaTeX conversion, then pdflatex). Progress is logged; if it appears stuck for >5 min, see README Troubleshooting.

**Windows (MiKTeX):** Download from https://miktex.org/ and add to PATH.

**Windows (TeX Live):** Download from https://tug.org/texlive/.

**Manual compile:**
```powershell
cd outputs\paper
pdflatex paper.tex
bibtex paper
pdflatex paper.tex
pdflatex paper.tex
```

---

## Gemini API (Optional — for Judge & Auditing Agents)

The **Judge Agent** and **Auditing Agent** use Gemini for semantic evaluation and Hour 6 review when an API key is set:

- **Judge:** Evaluates quality, consistency, and whether claims are supported by the data (beyond rule-based checks).
- **Auditing Hour 6:** Reviews paper structure, verifies formulas, and uses Google Search grounding to find recent papers supporting claims.

**Setup:**
1. Get an API key from [Google AI Studio](https://aistudio.google.com/apikey).
2. Set the environment variable:
   ```powershell
   $env:GOOGLE_API_KEY = "your-api-key"
   ```
   Or create a `.env` file (do not commit it).

3. Optional: Override the model (default: `gemini-3.1-pro-preview`). See [available models](https://ai.google.dev/gemini-api/docs/models):
   ```powershell
   $env:GEMINI_MODEL = "gemini-2.5-flash"
   ```
   If you get `404 NOT_FOUND`, try `gemini-2.5-flash` or `gemini-2.5-pro`.

Without the API key, agents fall back to rule-based evaluation only.

---

## alphaXiv (Optional — for Research Pipeline)

The **research pipeline** (`research_orchestrator.py`) uses alphaXiv to find papers supporting claims and fill gaps. Requires the same token you use in Cursor's MCP config.

**Setup:**
1. Get a token from [alphaxiv.org](https://alphaxiv.org/signin).
2. Add to `.env`:
   ```
   ALPHAXIV_TOKEN=your_token_here
   ```
3. Run the full pipeline (research phase runs automatically after the paper):
   ```bash
   python orchestrator.py
   ```

See [docs/ALPHAXIV_SETUP.md](docs/ALPHAXIV_SETUP.md) for details.

---

## Troubleshooting

### Permission denied when creating or removing venv

If you see `[Errno 13] Permission denied` on `.venv\Scripts\python.exe` or when running `Remove-Item -Recurse -Force .venv`, the venv is locked by another process (e.g. the GUI server, Cursor's Python extension, or a background Python process).

**Fix 1 — Use the alternate venv:** A fresh venv was created at `.venv_new`. Use it:

```powershell
.\.venv_new\Scripts\Activate.ps1
python orchestrator.py
```

Or run directly without activating:
```powershell
.\.venv_new\Scripts\python.exe orchestrator.py
```

**Fix 2 — Free the lock, then recreate:**
1. Close all terminals and stop the GUI server (`run_gui.py`) if it's running.
2. Restart Cursor (or close any process using the venv).
3. Delete the old venv: `Remove-Item -Recurse -Force .venv`
4. Create a new one: `python -m venv .venv`
5. Activate and install: `.\.venv\Scripts\Activate.ps1` then `pip install -r requirements.txt`
