from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlmodel import Session, select
from typing import List, Optional
from contextlib import asynccontextmanager
import httpx
from pydantic import BaseModel

from database import engine, create_db_and_tables, User, Transaction
from auth import get_current_user, create_access_token, verify_password, hash_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UserCreate(BaseModel):
    username: str
    password: str

class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None

class AdminUserView(BaseModel):
    id: int
    login: str
    pln: float
    inne_waluty: dict


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def read_index():
    return FileResponse('static/index.html')


# --- LOGOWANIE I REJESTRACJA ---

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == form_data.username)).first()
        if not user or not verify_password(form_data.password, user.password):
            raise HTTPException(status_code=401, detail="Błędny login lub hasło")
        token = create_access_token(data={"sub": user.username})
        return {"access_token": token, "token_type": "bearer"}


@app.post("/users/", status_code=201)
def create_user(user: UserCreate):
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == user.username)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Użytkownik już istnieje")
        db_user = User(
            username=user.username,
            password=hash_password(user.password),
            balance_pln=0.0
        )
        session.add(db_user)
        session.commit()
        return {"message": "Użytkownik stworzony"}


# --- ZARZĄDZANIE KONTEM ---

@app.get("/users/me")
def get_me(current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        transactions = session.exec(
            select(Transaction).where(Transaction.user_id == current_user.id)
        ).all()
        wallet = {}
        for t in transactions:
            wallet[t.currency] = wallet.get(t.currency, 0) + t.amount
        return {
            "username": current_user.username,
            "balance_pln": current_user.balance_pln,
            "currencies": {k: round(v, 4) for k, v in wallet.items() if v > 0}
        }


@app.put("/users/me/update")
def update_user(data: UserUpdate, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        user = session.get(User, current_user.id)
        if data.username:
            existing = session.exec(select(User).where(User.username == data.username)).first()
            if existing and existing.id != user.id:
                raise HTTPException(status_code=400, detail="Login już zajęty")
            user.username = data.username
        if data.password:
            user.password = hash_password(data.password)
        session.add(user)
        session.commit()
        return {"message": "Dane zaktualizowane"}


@app.delete("/users/me")
def delete_account(current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        user = session.get(User, current_user.id)
        session.delete(user)
        session.commit()
    return {"message": "Konto usunięte"}


# --- KANTOR I WALUTY ---

async def get_currency_rate(currency_code: str):
    if currency_code.upper() == "PLN":
        return 1.0
    url = f"https://api.nbp.pl/api/exchangerates/rates/a/{currency_code}/?format=json"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Błąd pobierania kursu {currency_code} z NBP")
        return response.json()["rates"][0]["mid"]


@app.get("/rates/{currency_code}")
async def get_rate_endpoint(currency_code: str):
    try:
        rate = await get_currency_rate(currency_code)
        return {
            "currency": currency_code.upper(),
            "mid": rate
        }
    except HTTPException:
        raise HTTPException(status_code=404, detail=f"Waluta {currency_code.upper()} nie istnieje")


@app.post("/exchange")
async def exchange_currency(
    from_currency: str,
    to_currency: str,
    amount: float,
    current_user: User = Depends(get_current_user)
):
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        raise HTTPException(status_code=400, detail="Waluty muszą być różne")

    rate_from = await get_currency_rate(from_currency)
    rate_to = await get_currency_rate(to_currency)

    with Session(engine) as session:
        user = session.get(User, current_user.id)

        if from_currency == "PLN":
            if user.balance_pln < amount:
                raise HTTPException(status_code=400, detail="Niewystarczające środki PLN")
            user.balance_pln -= amount
        else:
            transactions = session.exec(
                select(Transaction).where(
                    Transaction.user_id == user.id,
                    Transaction.currency == from_currency
                )
            ).all()
            current_wallet_balance = sum(t.amount for t in transactions)
            if current_wallet_balance < amount:
                raise HTTPException(status_code=400, detail=f"Niewystarczające środki {from_currency}")
            session.add(Transaction(user_id=user.id, currency=from_currency, amount=-amount, rate=rate_from))

        bought_amount = (amount * rate_from) / rate_to

        if to_currency == "PLN":
            user.balance_pln += bought_amount
        else:
            session.add(Transaction(user_id=user.id, currency=to_currency, amount=bought_amount, rate=rate_to))

        session.add(user)
        session.commit()
        session.refresh(user)

        return {
            "wiadomosc": "Wymiana udana",
            "pobrano": f"{amount:.2f} {from_currency}",
            "otrzymano": f"{bought_amount:.4f}",
            "waluta_docelowa": to_currency
        }


@app.post("/deposit")
async def deposit_money(amount: float, current_user: User = Depends(get_current_user)):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Kwota musi być dodatnia")
    if amount > 10000:
        raise HTTPException(status_code=400, detail="Maksymalna jednorazowa wpłata to 10 000 PLN")
    with Session(engine) as session:
        user = session.get(User, current_user.id)
        user.balance_pln += amount
        session.add(user)
        session.commit()
        session.refresh(user)
        return {"message": "Wpłacono pomyślnie", "new_balance": user.balance_pln}


@app.get("/admin/all_users", response_model=List[AdminUserView])
def get_all_users_admin(current_user: User = Depends(get_current_user)):
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="Tylko admin może to widzieć")
    with Session(engine) as session:
        all_users = session.exec(select(User)).all()
        result = []
        for u in all_users:
            transactions = session.exec(
                select(Transaction).where(Transaction.user_id == u.id)
            ).all()
            wallet = {}
            for t in transactions:
                wallet[t.currency] = wallet.get(t.currency, 0) + t.amount
            result.append({
                "id": u.id,
                "login": u.username,
                "pln": u.balance_pln,
                "inne_waluty": {k: round(v, 2) for k, v in wallet.items() if v != 0}
            })
        return result


@app.get("/history/{currency_code}")
async def get_currency_history(currency_code: str):
    from datetime import date, timedelta
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    url = f"https://api.frankfurter.app/{start_date}..{end_date}?from=PLN&to={currency_code.upper()}"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Nie udało się pobrać historii kursu")
        
        data = response.json()
        rates = data.get("rates", {})
        
        return {
            "currency": currency_code.upper(),
            "history": [
                {"date": date_str, "rate": round(1 / values[currency_code.upper()], 4)}
                for date_str, values in sorted(rates.items())
                if currency_code.upper() in values
            ]
        }