let authToken = localStorage.getItem("token") || "";
let availableCurrencies = [];
let currentRates = {};

window.onload = async () => {
    await loadRates();
    await loadCurrencies();
    await initStripe();
    if (authToken) {
        await loadUserData();
        showPrivateView();
    } else {
        showPublicView();
    }
    setupCalculatorListeners();
    setupExchangePreview();
    
    // DODAJ TE LINIE - przypisanie event listeners do przycisków
    const loginBtn = document.getElementById('loginButton');
    const registerBtn = document.getElementById('registerButton');
    
    if (loginBtn) {
        loginBtn.addEventListener('click', handleLogin);
    }
    if (registerBtn) {
        registerBtn.addEventListener('click', handleRegister);
    }
    
    // ZABLOKUJ automatyczne submitowanie na Enter
    const loginUserInput = document.getElementById('loginUser');
    const loginPassInput = document.getElementById('loginPass');
    const regUserInput = document.getElementById('regUser');
    const regPassInput = document.getElementById('regPass');
    
    if (loginUserInput) {
        loginUserInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleLogin();
            }
        });
    }
    if (loginPassInput) {
        loginPassInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleLogin();
            }
        });
    }
    if (regUserInput) {
        regUserInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleRegister();
            }
        });
    }
    if (regPassInput) {
        regPassInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleRegister();
            }
        });
    }
};

async function loadRates() {
    const grid = document.getElementById('ratesGrid');
    grid.innerHTML = '<div class="loading">Ładowanie kursów...</div>';
    try {
        const res = await fetch('/rates');
        const data = await res.json();
        currentRates = data;
        const currencies = Object.keys(data).filter(c => c !== 'PLN');
        grid.innerHTML = currencies.map(curr => `
            <div class="rate-card" onclick="setCurrencyForExchange('${curr}')">
                <div class="rate-currency">${curr}</div>
                <div class="rate-value">${data[curr].toFixed(4)} PLN</div>
                <div class="rate-base">1 ${curr}</div>
            </div>
        `).join('');
    } catch(e) {
        grid.innerHTML = '<div class="loading">Nie udało się pobrać kursów</div>';
    }
}

function setCurrencyForExchange(currency) {
    if (document.getElementById('privateView').classList.contains('hidden')) {
        openAuthModal();
        return;
    }
    document.getElementById('toCurrency').value = currency;
    updateExchangePreview();
    updateCalculator();
}

