from fastapi import FastAPI, HTTPException, status, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlmodel import Session, select
from typing import List, Optional
from contextlib import asynccontextmanager
import httpx
from pydantic import BaseModel
import os
from datetime import datetime, timedelta
import asyncio
import stripe
import secrets

from database import engine, create_db_and_tables, User, Transaction
from auth import get_current_user, create_access_token, verify_password, hash_password

# ============================================================
# KONFIGURACJA STRIPE - TRYB TESTOWY
# ============================================================
STRIPE_SECRET_KEY = "sk_test_51TbI0yK0857NUwxxiE605Rn9V260DuSIO0dWjYLbvpZxeraxzgQQ4ikkLiVGjx5mGURpVR6JBHBihm61fHicioWi00zcJrnnuT"
STRIPE_PUBLISHABLE_KEY = "pk_test_51TbI0yK0857NUwxx7SHeGpeAOHiyPBjSAIQxCEItW8jh1DVMXlT44FRiYegIxKKoJaXTRggAtfV0V9uw49eAnRWB00BgT9lUYU"

stripe.api_key = STRIPE_SECRET_KEY
# ============================================================

# Cache dla kursów
cached_rates = {}
cache_time = None
CACHE_DURATION = 60


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

class DepositRequest(BaseModel):
    amount: int  # w groszach

class PaymentRequest(BaseModel):
    amount: float  # w PLN


static_dir = "static"
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def read_index():
    return FileResponse('static/index.html')


@app.get("/config")
async def get_config():
    """Zwraca publiczny klucz Stripe do frontendu"""
    return {"stripePublishableKey": STRIPE_PUBLISHABLE_KEY}


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
        response = await client.get(url, timeout=5.0)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Błąd pobierania kursu {currency_code}")
        return response.json()["rates"][0]["mid"]


@app.get("/rates/{currency_code}")
async def get_rate_endpoint(currency_code: str):
    try:
        rate = await get_currency_rate(currency_code)
        return {"currency": currency_code.upper(), "mid": rate}
    except HTTPException:
        raise HTTPException(status_code=404, detail=f"Waluta {currency_code.upper()} nie istnieje")


@app.get("/rates")
async def get_all_rates():
    global cached_rates, cache_time
    
    if cache_time and datetime.now() - cache_time < timedelta(seconds=CACHE_DURATION):
        return cached_rates
    
    currencies = ["USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "NOK", "SEK"]
    rates = {}
    
    tasks = [get_currency_rate(curr) for curr in currencies]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for curr, result in zip(currencies, results):
        if isinstance(result, Exception):
            continue
        rates[curr] = result
    
    rates["PLN"] = 1.0
    
    cached_rates = rates
    cache_time = datetime.now()
    
    return rates


@app.post("/exchange")
async def exchange_currency(
    from_currency: str,
    to_currency: str,
    amount: float,
    current_user: User = Depends(get_current_user)
):
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Kwota musi być większa od 0")

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


# --- TRADYCYJNE DOŁADOWANIE (API 1) ---

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
        
        deposit_transaction = Transaction(
            user_id=user.id,
            currency="PLN",
            amount=amount,
            rate=1.0
        )
        session.add(deposit_transaction)
        session.commit()
        session.refresh(user)
        
        return {"message": "Wpłacono pomyślnie", "new_balance": user.balance_pln}


# ============ API 2: STRIPE INTEGRATION - SYMULACJA ============

@app.post("/stripe/create-payment-intent")
async def create_payment_intent(
    request: PaymentRequest,
    current_user: User = Depends(get_current_user)
):
    """Tworzy PaymentIntent w Stripe - dla testowych kart"""
    try:
        amount_grosze = int(request.amount * 100)
        
        # Tworzenie PaymentIntent w Stripe (tryb testowy)
        intent = stripe.PaymentIntent.create(
            amount=amount_grosze,
            currency="pln",
            metadata={
                "user_id": str(current_user.id),
                "username": current_user.username
            }
        )
        
        return {
            "clientSecret": intent.client_secret,
            "paymentIntentId": intent.id
        }
        
    except Exception as e:
        print(f"Błąd Stripe: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/stripe/confirm-payment")
async def confirm_payment(
    payment_intent_id: str,
    current_user: User = Depends(get_current_user)
):
    """Potwierdza płatność i doładowuje konto"""
    try:
        # Pobierz PaymentIntent ze Stripe
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        if intent.status == "succeeded":
            amount_pln = intent.amount / 100
            
            with Session(engine) as session:
                user = session.get(User, current_user.id)
                user.balance_pln += amount_pln
                session.add(user)
                
                deposit_transaction = Transaction(
                    user_id=user.id,
                    currency="PLN",
                    amount=amount_pln,
                    rate=1.0
                )
                session.add(deposit_transaction)
                session.commit()
            
            return {"success": True, "message": f"Doładowano {amount_pln:.2f} PLN"}
        else:
            return {"success": False, "error": f"Status płatności: {intent.status}"}
            
    except Exception as e:
        print(f"Błąd weryfikacji: {e}")
        return {"success": False, "error": str(e)}


@app.get("/stripe/success")
async def stripe_payment_success():
    """Strona sukcesu"""
    return FileResponse('static/success.html')


@app.get("/stripe/cancel")
async def stripe_payment_cancel():
    """Strona anulowania"""
    return FileResponse('static/cancel.html')


# --- ADMIN ---

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
