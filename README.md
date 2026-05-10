# Kantor Online

Aplikacja webowa do wymiany walut z wykorzystaniem rzeczywistych kursów z Narodowego Banku Polskiego (NBP).

## Funkcjonalności

- **Rejestracja i logowanie użytkowników** - bezpieczne uwierzytelnianie z użyciem JWT
- **Portfel użytkownika** - śledzenie stanu konta w PLN oraz posiadanych walut
- **Wymiana walut** - przewalutowanie po aktualnych kursach NBP
- **Doładowanie konta** - wpłata środków w PLN (limit 10 000 PLN jednorazowo)
- **Historia kursów** - wykres zmian kursu wybranej waluty z ostatnich 30 dni
- **Zarządzanie kontem** - zmiana loginu, hasła lub usunięcie konta
- **Panel administratora** - podgląd wszystkich użytkowników i ich stanów kont (dla admina)

## Technologie

### Backend
- **FastAPI** - framework do budowy API
- **SQLModel** - ORM dla bazy danych SQLite
- **JWT** - autoryzacja i uwierzytelnianie
- **Passlib** - hashowanie haseł (bcrypt)
- **HTTPX** - asynchroniczne zapytania do API NBP

### Frontend
- **HTML5/CSS3** - struktura i stylizacja
- **JavaScript (ES6)** - logika aplikacji
- **Chart.js** - wizualizacja historii kursów

## Instalacja

### Wymagania wstępne
- Python 3.8+
- pip (menadżer pakietów Python)

### Kroki instalacji

1. **Sklonuj repozytorium**
```bash
git clone <repository-url>
cd kantor-online

2. **Utwórz i aktywuj środowisko wirtualne**
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python -m venv venv
source venv/bin/activate

3. **Zainstaluj zależności z pliku requirments.txt**
pip install -r requirements.txt

4. **Uruchom aplikację**
uvicorn main:app --reload

