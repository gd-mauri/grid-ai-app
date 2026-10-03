# GridU GenAI Practice

A Streamlit application that produces synthetic relational data from a SQL schema using Google Gemini on Vertex AI, stores it in PostgreSQL, and lets you explore it with plain SQL.

## Working App Screenshots

<img width="1011" height="896" alt="Captura de pantalla 2026-10-03 a la(s) 2 56 25 p  m" src="https://github.com/user-attachments/assets/055799e7-6efa-44ac-a3b4-b20da372dc04" />

<img width="1147" height="761" alt="Captura de pantalla 2026-10-03 a la(s) 2 57 04 p  m" src="https://github.com/user-attachments/assets/a3c02a6f-9c3e-4590-b043-00d6175a2662" />




## Features

- **Data Generation** – Upload a DDL schema, optionally add custom instructions, and generate realistic rows for every table while keeping foreign keys consistent.
- **Preview and export** – Inspect each generated table in the browser, download everything as a ZIP of CSV files, or load the tables straight into PostgreSQL.
- **Talk to your data** – Browse the tables available in the database and run SQL queries against them.
- **Offline fallback** – If Vertex AI can't be reached, the app can build mock rows from your DDL so the rest of the workflow keeps working.

## Interface

The app uses a light theme, configured in `.streamlit/config.toml`. Page content is shown at the top, and a control panel sits at the bottom of the page:

- **Navigation** – Switch between the *Data Generation* and *Talk to your data* tabs.
- **Generation Settings** (Data Generation tab only):
  - GCP location
  - Gemini model
  - Temperature
  - Rows per table (5–1000)

If the chosen model or location isn't available, the app automatically tries the other configured locations and models, then a set of fallback Vertex AI models.

## Project structure

| File | Purpose |
| --- | --- |
| `main.py` | Streamlit application entry point |
| `Dockerfile` | Image definition for the app container |
| `docker-compose.yml` | Runs the app together with a PostgreSQL database |
| `requirements.txt` | Python dependencies |
| `.streamlit/config.toml` | Streamlit theme settings |
| `.env` | Environment variables for GCP, PostgreSQL and the fallback mode |

## Prerequisites

- Docker and Docker Compose
- A GCP project with Vertex AI access
- Application Default Credentials on your machine (`gcloud auth application-default login`). Compose mounts `~/.config/gcloud` into the container read-only.

## Configuration

Create a `.env` file next to `docker-compose.yml`:

| Variable | Description |
| --- | --- |
| `GCP_PROJECT_ID` | GCP project used for Vertex AI |
| `GCP_LOCATION` | Default Vertex AI region (e.g. `us-central1`) |
| `GEMINI_MODEL` | Default Gemini model (e.g. `gemini-2.0-flash-001`) |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `POSTGRES_DB` | Database name |
| `POSTGRES_HOST` | Database host (`db` when using Compose) |
| `POSTGRES_PORT` | Database port inside the Compose network (`5432`) |
| `LOCAL_FALLBACK` | `true` to generate mock data when model access fails |

## Running with Docker

1. Build and start the stack:

   ```bash
   docker compose up --build
   ```

2. Open the app at <http://localhost:8001>.

PostgreSQL is also published on the host at port `5433`, in case you want to connect with an external client.

To stop everything:

```bash
docker compose down
```

Add `-v` to also delete the stored database volume.

## Running locally

Without Docker, you need a reachable PostgreSQL instance and the environment variables above set in your shell (with `POSTGRES_HOST` and `POSTGRES_PORT` pointing to that instance).

```bash
pip install -r requirements.txt
streamlit run main.py
```

## Using the app

1. On the **Data Generation** tab, set the location, model, temperature and row count in the bottom panel.
2. Upload a DDL file (`.sql`, `.ddl` or `.txt`).
3. Optionally add extra instructions, such as "use dates from 2023-2024 and keep order totals between 10 and 500".
4. Click **Generate Data** and review the tables in the preview.
5. Download the ZIP of CSV files, or click **Save Tables to PostgreSQL**.
6. Switch to **Talk to your data** in the bottom panel to see the available tables and run SQL queries.

## Local fallback mode

With `LOCAL_FALLBACK=true`, a failure to reach any Vertex AI model makes the app generate simple placeholder data from your DDL instead of showing an error. This lets you try the full flow without cloud access.

Once you have access to a live Gemini model, set `LOCAL_FALLBACK=false` and restart the app.
