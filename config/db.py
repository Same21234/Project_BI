from urllib.parse import quote_plus
from sqlalchemy import create_engine

# ---------------- DB Config ----------------
db_config = {
    "user": "saurabh_mehrotra",
    "password": "Same@1234",
    "host": "db-report-risk.czukgkusg65k.ap-south-1.rds.amazonaws.com",
    "port": 5432,
    "database": "credit_risk",
    "schema": "warburg_mom"
}

# Encode Password
encoded_password = quote_plus(db_config["password"])

# Create Database Engine
engine = create_engine(
    f"postgresql+psycopg2://"
    f"{db_config['user']}:"
    f"{encoded_password}@"
    f"{db_config['host']}:"
    f"{db_config['port']}/"
    f"{db_config['database']}"
)