async function loadCurrencies() {
    try {
        const res = await fetch('/rates');
        const data = await res.json();
        availableCurrencies = Object.keys(data).sort();
        currentRates = data;
    } catch(e) {
        availableCurrencies = ["PLN", "USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "NZD", "NOK", "SEK", "DKK", "CZK", "HUF"];
    }
    
    const fromSelect = document.getElementById('fromCurrency');
    const toSelect = document.getElementById('toCurrency');
    const calcFrom = document.getElementById('calcFromCurrency');
    const calcTo = document.getElementById('calcToCurrency');
    
    const options = availableCurrencies.map(c => `<option value="${c}">${c}</option>`).join('');
    
    if (fromSelect) fromSelect.innerHTML = options;
    if (toSelect) toSelect.innerHTML = options;
    if (calcFrom) calcFrom.innerHTML = options;
    if (calcTo) calcTo.innerHTML = options;
    
    if (fromSelect) fromSelect.value = "PLN";
    if (toSelect) toSelect.value = "EUR";
    if (calcFrom) calcFrom.value = "PLN";
    if (calcTo) calcTo.value = "EUR";
    
    updateCalculator();
    updateExchangePreview();
}

function setupCalculatorListeners() {
    const calcFromAmount = document.getElementById('calcFromAmount');
    const calcFromCurrency = document.getElementById('calcFromCurrency');
    const calcToCurrency = document.getElementById('calcToCurrency');
    
    if (calcFromAmount) calcFromAmount.addEventListener('input', updateCalculator);
    if (calcFromCurrency) calcFromCurrency.addEventListener('change', updateCalculator);
    if (calcToCurrency) calcToCurrency.addEventListener('change', updateCalculator);
}

function setupExchangePreview() {
    const fromCurrency = document.getElementById('fromCurrency');
    const toCurrency = document.getElementById('toCurrency');
    const amount = document.getElementById('amount');
    
    if (fromCurrency) fromCurrency.addEventListener('change', updateExchangePreview);
    if (toCurrency) toCurrency.addEventListener('change', updateExchangePreview);
    if (amount) amount.addEventListener('input', updateExchangePreview);
}

function updateCalculator() {
    const fromAmount = parseFloat(document.getElementById('calcFromAmount')?.value) || 0;
    const fromCurr = document.getElementById('calcFromCurrency')?.value || 'PLN';
    const toCurr = document.getElementById('calcToCurrency')?.value || 'EUR';
    
    if (!currentRates[fromCurr] || !currentRates[toCurr]) return;
    
    const fromRate = currentRates[fromCurr];
    const toRate = currentRates[toCurr];
    
    const toAmount = (fromAmount * fromRate) / toRate;
    
    const toInput = document.getElementById('calcToAmount');
    if (toInput) toInput.value = toAmount.toFixed(4);
    
    const rateInfo = document.getElementById('liveRateInfo');
    if (rateInfo) {
        rateInfo.innerHTML = `📊 1 ${fromCurr} = ${(fromRate / toRate).toFixed(4)} ${toCurr} • 1 ${toCurr} = ${(toRate / fromRate).toFixed(4)} ${fromCurr}`;
    }
}

function updateExchangePreview() {
    const fromCurr = document.getElementById('fromCurrency')?.value || 'PLN';
    const toCurr = document.getElementById('toCurrency')?.value || 'EUR';
    const amount = parseFloat(document.getElementById('amount')?.value) || 0;
    
    if (!currentRates[fromCurr] || !currentRates[toCurr]) return;
    
    const fromRate = currentRates[fromCurr];
    const toRate = currentRates[toCurr];
    
    const receivedAmount = (amount * fromRate) / toRate;
    
    const previewDiv = document.getElementById('exchangePreview');
    if (previewDiv && amount > 0) {
        previewDiv.innerHTML = `📈 Podgląd: Otrzymasz ${receivedAmount.toFixed(4)} ${toCurr} za ${amount.toFixed(2)} ${fromCurr}<br>📉 Kurs: 1 ${fromCurr} = ${(fromRate / toRate).toFixed(4)} ${toCurr}`;
    } else if (previewDiv) {
        previewDiv.innerHTML = `📊 1 ${fromCurr} = ${(fromRate / toRate).toFixed(4)} ${toCurr} • 1 ${toCurr} = ${(toRate / fromRate).toFixed(4)} ${fromCurr}`;
    }
}

async function loadUserData() {
    try {
        const res = await fetch('/users/me', {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (res.status === 401) {
            handleLogout();
            return;
        }
        const data = await res.json();
        document.getElementById('balancePLN').innerHTML = data.balance_pln.toFixed(2);
        const currenciesDiv = document.getElementById('userCurrencies');
        const entries = Object.entries(data.currencies || {});
        if (entries.length === 0) {
            currenciesDiv.innerHTML = '<span class="currency-badge">brak</span>';
        } else {
            currenciesDiv.innerHTML = entries.map(([c, a]) => `<span class="currency-badge">${a.toFixed(2)} ${c}</span>`).join('');
        }
    } catch(e) { console.error(e); }
}

function showPublicView() {
    document.getElementById('publicView').classList.remove('hidden');
    document.getElementById('privateView').classList.add('hidden');
    document.getElementById('navAuth').innerHTML = '<button class="nav-btn" onclick="openAuthModal()">Zaloguj</button>';
}

function showPrivateView() {
    document.getElementById('publicView').classList.add('hidden');
    document.getElementById('privateView').classList.remove('hidden');
    document.getElementById('navAuth').innerHTML = '<button class="nav-btn" onclick="handleLogout()">Konto</button>';
    updateCalculator();
    updateExchangePreview();
}

function openAuthModal() {
    document.getElementById('authModal').classList.remove('hidden');
    switchTab('login');
}

function closeAuthModal() {
    document.getElementById('authModal').classList.add('hidden');
}

function switchTab(tab) {
    const loginPanel = document.getElementById('loginPanel');
    const registerPanel = document.getElementById('registerPanel');
    const tabs = document.querySelectorAll('.tab');
    if (tab === 'login') {
        loginPanel.classList.remove('hidden');
        registerPanel.classList.add('hidden');
        tabs[0].classList.add('active');
        tabs[1].classList.remove('active');
    } else {
        loginPanel.classList.add('hidden');
        registerPanel.classList.remove('hidden');
        tabs[0].classList.remove('active');
        tabs[1].classList.add('active');
    }
}

async function handleLogin() {
    const username = document.getElementById('loginUser').value.trim();
    const password = document.getElementById('loginPass').value;
    if (!username || !password) { alert("Wpisz login i hasło"); return; }
    
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    
    try {
        const res = await fetch('/token', { method: 'POST', body: formData });
        if (res.ok) {
            const data = await res.json();
            authToken = data.access_token;
            localStorage.setItem("token", authToken);
            closeAuthModal();
            await loadUserData();
            showPrivateView();
            await loadRates();
        } else {
            alert("Błędny login lub hasło");
        }
    } catch(e) { alert("Błąd połączenia"); }
}

async function handleRegister() {
    const username = document.getElementById('regUser').value.trim();
    const password = document.getElementById('regPass').value;
    if (!username || !password) { alert("Wypełnij wszystkie pola"); return; }
    if (password.length < 4) { alert("Hasło musi mieć min. 4 znaki"); return; }
    
    try {
        const res = await fetch('/users/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        if (res.ok) {
            alert("Konto utworzone! Możesz się zalogować.");
            switchTab('login');
            document.getElementById('loginUser').value = username;
            document.getElementById('loginPass').value = '';
        } else {
            const err = await res.json();
            alert(err.detail || "Błąd rejestracji");
        }
    } catch(e) { alert("Błąd połączenia"); }
}

async function handleExchange() {
    const fromCurr = document.getElementById('fromCurrency').value;
    const toCurr = document.getElementById('toCurrency').value;
    const amount = parseFloat(document.getElementById('amount').value);
    const statusDiv = document.getElementById('exchangeStatus');
    
    if (fromCurr === toCurr) {
        statusDiv.className = "status status-error";
        statusDiv.innerHTML = "Waluty muszą być różne";
        statusDiv.classList.remove('hidden');
        return;
    }
    if (isNaN(amount) || amount <= 0) {
        statusDiv.className = "status status-error";
        statusDiv.innerHTML = "Podaj poprawną kwotę";
        statusDiv.classList.remove('hidden');
        return;
    }
    
    statusDiv.className = "status status-info";
    statusDiv.innerHTML = "Przetwarzanie...";
    statusDiv.classList.remove('hidden');
    
    try {
        const res = await fetch(`/exchange?from_currency=${fromCurr}&to_currency=${toCurr}&amount=${amount}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        const data = await res.json();
        if (res.ok) {
            statusDiv.className = "status status-success";
            statusDiv.innerHTML = `✓ Wymiana udana<br>Pobrano: ${parseFloat(data.pobrano).toFixed(2)} ${fromCurr}<br>Otrzymano: ${parseFloat(data.otrzymano).toFixed(4)} ${toCurr}`;
            document.getElementById('amount').value = '';
            await loadUserData();
            await loadRates();
            updateCalculator();
            updateExchangePreview();
        } else {
            statusDiv.className = "status status-error";
            statusDiv.innerHTML = "✗ " + (data.detail || "Błąd wymiany");
        }
    } catch(e) {
        statusDiv.className = "status status-error";
        statusDiv.innerHTML = "✗ Błąd połączenia";
    }
}

async function handleDeposit() {
    const amount = prompt("Kwota doładowania (PLN):", "100");
    if (!amount) return;
    const num = parseFloat(amount);
    if (isNaN(num) || num <= 0) { alert("Podaj poprawną kwotę"); return; }
    if (num > 10000) { alert("Maksymalna wpłata to 10 000 PLN"); return; }
    
    try {
        const res = await fetch(`/deposit?amount=${num}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (res.ok) {
            alert(`Doładowano ${num} PLN`);
            await loadUserData();
        } else {
            alert("Błąd doładowania");
        }
    } catch(e) { alert("Błąd połączenia"); }
}

function handleLogout() {
    localStorage.removeItem("token");
    authToken = "";
    showPublicView();
    loadRates();
}

function toggleSettings() {
    const modal = document.getElementById('settingsModal');
    modal.classList.toggle('hidden');
    document.getElementById('newUsername').value = '';
    document.getElementById('newPassword').value = '';
}

async function updateUsername() {
    const newUsername = document.getElementById('newUsername').value.trim();
    if (!newUsername) { alert("Podaj nowy login"); return; }
    try {
        const res = await fetch('/users/me/update', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
            body: JSON.stringify({ username: newUsername })
        });
        if (res.ok) {
            alert("Login zmieniony. Zaloguj się ponownie.");
            handleLogout();
        } else {
            const err = await res.json();
            alert(err.detail || "Błąd");
        }
    } catch(e) { alert("Błąd"); }
}

async function updatePassword() {
    const newPassword = document.getElementById('newPassword').value;
    if (!newPassword || newPassword.length < 4) { alert("Hasło musi mieć min. 4 znaki"); return; }
    try {
        const res = await fetch('/users/me/update', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
            body: JSON.stringify({ password: newPassword })
        });
        if (res.ok) {
            alert("Hasło zmienione. Zaloguj się ponownie.");
            handleLogout();
        } else {
            alert("Błąd");
        }
    } catch(e) { alert("Błąd"); }
}

async function deleteAccount() {
    if (!confirm("Czy na pewno chcesz usunąć konto? Tej operacji nie można cofnąć.")) return;
    try {
        const res = await fetch('/users/me', {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (res.ok) {
            alert("Konto zostało usunięte.");
            handleLogout();
        } else {
            alert("Błąd usuwania konta");
        }
    } catch(e) { alert("Błąd"); }
}

window.onclick = function(event) {
    const authModal = document.getElementById('authModal');
    const settingsModal = document.getElementById('settingsModal');
    if (event.target === authModal) closeAuthModal();
    if (event.target === settingsModal) toggleSettings();
};

async function handleCardDeposit() {
    const amount = prompt("Kwota doładowania (PLN):", "100");
    if (!amount) return;
    
    const num = parseFloat(amount);
    if (isNaN(num) || num <= 0) {
        alert("Podaj poprawną kwotę");
        return;
    }
    if (num > 10000) {
        alert("Maksymalna wpłata to 10 000 PLN");
        return;
    }
    
    const amountGrosze = Math.round(num * 100);
    
    try {
        const res = await fetch('/create-deposit-session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({ amount: amountGrosze })
        });
        
        const data = await res.json();
        
        if (res.ok && data.url) {
            // Przekieruj do Stripe Checkout
            window.location.href = data.url;
        } else {
            alert("Błąd tworzenia sesji płatności");
        }
    } catch(e) {
        alert("Błąd połączenia: " + e.message);
    }
}
