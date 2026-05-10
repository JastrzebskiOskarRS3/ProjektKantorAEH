let authToken = localStorage.getItem("token") || "";
let userCurrencies = {};

window.onload = function() {
    if (authToken) {
        document.getElementById('authSection').classList.add('hidden');
        document.getElementById('exchangeSection').classList.remove('hidden');
        updateWallet();
    }
};

async function updateWallet() {
    try {
        const res = await fetch('/users/me', {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (res.status === 401) { handleLogout(); return; }
        
        const data = await res.json();
        
        userCurrencies = data.currencies || {};
        userCurrencies["PLN"] = data.balance_pln;

        document.getElementById('displayUser').innerText = data.username;
        document.getElementById('balancePLN').innerText = data.balance_pln.toFixed(2);
        
        const otherCurrenciesDiv = document.getElementById('otherCurrencies');
        const entries = Object.entries(data.currencies);
        
        if (entries.length === 0) {
            otherCurrenciesDiv.innerHTML = "<small>Inne waluty: brak</small>";
        } else {
            let list = entries.map(([curr, amt]) => `<b>${amt.toFixed(2)}</b> ${curr}`).join(', ');
            otherCurrenciesDiv.innerHTML = `<strong>Twoje waluty:</strong> ${list}`;
        }
    } catch (e) { 
        console.error("Błąd podczas aktualizacji portfela:", e); 
    }
}

async function handleDeposit() {
    const amount = prompt("Podaj kwotę doładowania PLN:");
    if (!amount || isNaN(amount) || parseFloat(amount) <= 0) return;
    try {
        const res = await fetch(`/deposit?amount=${amount}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (res.ok) updateWallet();
    } catch (e) { alert("Błąd połączenia."); }
}

async function handleLogin() {
    const u = document.getElementById('usernameField').value;
    const p = document.getElementById('passwordField').value;
    if (!u || !p) { alert("Wpisz login i hasło!"); return; }

    const formData = new FormData();
    formData.append('username', u);
    formData.append('password', p);
    
    try {
        const res = await fetch('/token', { method: 'POST', body: formData });
        if (res.ok) {
            const data = await res.json();
            authToken = data.access_token;
            localStorage.setItem("token", authToken);
            location.reload();
        } else { 
            alert("Błędne dane logowania."); 
        }
    } catch (e) { alert("Błąd serwera."); }
}

async function handleRegister() {
    const uField = document.getElementById('usernameField');
    const pField = document.getElementById('passwordField');
    const u = uField.value;
    const p = pField.value;

    if (!u || !p) { alert("Wpisz login i hasło dla nowego konta!"); return; }

    try {
        const res = await fetch('/users/', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: u, password: p })
        });
        
        if (res.ok) {
            alert("Konto utworzone pomyślnie! Teraz możesz się zalogować.");
            uField.value = "";
            pField.value = "";
        } else {
            const err = await res.json();
            alert("Błąd: " + err.detail);
        }
    } catch (e) { alert("Błąd połączenia."); }
}

async function handleExchange() {
    const fromCode = document.getElementById('payCurrCode').value.toUpperCase(); 
    const toCode = document.getElementById('currCode').value.toUpperCase();      
    const amount = parseFloat(document.getElementById('plnAmount').value);        
    const statusDiv = document.getElementById('status');
    
    if (!fromCode || !toCode || isNaN(amount) || amount <= 0) {
        alert("Uzupełnij poprawnie wszystkie pola!");
        return;
    }

    const availableBalance = userCurrencies[fromCode] || 0;
    if (amount > availableBalance) {
        statusDiv.innerHTML = `<div class="error">❌ Brak środków! Masz tylko ${availableBalance.toFixed(2)} ${fromCode}</div>`;
        return;
    }

    try {
        const res = await fetch(`/exchange?from_currency=${fromCode}&to_currency=${toCode}&amount=${amount}`, { 
            method: 'POST',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        const data = await res.json();

        if (res.ok) {
            const receivedAmount = parseFloat(data.otrzymano);
            statusDiv.innerHTML = `
                <div class="info">
                    ✅ <b>Wymiana udana!</b><br>
                    Pobrano: <b>${amount.toFixed(2)} ${fromCode}</b><br>
                    Otrzymano: <b>${receivedAmount.toFixed(2)} ${toCode}</b>
                </div>`;
            updateWallet();
            const chartCurrency = toCode === 'PLN' ? fromCode : toCode;
            showCurrencyChart(chartCurrency, fromCode);
        } else {
            let errorMsg = data.detail;
            if (errorMsg.includes("pobierania kursu") || errorMsg.includes("not found")) {
                errorMsg = "Wpisz poprawny kod waluty";
            }
            statusDiv.innerHTML = `<div class="error">❌ ${errorMsg}</div>`;
        }
    } catch (e) { 
        statusDiv.innerHTML = `<div class="error">❌ Błąd połączenia z serwerem.</div>`;
    }
}

function handleLogout() {
    localStorage.removeItem("token");
    location.reload();
}

function toggleOptions() {
    const modal = document.getElementById('optionsModal');
    modal.classList.toggle('hidden');
}

window.onclick = function(event) {
    const modal = document.getElementById('optionsModal');
    if (event.target == modal) {
        modal.classList.add('hidden');
    }
}

async function updateAccount(type) {
    const inputId = type === 'username' ? 'newUsername' : 'newPassword';
    const val = document.getElementById(inputId).value;
    if (!val) { alert("Pole nie może być puste!"); return; }

    const res = await fetch('/users/me/update', {
        method: 'PUT',
        headers: { 
            'Content-Type': 'application/json', 
            'Authorization': `Bearer ${authToken}` 
        },
        body: JSON.stringify({ [type]: val })
    });

    if (res.ok) { 
        alert("Dane zostały zaktualizowane. Zaloguj się ponownie."); 
        handleLogout(); 
    } else {
        const err = await res.json();
        alert("Błąd aktualizacji: " + err.detail);
    }
}

async function deleteAccount() {
    if (confirm("Czy na pewno chcesz całkowicie usunąć konto? Tej operacji nie można cofnąć.")) {
        const res = await fetch('/users/me', { 
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (res.ok) {
            alert("Konto zostało usunięte.");
            handleLogout();
        }
    }
}

async function showCurrencyChart(currencyCode, fromCurrency = 'PLN') {
    const existingChart = document.getElementById('chartSection');
    if (existingChart) existingChart.remove();

    const chartSection = document.createElement('div');
    chartSection.id = 'chartSection';
    chartSection.style.cssText = 'margin-top:20px; background:white; padding:20px; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.08);';
    chartSection.innerHTML = `
        <h4 style="margin:0 0 15px; color:#2c3e50;">📈 Kurs ${currencyCode}/PLN — ostatnie 30 dni</h4>
        <canvas id="rateChart" height="120"></canvas>
    `;
    document.getElementById('status').after(chartSection);

    try {
        const res = await fetch(`/history/${currencyCode}`);
        const data = await res.json();

        const labels = data.history.map(h => h.date);
        const rates = data.history.map(h => h.rate);
        const min = Math.min(...rates);
        const max = Math.max(...rates);

        const ctx = document.getElementById('rateChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: `${currencyCode}/PLN`,
                    data: rates,
                    borderColor: '#3498db',
                    backgroundColor: 'rgba(52,152,219,0.08)',
                    borderWidth: 2,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => `${ctx.parsed.y.toFixed(4)} PLN`
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            maxTicksLimit: 8,
                            font: { size: 11 }
                        }
                    },
                    y: {
                        min: parseFloat((min * 0.998).toFixed(4)),
                        max: parseFloat((max * 1.002).toFixed(4)),
                        ticks: {
                            font: { size: 11 },
                            callback: v => v.toFixed(4)
                        }
                    }
                }
            }
        });
    } catch(e) {
        chartSection.innerHTML += '<p style="color:#e74c3c">Nie udało się załadować wykresu.</p>';
    }
}