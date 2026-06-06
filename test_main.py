import pytest
from fastapi.testclient import TestClient
from fastapi import status
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import respx
import httpx
from sqlmodel import SQLModel, Session, select

from main import app
from database import engine, User, Transaction, create_db_and_tables
from auth import hash_password, verify_password, create_access_token, get_current_user

# ============================================================
# FIXTURY
# ============================================================

@pytest.fixture(autouse=True)
def setup_database():
    """Tworzy czystą bazę danych przed każdym testem"""
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


@pytest.fixture
def client():
    """Klient testowy FastAPI"""
    return TestClient(app)


@pytest.fixture
def test_user(setup_database):
    """Tworzy testowego użytkownika w bazie"""
    with Session(engine) as session:
        user = User(
            username="testuser",
            password=hash_password("testpass123"),
            balance_pln=1000.0
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest.fixture
def test_token(test_user):
    """Generuje token JWT dla testowego użytkownika"""
    return create_access_token(data={"sub": test_user.username})


@pytest.fixture
def auth_headers(test_token):
    """Nagłówki autoryzacji dla zalogowanego użytkownika"""
    return {"Authorization": f"Bearer {test_token}"}


# ============================================================
# TESTY ENDPOINTÓW PUBLICZNYCH
# ============================================================

class TestPublicEndpoints:
    """Testy endpointów dostępnych bez logowania"""
    
    def test_root_endpoint(self, client):
        """Test strony głównej"""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
    
    def test_config_endpoint(self, client):
        """Test endpointu konfiguracji Stripe"""
        response = client.get("/config")
        assert response.status_code == status.HTTP_200_OK
        assert "stripePublishableKey" in response.json()
        key = response.json()["stripePublishableKey"]
        # Stripe publishable keys mogą zaczynać się od pk_test_ LUB pk_live_ LUB ppk_test_
        assert key.startswith(("pk_", "ppk_")), f"Nieprawidłowy format klucza: {key}"
    
    def test_get_rates_all(self, client):
        """Test pobierania wszystkich kursów walut"""
        response = client.get("/rates")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        # Sprawdź, czy podstawowe waluty istnieją
        expected_currencies = ["PLN", "USD", "EUR", "GBP", "CHF"]
        for currency in expected_currencies:
            assert currency in data
            assert isinstance(data[currency], (int, float))
            assert data[currency] > 0
    
    @respx.mock
    def test_get_single_rate_success(self, client):
        """Test pobierania pojedynczego kursu - sukces"""
        mock_response = {
            "currency": "dolar amerykański",
            "code": "USD",
            "rates": [{"mid": 4.05}]
        }
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/USD/?format=json").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        
        response = client.get("/rates/USD")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["currency"] == "USD"
        assert response.json()["mid"] == 4.05
    
    @respx.mock
    def test_get_single_rate_not_found(self, client):
        """Test pobierania nieistniejącej waluty"""
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/XXX/?format=json").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        
        response = client.get("/rates/XXX")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================
# TESTY REJESTRACJI I LOGOWANIA
# ============================================================

class TestAuthEndpoints:
    """Testy autoryzacji i zarządzania użytkownikami"""
    
    def test_register_user_success(self, client):
        """Test rejestracji nowego użytkownika"""
        response = client.post("/users/", json={
            "username": "newuser",
            "password": "securepass123"
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["message"] == "Użytkownik stworzony"
        
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == "newuser")).first()
            assert user is not None
            assert user.username == "newuser"
            assert verify_password("securepass123", user.password)
            assert user.balance_pln == 0.0
    
    def test_register_duplicate_user(self, client, test_user):
        """Test rejestracji użytkownika z już istniejącą nazwą"""
        response = client.post("/users/", json={
            "username": test_user.username,
            "password": "somepassword"
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["detail"] == "Użytkownik już istnieje"
    
    def test_register_missing_fields(self, client):
        """Test rejestracji bez wymaganych pól"""
        response = client.post("/users/", json={
            "username": "onlyusername"
        })
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_login_success(self, client, test_user):
        """Test logowania - prawidłowe dane"""
        response = client.post("/token", data={
            "username": test_user.username,
            "password": "testpass123"
        })
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"
        
        token = response.json()["access_token"]
        from jose import jwt
        from auth import SECRET_KEY, ALGORITHM
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == test_user.username
        assert "exp" in payload
    
    def test_login_wrong_password(self, client, test_user):
        """Test logowania - złe hasło"""
        response = client.post("/token", data={
            "username": test_user.username,
            "password": "wrongpassword"
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_login_nonexistent_user(self, client):
        """Test logowania - nieistniejący użytkownik"""
        response = client.post("/token", data={
            "username": "nonexistent",
            "password": "anything"
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================
# TESTY ZABEZPIECZONYCH ENDPOINTÓW
# ============================================================

class TestProtectedEndpoints:
    """Testy endpointów wymagających autoryzacji"""
    
    def test_get_current_user_success(self, client, auth_headers, test_user):
        """Test pobierania danych zalogowanego użytkownika"""
        response = client.get("/users/me", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["username"] == test_user.username
        assert response.json()["balance_pln"] == test_user.balance_pln
        assert "currencies" in response.json()
    
    def test_get_current_user_no_token(self, client):
        """Test dostępu bez tokena"""
        response = client.get("/users/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_get_current_user_invalid_token(self, client):
        """Test dostępu z nieprawidłowym tokenem"""
        response = client.get("/users/me", headers={"Authorization": "Bearer invalidtoken"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_update_username_success(self, client, auth_headers, test_user):
        """Test zmiany nazwy użytkownika"""
        response = client.put("/users/me/update", 
                              headers=auth_headers,
                              json={"username": "newusername"})
        assert response.status_code == status.HTTP_200_OK
        
        with Session(engine) as session:
            updated_user = session.get(User, test_user.id)
            assert updated_user.username == "newusername"
    
    def test_update_username_duplicate(self, client, auth_headers, test_user):
        """Test zmiany nazwy na już zajętą"""
        with Session(engine) as session:
            other_user = User(
                username="existinguser",
                password=hash_password("pass123")
            )
            session.add(other_user)
            session.commit()
        
        response = client.put("/users/me/update",
                              headers=auth_headers,
                              json={"username": "existinguser"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_update_password_success(self, client, auth_headers, test_user):
        """Test zmiany hasła"""
        response = client.put("/users/me/update",
                              headers=auth_headers,
                              json={"password": "newpassword456"})
        assert response.status_code == status.HTTP_200_OK
        
        login_response = client.post("/token", data={
            "username": test_user.username,
            "password": "newpassword456"
        })
        assert login_response.status_code == status.HTTP_200_OK
    
    def test_delete_account_success(self, client, auth_headers, test_user):
        """Test usuwania konta"""
        response = client.delete("/users/me", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        
        with Session(engine) as session:
            deleted_user = session.get(User, test_user.id)
            assert deleted_user is None
        
        protected_response = client.get("/users/me", headers=auth_headers)
        assert protected_response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================
# TESTY OPERACJI NA WALUTACH
# ============================================================

class TestCurrencyOperations:
    """Testy wymiany walut i operacji finansowych"""
    
    @respx.mock
    def test_exchange_pln_to_eur_success(self, client, auth_headers, test_user):
        """Test wymiany PLN na EUR z wystarczającymi środkami"""
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/EUR/?format=json").mock(
            return_value=httpx.Response(200, json={"rates": [{"mid": 4.50}]})
        )
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/PLN/?format=json").mock(
            return_value=httpx.Response(200, json={"rates": [{"mid": 1.0}]})
        )
        
        response = client.post("/exchange?from_currency=PLN&to_currency=EUR&amount=100",
                               headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "Wymiana udana" in data["wiadomosc"]
        assert data["pobrano"] == "100.00 PLN"
        
        user_response = client.get("/users/me", headers=auth_headers)
        assert user_response.json()["balance_pln"] == 900.0
        assert "EUR" in user_response.json()["currencies"]
    
    @respx.mock
    def test_exchange_insufficient_funds(self, client, auth_headers, test_user):
        """Test wymiany z niewystarczającymi środkami"""
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/EUR/?format=json").mock(
            return_value=httpx.Response(200, json={"rates": [{"mid": 4.50}]})
        )
        
        response = client.post("/exchange?from_currency=PLN&to_currency=EUR&amount=2000",
                               headers=auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Niewystarczające środki" in response.json()["detail"]
    
    def test_exchange_zero_amount(self, client, auth_headers):
        """Test wymiany z kwotą 0"""
        response = client.post("/exchange?from_currency=PLN&to_currency=EUR&amount=0",
                               headers=auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_exchange_same_currency(self, client, auth_headers):
        """Test wymiany tej samej waluty na samą siebie"""
        response = client.post("/exchange?from_currency=PLN&to_currency=PLN&amount=100",
                               headers=auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Waluty muszą być różne" in response.json()["detail"]
    
    def test_deposit_success(self, client, auth_headers, test_user):
        """Test doładowania konta"""
        initial_balance = test_user.balance_pln
        deposit_amount = 500.0
        
        response = client.post(f"/deposit?amount={deposit_amount}", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["new_balance"] == initial_balance + deposit_amount
        
        with Session(engine) as session:
            transactions = session.exec(
                select(Transaction).where(Transaction.user_id == test_user.id)
            ).all()
            deposit_transactions = [t for t in transactions if t.currency == "PLN" and t.amount > 0]
            assert len(deposit_transactions) >= 1
    
    def test_deposit_exceeds_limit(self, client, auth_headers):
        """Test doładowania powyżej limitu"""
        response = client.post("/deposit?amount=15000", headers=auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Maksymalna jednorazowa wpłata" in response.json()["detail"]
    
    def test_deposit_negative_amount(self, client, auth_headers):
        """Test doładowania ujemną kwotą"""
        response = client.post("/deposit?amount=-100", headers=auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================
# TESTY ADMINISTRATORA
# ============================================================

class TestAdminEndpoints:
    """Testy endpointów dostępnych tylko dla admina"""
    
    @pytest.fixture
    def admin_user(self, setup_database):
        """Tworzy użytkownika admin"""
        with Session(engine) as session:
            admin = User(
                username="admin",
                password=hash_password("adminpass"),
                balance_pln=0.0
            )
            session.add(admin)
            session.commit()
            session.refresh(admin)
            return admin
    
    @pytest.fixture
    def admin_token(self, admin_user):
        return create_access_token(data={"sub": admin_user.username})
    
    @pytest.fixture
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    def test_admin_access_all_users(self, client, admin_headers, test_user):
        """Test dostępu admina do listy wszystkich użytkowników"""
        response = client.get("/admin/all_users", headers=admin_headers)
        assert response.status_code == status.HTTP_200_OK
        
        users = response.json()
        assert len(users) >= 1
        usernames = [u["login"] for u in users]
        assert test_user.username in usernames
    
    def test_non_admin_cannot_access_admin(self, client, auth_headers):
        """Test dostępu zwykłego użytkownika do endpointów admina"""
        response = client.get("/admin/all_users", headers=auth_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================
# TESTY STRIPE
# ============================================================

class TestStripeEndpoints:
    """Testy endpointów Stripe"""
    
    def test_create_payment_intent_unauthorized(self, client):
        """Test tworzenia PaymentIntent bez autoryzacji"""
        response = client.post("/stripe/create-payment-intent", 
                               json={"amount": 100})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_create_payment_intent_invalid_amount(self, client, auth_headers):
        """Test tworzenia PaymentIntent z nieprawidłową kwotą"""
        response = client.post("/stripe/create-payment-intent",
                               headers=auth_headers,
                               json={"amount": -50})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    @patch('stripe.PaymentIntent.create')
    def test_create_payment_intent_success(self, mock_create, client, auth_headers):
        """Test udanego tworzenia PaymentIntent"""
        mock_create.return_value = MagicMock(
            client_secret="secret_123",
            id="pi_123"
        )
        
        response = client.post("/stripe/create-payment-intent",
                               headers=auth_headers,
                               json={"amount": 100})
        
        assert response.status_code == status.HTTP_200_OK
        assert "clientSecret" in response.json()
    
    def test_stripe_success_page(self, client):
        """Test strony sukcesu Stripe"""
        response = client.get("/stripe/success")
        assert response.status_code == status.HTTP_200_OK
    
    def test_stripe_cancel_page(self, client):
        """Test strony anulowania Stripe"""
        response = client.get("/stripe/cancel")
        assert response.status_code == status.HTTP_200_OK


# ============================================================
# TESTY LOGIKI BIZNESOWEJ
# ============================================================

class TestBusinessLogic:
    """Testy logiki biznesowej (nie endpointy)"""
    
    def test_password_hashing_and_verification(self):
        """Test hashowania i weryfikacji haseł"""
        password = "mySecurePassword123"
        hashed = hash_password(password)
        
        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("wrongpassword", hashed)
    
    def test_create_access_token(self):
        """Test tworzenia tokena JWT"""
        data = {"sub": "testuser", "role": "user"}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0
        
        from jose import jwt
        from auth import SECRET_KEY, ALGORITHM
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert decoded["sub"] == "testuser"
        assert decoded["role"] == "user"
        assert "exp" in decoded
    
    def test_jwt_expiration(self):
        """Test wygaśnięcia tokena"""
        from auth import ACCESS_TOKEN_EXPIRE_MINUTES
        assert ACCESS_TOKEN_EXPIRE_MINUTES == 30
    
    @respx.mock
    @pytest.mark.asyncio
    async def test_currency_rate_calculation(self):
        """Test obliczania kursów wymiany"""
        from main import get_currency_rate
        
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/USD/?format=json").mock(
            return_value=httpx.Response(200, json={"rates": [{"mid": 4.05}]})
        )
        
        rate = await get_currency_rate("USD")
        assert rate == 4.05
    
    def test_balance_initialization(self, test_user):
        """Test inicjalizacji salda użytkownika"""
        assert test_user.balance_pln == 1000.0
        
        with Session(engine) as session:
            new_user = User(
                username="freshuser",
                password=hash_password("pass")
            )
            session.add(new_user)
            session.commit()
            session.refresh(new_user)
            assert new_user.balance_pln == 0.0


# ============================================================
# TESTY TRANSAKCJI
# ============================================================

class TestTransactionHistory:
    """Testy historii transakcji"""
    
    @respx.mock
    def test_transaction_recorded_on_exchange(self, client, auth_headers, test_user):
        """Test czy transakcja jest zapisywana po wymianie"""
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/EUR/?format=json").mock(
            return_value=httpx.Response(200, json={"rates": [{"mid": 4.50}]})
        )
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/PLN/?format=json").mock(
            return_value=httpx.Response(200, json={"rates": [{"mid": 1.0}]})
        )
        
        response = client.post("/exchange?from_currency=PLN&to_currency=EUR&amount=100",
                               headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        
        with Session(engine) as session:
            transactions = session.exec(
                select(Transaction).where(Transaction.user_id == test_user.id)
            ).all()
            
            eur_transactions = [t for t in transactions if t.currency == "EUR" and t.amount > 0]
            assert len(eur_transactions) >= 1
    
    @respx.mock
    def test_multiple_currency_accumulation(self, client, auth_headers, test_user):
        """Test kumulowania się tej samej waluty"""
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/EUR/?format=json").mock(
            return_value=httpx.Response(200, json={"rates": [{"mid": 4.50}]})
        )
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/PLN/?format=json").mock(
            return_value=httpx.Response(200, json={"rates": [{"mid": 1.0}]})
        )
        
        client.post("/exchange?from_currency=PLN&to_currency=EUR&amount=100",
                    headers=auth_headers)
        client.post("/exchange?from_currency=PLN&to_currency=EUR&amount=200",
                    headers=auth_headers)
        
        with Session(engine) as session:
            transactions = session.exec(
                select(Transaction).where(Transaction.user_id == test_user.id)
            ).all()
            
            eur_total = sum(t.amount for t in transactions if t.currency == "EUR")
            expected = (100 / 4.50) + (200 / 4.50)
            assert abs(eur_total - expected) < 0.01


# ============================================================
# TESTY INTEGRACYJNE
# ============================================================

class TestIntegrationScenarios:
    """Scenariusze integracyjne - pełne flow użytkownika"""
    
    @respx.mock
    def test_complete_user_flow(self, client):
        """Pełny scenariusz: rejestracja -> login -> wpłata -> wymiana -> zmiana danych -> usunięcie"""
        
        # 1. Rejestracja
        register_response = client.post("/users/", json={
            "username": "flowuser",
            "password": "flowpass123"
        })
        assert register_response.status_code == 201
        
        # 2. Logowanie
        login_response = client.post("/token", data={
            "username": "flowuser",
            "password": "flowpass123"
        })
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 3. Wpłata środków
        deposit_response = client.post("/deposit?amount=1000", headers=headers)
        assert deposit_response.status_code == 200
        assert deposit_response.json()["new_balance"] == 1000.0
        
        # 4. Sprawdzenie salda
        me_response = client.get("/users/me", headers=headers)
        assert me_response.json()["balance_pln"] == 1000.0
        
        # 5. Mock kursów dla wymiany
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/EUR/?format=json").mock(
            return_value=httpx.Response(200, json={"rates": [{"mid": 4.50}]})
        )
        respx.get("https://api.nbp.pl/api/exchangerates/rates/a/PLN/?format=json").mock(
            return_value=httpx.Response(200, json={"rates": [{"mid": 1.0}]})
        )
        
        # 6. Wymiana waluty
        exchange_response = client.post("/exchange?from_currency=PLN&to_currency=EUR&amount=100",
                                        headers=headers)
        assert exchange_response.status_code == 200
        
        # 7. Sprawdzenie, czy saldo się zmieniło
        me_after_response = client.get("/users/me", headers=headers)
        assert me_after_response.json()["balance_pln"] == 900.0
        
        # 8. Zmiana nazwy użytkownika
        update_response = client.put("/users/me/update",
                                     headers=headers,
                                     json={"username": "newname"})
        assert update_response.status_code == 200
        
        # 9. PO ZMIANIE NAZWY - musimy zalogować się ponownie (token jest nieaktualny)
        new_login_response = client.post("/token", data={
            "username": "newname",
            "password": "flowpass123"
        })
        assert new_login_response.status_code == 200
        new_token = new_login_response.json()["access_token"]
        new_headers = {"Authorization": f"Bearer {new_token}"}
        
        # 10. Usunięcie konta (używając nowego tokena)
        delete_response = client.delete("/users/me", headers=new_headers)
        assert delete_response.status_code == 200
        
        # 11. Weryfikacja, że konto zostało usunięte
        verify_response = client.get("/users/me", headers=new_headers)
        assert verify_response.status_code == 401


# ============================================================
# URUCHAMIANIE TESTÓW
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
