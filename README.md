# Project_BI — Credit Risk Management Dashboard

## 1. Overview

Project_BI is a Python and Streamlit-based dashboard project for Credit Risk Management and portfolio analysis. It brings multiple analytical reports together in one application and uses PostgreSQL as the database.

> **Note:** The exact metrics and data availability depend on each report's implementation and the connected database.

## 2. Key Features

The repository contains report modules for:

- **ATS Analysis**
- **ATS Disbursement MoM**
- **Branch-wise Analysis**
- **Monthly Disbursement**
- **PIN Code Analysis**
- **State-wise Analysis**
- **Vintage Analysis**

The application also includes dashboard navigation, login-related code, database configuration, shared SQL/report utilities, and supporting assets.

## 3. Technology Stack

- **Python** — application and report logic
- **Streamlit** — dashboard interface
- **PostgreSQL** — data source
- **pandas** — data processing
- **Plotly** — interactive charts, where used

Refer to `requirements.txt` for the Python package list.

## 4. Project Structure

```text
Project_BI/
├── app.py
├── dashboard.py
├── login.py
├── requirements.txt
├── Run_Dashboard.bat
├── assets/
├── config/
├── Input_excel_file/
├── reports/
│   ├── ATS_Analysis.py
│   ├── ATS_Disb_MoM.py
│   ├── Branchwise_Analysis.py
│   ├── Monthly_Disbursement.py
│   ├── PIN_Code_Analysis.py
│   ├── State_Wise_Analysis.py
│   └── Vintage_Analysis.py
├── sql/
└── utils/
```

Additional files and modules may exist in the local working copy.

## 5. Prerequisites

Before running the dashboard, ensure you have:

1. A supported Python installation.
2. Access to the required PostgreSQL database.
3. Valid database configuration in your local environment.
4. The required Python packages installed.

## 6. Setup and Run

### Step 1 — Open the project folder

Open a terminal in the local `Project_BI` directory.

### Step 2 — Create and activate a virtual environment (recommended)

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, follow your organisation's approved execution-policy guidance or use Command Prompt activation:

```bat
.venv\Scripts\activate.bat
```

### Step 3 — Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4 — Configure database access

Configure the database connection using the project's existing configuration files and approved local environment variables. Keep database passwords, tokens, and other secrets out of source control.

### Step 5 — Start the dashboard

From the project root, run:

```powershell
streamlit run app.py
```

Alternatively, use `Run_Dashboard.bat` if it is configured for your local environment.

## 7. Security and Data Handling

- Do not commit `.env` files, database passwords, access tokens, or private keys.
- Do not put customer-level or other confidential business data in a public repository.
- Keep this repository private if it contains confidential company code or data.
- Review files such as `users.json`, `sessions.json`, and files in `Input_excel_file/` before sharing the repository or granting access.
- Follow your organisation's information-security and data-retention policies.

## 8. Version Control

This project uses Git for version control. The `main` branch contains the primary project version.

Common commands:

```powershell
git status
git add .
git commit -m "Describe your change"
git push
```

Use a separate branch to develop and test larger changes before merging them into `main`.

## 9. Maintenance

When adding a new report:

1. Add the report module under `reports/`.
2. Register the report in the project's report registry/navigation as required.
3. Confirm database queries, filters, and calculations.
4. Test the report locally.
5. Commit and push the verified changes.

## 10. Disclaimer

This repository contains application code and configuration for internal analytics. Dashboard outputs depend on the source data, database access, and implementation of each report. Validate important figures before using them for business decisions.
