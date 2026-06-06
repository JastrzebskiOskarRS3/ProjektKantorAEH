# 💱 Kantor Online

Aplikacja webowa do wymiany walut w czasie rzeczywistym, zbudowana na FastAPI z integracją Stripe i kursami NBP.

---

## 📋 Spis treści

- [Opis projektu](#opis-projektu)
- [Technologie](#technologie)
- [Struktura projektu](#struktura-projektu)
- [Instalacja i uruchomienie](#instalacja-i-uruchomienie)
- [Konfiguracja](#konfiguracja)
- [API – dokumentacja endpointów](#api--dokumentacja-endpointów)
- [Uruchamianie testów](#uruchamianie-testów)
- [Funkcje aplikacji](#funkcje-aplikacji)

---

## Opis projektu

Kantor Online to pełnoprawna aplikacja do wymiany walut oferująca:

- rejestrację i logowanie użytkowników z JWT,
- pobieranie kursów walut na żywo z API Narodowego Banku Polskiego,
- wymianę walut między PLN a walutami obcymi (i odwrotnie),
- doładowanie konta PLN tradycyjnie lub przez Stripe (tryb testowy),
- panel administracyjny z podglądem wszystkich kont,
- kompletny zestaw testów jednostkowych i integracyjnych.

---

## Technologie

| Warstwa | Technologie |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLModel, SQLite |
| Autoryzacja | JWT (python-jose), bcrypt (passlib) |
| Płatności | Stripe (tryb testowy) |
| Kursy walut | NBP API (`api.nbp.pl`) |
| Frontend | HTML, CSS, JavaScript (vanilla) |
| Testy | pytest, pytest-asyncio, respx, httpx |

---

## Struktura projektu

```
kantor-online/
├── main.py              # Główna aplikacja FastAPI, wszystkie endpointy
├── auth.py              # Logika JWT, haszowanie haseł, autoryzacja
├── database.py          # Modele SQLModel (User, Transaction), silnik bazy
├── test_main.py         # Testy jednostkowe i integracyjne (pytest)
├── database.db          # Baza SQLite (generowana automatycznie)
└── static/
    ├── index.html       # Główny interfejs użytkownika
    ├── style.css        # Style aplikacji
    ├── script.js        # Logika frontendu
    ├── success.html     # Strona po udanej płatności Stripe
    └── cancel.html      # Strona po anulowaniu płatności Stripe
```

---

## Instalacja i uruchomienie

### 1. Sklonuj repozytorium

```bash
git clone https://github.com/twoj-login/kantor-online.git
cd kantor-online
```

### 2. Utwórz wirtualne środowisko i zainstaluj zależności

```bash
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

pip install fastapi uvicorn sqlmodel python-jose passlib[bcrypt] httpx stripe
```

### 3. Umieść pliki statyczne

Utwórz katalog `static/` i skopiuj do niego `index.html`, `style.css`, `script.js`, `success.html` oraz `cancel.html`.

```bash
mkdir static
cp index.html style.css script.js success.html cancel.html static/
```

### 4. Uruchom serwer

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Aplikacja będzie dostępna pod adresem: `http://localhost:8000`

Interaktywna dokumentacja API: `http://localhost:8000/docs`

---

## Konfiguracja

Zmienne konfiguracyjne znajdują się bezpośrednio w plikach. W środowisku produkcyjnym warto przenieść je do zmiennych środowiskowych (np. przez `python-dotenv`).

| Zmienna | Plik | Opis |
|---|---|---|
| `SECRET_KEY` | `auth.py` | Klucz do podpisywania tokenów JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `auth.py` | Czas życia tokena (domyślnie 30 min) |
| `STRIPE_SECRET_KEY` | `main.py` | Klucz prywatny Stripe (tryb testowy: `sk_test_...`) |
| `STRIPE_PUBLISHABLE_KEY` | `main.py` | Klucz publiczny Stripe (tryb testowy: `pk_test_...`) |

> **Uwaga bezpieczeństwa:** Przed wdrożeniem na produkcję zmień `SECRET_KEY` na losowy, silny klucz i nigdy nie commituj kluczy Stripe do repozytorium. Użyj `.gitignore` lub zmiennych środowiskowych.

---

## API – dokumentacja endpointów

### Publiczne

| Metoda | Endpoint | Opis |
|---|---|---|
| `GET` | `/` | Strona główna (index.html) |
| `GET` | `/config` | Zwraca publiczny klucz Stripe |
| `GET` | `/rates` | Kursy wszystkich walut (cache 60s) |
| `GET` | `/rates/{currency_code}` | Kurs pojedynczej waluty z NBP |

### Autoryzacja

| Metoda | Endpoint | Opis |
|---|---|---|
| `POST` | `/users/` | Rejestracja nowego użytkownika |
| `POST` | `/token` | Logowanie, zwraca token JWT |

### Chronione (wymagają nagłówka `Authorization: Bearer <token>`)

| Metoda | Endpoint | Opis |
|---|---|---|
| `GET` | `/users/me` | Dane zalogowanego użytkownika + portfel |
| `PUT` | `/users/me/update` | Zmiana loginu lub hasła |
| `DELETE` | `/users/me` | Usunięcie konta |
| `POST` | `/deposit?amount=<float>` | Doładowanie PLN (maks. 10 000 zł) |
| `POST` | `/exchange` | Wymiana walut (parametry: `from_currency`, `to_currency`, `amount`) |

### Stripe

| Metoda | Endpoint | Opis |
|---|---|---|
| `POST` | `/stripe/create-payment-intent` | Tworzy PaymentIntent w Stripe |
| `POST` | `/stripe/confirm-payment` | Potwierdza płatność i zasila konto |
| `GET` | `/stripe/success` | Strona po udanej płatności |
| `GET` | `/stripe/cancel` | Strona po anulowaniu płatności |

### Admin

| Metoda | Endpoint | Opis |
|---|---|---|
| `GET` | `/admin/all_users` | Lista wszystkich użytkowników (tylko konto `admin`) |

---

## Uruchamianie testów

### Instalacja zależności testowych

```bash
pip install pytest pytest-asyncio respx
```

### Uruchomienie testów

```bash
pytest test_main.py -v
```

### Uruchomienie z krótkim raportem błędów

```bash
pytest test_main.py -v --tb=short
```

### Zakres testów

Testy obejmują 7 klas:

- **`TestPublicEndpoints`** – endpointy dostępne bez logowania, kursy NBP
- **`TestAuthEndpoints`** – rejestracja, logowanie, walidacja danych
- **`TestProtectedEndpoints`** – autoryzacja JWT, zmiana danych, usuwanie konta
- **`TestCurrencyOperations`** – wymiana walut, limity, doładowania
- **`TestAdminEndpoints`** – dostęp admina, blokada dla zwykłych użytkowników
- **`TestStripeEndpoints`** – tworzenie PaymentIntent, strony sukcesu/anulowania
- **`TestBusinessLogic`** – haszowanie haseł, generowanie tokenów JWT, kalkulacja kursów
- **`TestTransactionHistory`** – zapis transakcji, kumulowanie sald walutowych
- **`TestIntegrationScenarios`** – pełny scenariusz użytkownika end-to-end

---

## Funkcje aplikacji

### Dla użytkownika
- rejestracja i bezpieczne logowanie (hasła haszowane bcrypt)
- portfel wielowalutowy (PLN + waluty obce)
- wymiana walut po kursach NBP w czasie rzeczywistym
- doładowanie konta tradycyjnie lub przez Stripe
- zmiana danych konta i usunięcie konta

### Dla administratora
- podgląd wszystkich kont i sald (endpoint `/admin/all_users`, dostęp tylko dla użytkownika `admin`)

### Techniczne
- kursy walut cachowane przez 60 sekund (ograniczenie zapytań do NBP)
- tokeny JWT wygasają po 30 minutach
- baza SQLite tworzona automatycznie przy pierwszym uruchomieniu
- obsługiwane waluty: USD, EUR, GBP, CHF, JPY, CAD, AUD, NOK, SEK, PLN

