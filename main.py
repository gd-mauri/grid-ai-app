import io
import json
import os
import zipfile
import pandas as pd
import sqlalchemy
import streamlit as st
from google import genai
from google.genai import types

# ---------------------------------------------------------
# 1. STRICT FIRST STREAMLIT COMMAND
# ---------------------------------------------------------
st.set_page_config(page_title="Synthetic Data & Chatbot", layout="wide")

# ---------------------------------------------------------
# 2. Environment variables
# ---------------------------------------------------------
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "gd-gcp-gridu-genai")
DEFAULT_GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "synthdata_db")
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
LOCAL_FALLBACK = os.getenv("LOCAL_FALLBACK", "false").lower() in ("1", "true", "yes")

LOCATION_CANDIDATES = list(dict.fromkeys([
    DEFAULT_GCP_LOCATION,
    "us-east4",
    "europe-west1",
]))

MODEL_CANDIDATES = list(dict.fromkeys([
    DEFAULT_GEMINI_MODEL,
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-1.5-flash",
]))

FALLBACK_MODEL_CANDIDATES = [
    "text-bison@001",
    "text-bison",
    "code-bison@001",
]

# Initialize the new Google GenAI SDK (Vertex AI)
@st.cache_resource
def get_genai_client(location):
    # Initialize the Google GenAI SDK client for Vertex AI
    return genai.Client(vertexai=True, project=PROJECT_ID, location=location)

# Connect to the database
def get_db_engine():
    db_url = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return sqlalchemy.create_engine(db_url)

# Local fallback data generator when Vertex AI access is unavailable
import re

def generate_mock_data_from_ddl(ddl_text, row_count):
    tables = {}
    pattern = re.compile(r"CREATE\s+TABLE\s+`?(\w+)`?\s*\((.*?)\)", re.I | re.S)
    col_pattern = re.compile(r"`?(\w+)`?\s+([A-Z]+)", re.I)

    for match in pattern.finditer(ddl_text):
        table_name = match.group(1)
        cols_block = match.group(2)
        columns = col_pattern.findall(cols_block)
        if not columns:
            continue

        rows = []
        for i in range(row_count):
            row = {}
            for name, col_type in columns:
                t = col_type.upper()
                if "INT" in t:
                    row[name] = i + 1
                elif "DATE" in t:
                    row[name] = f"2024-01-{(i % 28) + 1:02d}"
                elif "TIMESTAMP" in t or "TIME" in t:
                    row[name] = "2024-01-01T00:00:00Z"
                elif "BOOL" in t:
                    row[name] = i % 2 == 0
                elif "CHAR" in t or "TEXT" in t or "STRING" in t:
                    row[name] = f"{name}_{i+1}"
                else:
                    row[name] = f"{name}_{i+1}"
            rows.append(row)
        tables[table_name] = rows

    if not tables:
        tables["mock_table"] = [{"id": 1, "value": "mock"}]
    return tables

# ---------------------------------------------------------
# 4. Streamlit UI
# ---------------------------------------------------------
st.title("Grid University Practice 1 & 2")

content_area = st.container()
bottom_panel = st.container(border=True)

# Bottom panel: navigation + generation settings (created first so values are available to the content)
with bottom_panel:
    st.subheader("Navigation")
    page = st.radio("Select Tab", ["Data Generation", "Talk to your data"], horizontal=True)

    if page == "Data Generation":
        st.subheader("Generation Settings")
        col_loc, col_model, col_temp, col_rows = st.columns(4)
        with col_loc:
            selected_location = st.selectbox("Select GCP Location", LOCATION_CANDIDATES, index=0)
        with col_model:
            selected_model = st.selectbox("Select Gemini Model", MODEL_CANDIDATES, index=0)
        with col_temp:
            temperature = st.slider("Temperature", 0.0, 1.0, 0.2, 0.1)
        with col_rows:
            row_count = st.number_input("Rows per table", min_value=5, max_value=1000, value=10)

