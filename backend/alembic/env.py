import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine

import app.advising_models  # noqa: F401
import app.intake_models  # noqa: F401
from alembic import context
from app.models import Base

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
url = os.environ["MIGRATION_DATABASE_URL"]
engine = create_engine(url, hide_parameters=True)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
