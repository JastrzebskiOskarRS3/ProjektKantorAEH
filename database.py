from sqlmodel import SQLModel, Field, create_engine, Session, select
from typing import Optional

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(
    sqlite_url, 
    connect_args={"check_same_thread": False}
)

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password: str
    balance_pln: float = Field(default=0.0)

class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    currency: str
    amount: float
    rate: float

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