with content_area:
    if page == "Data Generation":
        st.header("Phase 1: Synthetic Data Generation")

        if LOCAL_FALLBACK:
            st.info("LOCAL_FALLBACK is enabled: app will generate mock data if Vertex AI model access fails.")

        # Upload DDL
        uploaded_file = st.file_uploader("Upload DDL Schema (.sql, .ddl, .txt)", type=["sql", "ddl", "txt"])
        user_prompt = st.text_area("Additional Generation Instructions", placeholder="e.g. Use dates from 2023-2024 and keep order totals between 10 and 500...")

        if uploaded_file and st.button("Generate Data"):
            ddl_text = uploaded_file.read().decode("utf-8")

            system_instruction = f"""
            You are an expert SQL Data Generator.
            Analyze the provided DDL schema and generate realistic synthetic data.
        
            CRITICAL RULES:
            1. Maintain Referential Integrity: Ensure foreign keys strictly match existing primary keys in parent tables.
            2. Generate exactly {row_count} rows for each table defined in the DDL.
            3. Output MUST be valid JSON adhering strictly to the schema provided.
            """

            prompt = f"""
            DDL Schema:
            {ddl_text}

            Additional Instructions:
            {user_prompt}

            Return data as a JSON object where keys are table names and values are lists of objects representing rows.
            Example format: {{"table_name": [{{"column1": "val1"}}]}}
            """

            with st.spinner(f"Generating data with {selected_model} in {selected_location}..."):
                try:
                    attempt_logs = []
                    response = None
                    used_location = None
                    used_model = None
                    local_fallback_used = False

                    for candidate_location in [selected_location] + [l for l in LOCATION_CANDIDATES if l != selected_location]:
                        candidate_client = get_genai_client(candidate_location)
                        for candidate_model in [selected_model] + [m for m in MODEL_CANDIDATES if m != selected_model]:
                            try:
                                response = candidate_client.models.generate_content(
                                    model=candidate_model,
                                    contents=prompt,
                                    config=types.GenerateContentConfig(
                                        system_instruction=system_instruction,
                                        temperature=temperature,
                                        response_mime_type="application/json",
                                    ),
                                )
                                used_location = candidate_location
                                used_model = candidate_model
                                break
                            except Exception as exc:
                                attempt_logs.append(f"{candidate_model}@{candidate_location}: {str(exc)}")
                                continue
                        if response is not None:
                            break

                    if response is None:
                        # Try fallback Vertex AI models if Gemini is not available in this project
                        for candidate_location in [selected_location] + [l for l in LOCATION_CANDIDATES if l != selected_location]:
                            candidate_client = get_genai_client(candidate_location)
                            for candidate_model in FALLBACK_MODEL_CANDIDATES:
                                try:
                                    response = candidate_client.models.generate_content(
                                        model=candidate_model,
                                        contents=prompt,
                                        config=types.GenerateContentConfig(
                                            system_instruction=system_instruction,
                                            temperature=temperature,
                                            response_mime_type="application/json",
                                        ),
                                    )
                                    used_location = candidate_location
                                    used_model = candidate_model
                                    break
                                except Exception as exc:
                                    attempt_logs.append(f"{candidate_model}@{candidate_location}: {str(exc)}")
                                    continue
                            if response is not None:
                                break

                    if response is None:
                        if LOCAL_FALLBACK:
                            st.warning("Model access failed, using local fallback mock data.")
                            generated_data = generate_mock_data_from_ddl(ddl_text, row_count)
                            st.session_state["generated_data"] = generated_data
                            st.session_state["ddl_text"] = ddl_text
                            local_fallback_used = True
                            st.success("Local fallback data generated.")
                        else:
                            error_detail = "\n".join(attempt_logs[:10])
                            st.error(
                                "Generation failed: no available Gemini or fallback model found in the selected locations. "
                                "Tried the following model/location combinations:\n" + error_detail
                            )
                            raise RuntimeError("Vertex AI model access failure")

                    if not local_fallback_used:
                        # Clean up and parse JSON
                        raw_text = response.text.strip()
                        if raw_text.startswith("```json"):
                            raw_text = raw_text[7:-3].strip()
                        elif raw_text.startswith("```"):
                            raw_text = raw_text[3:-3].strip()

                        st.session_state["used_model"] = used_model
                        st.session_state["used_location"] = used_location
                        generated_data = json.loads(raw_text)
                        st.session_state["generated_data"] = generated_data
                        st.session_state["ddl_text"] = ddl_text
                        st.success(f"Data successfully generated using {used_model} in {used_location}!")
                    else:
                        used_model = "local-fallback"
                        used_location = "local"
                        st.session_state["used_model"] = used_model
                        st.session_state["used_location"] = used_location


                except Exception as e:
                    if not isinstance(e, RuntimeError):
                        st.error(f"Generation failed: {str(e)}")

        # Preview and management
        if "generated_data" in st.session_state:
            st.subheader("Data Preview & Management")
            data = st.session_state["generated_data"]
            engine = get_db_engine()

            for table_name, rows in data.items():
                st.write(f"### Table: `{table_name}`")
                df = pd.DataFrame(rows)
                st.dataframe(df)

            col1, col2 = st.columns(2)

            with col1:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for table_name, rows in data.items():
                        df = pd.DataFrame(rows)
                        zip_file.writestr(f"{table_name}.csv", df.to_csv(index=False))

                st.download_button(
                    label="📦 Download CSV Archive (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="synthetic_data.zip",
                    mime="application/zip",
                )

            with col2:
                if st.button("💾 Save Tables to PostgreSQL"):
                    try:
                        with engine.connect() as conn:
                            conn.execute(sqlalchemy.text(st.session_state["ddl_text"]))
                            conn.commit()

                        for table_name, rows in data.items():
                            df = pd.DataFrame(rows)
                            df.to_sql(table_name, engine, if_exists="append", index=False)

                        st.success("Data successfully pushed to PostgreSQL!")
                    except Exception as e:
                        st.error(f"Database insertion failed: {str(e)}")

    else:
        st.header("Phases 2 & 3: Talk to your Data")
        if LOCAL_FALLBACK:
            st.info("Vertex AI may be unavailable in this environment. You can still run SQL queries against Postgres.")

        engine = get_db_engine()
        try:
            inspector = sqlalchemy.inspect(engine)
            tables = inspector.get_table_names()
        except Exception as e:
            st.error(f"Unable to inspect Postgres database: {e}")
            tables = []

        if tables:
            st.subheader("Available database tables")
            st.write(tables)
        else:
            st.warning("No tables found in Postgres yet. Generate data and save to Postgres first.")

        query = st.text_area("SQL Query", "SELECT * FROM your_table LIMIT 20")
        if st.button("Run Query"):
            if not query.strip():
                st.error("Enter a SQL query first.")
            else:
                try:
                    with engine.connect() as conn:
                        result = conn.execute(sqlalchemy.text(query))
                        df = pd.DataFrame(result.fetchall(), columns=result.keys())
                        st.dataframe(df)
                except Exception as e:
                    st.error(f"Query failed: {e}")
