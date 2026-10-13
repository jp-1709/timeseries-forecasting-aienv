// Configuration
const API_BASE_URL = window.location.hostname === 'localhost' || window.location.protocol === 'file:'
    ? 'http://localhost:8000'
    : '';  // Empty string = same origin

const DEFAULT_DAYS = 30;

// Commodity display names
const COMMODITY_LABELS = {
    gold:        'Gold',
    silver:      'Silver',
    copper:      'Copper',
    crudeoil_wti:'Crude Oil (WTI)',
    naturalgas:  'Natural Gas',
    steel_hrc:   'Steel HRC'
};

// State
let currentCommodity = 'steel_hrc';  // default; driven by commodity selector buttons
let currentDays = DEFAULT_DAYS;
let historicalChart = null;
let forecastChart = null;
let historicalData = null;
let forecastData = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initializeCommodityButtons();
    initializeTimeRangeButtons();
    loadDashboardData();
});

// Commodity selector
function initializeCommodityButtons() {
    const buttons = document.querySelectorAll('.commodity-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            buttons.forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');

            currentCommodity = e.target.dataset.commodity;

            // Update label in price card
            const label = COMMODITY_LABELS[currentCommodity] || currentCommodity.toUpperCase();
            document.getElementById('commodityLabel').textContent = label;

            // Reset displays
            document.getElementById('currentPrice').textContent = '--';
            document.getElementById('priceChange').querySelector('.change-value').textContent = '--';
            document.getElementById('lastUpdated').textContent = 'Last updated: --';
            ['pred1d','pred7d','pred30d','pred60d'].forEach(id => {
                document.getElementById(id).textContent = '--';
            });
            ['change1d','change7d','change30d','change60d'].forEach(id => {
                const el = document.getElementById(id);
                el.textContent = '--';
                el.className = 'prediction-change';
            });

            loadDashboardData();
        });
    });
}

// Time Range Button Handlers
function initializeTimeRangeButtons() {
    const buttons = document.querySelectorAll('.time-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            buttons.forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            currentDays = parseInt(e.target.dataset.days);
            loadHistoricalData();
        });
    });
}

// Main data loading
async function loadDashboardData() {
    showLoading();
    try {
        await Promise.all([
            loadHistoricalData(),
            loadForecastData()
        ]);
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        alert('Failed to load data. Please check if the backend server is running at ' + API_BASE_URL);
    } finally {
        hideLoading();
    }
}

// Load historical price data
async function loadHistoricalData() {
    try {
        const response = await fetch(
            `${API_BASE_URL}/price/history?commodity=${currentCommodity}&days=${currentDays}`
        );

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        historicalData = data;

        updateCurrentPrice(data);
        renderHistoricalChart(data);
    } catch (error) {
        console.error('Error loading historical data:', error);
        throw error;
    }
}

// Load forecast data
async function loadForecastData() {
    try {
        const response = await fetch(
            `${API_BASE_URL}/forecast?commodities=${currentCommodity}`
        );

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.results && data.results.length > 0) {
            forecastData = data.results[0];
            updatePredictionCards(forecastData);
            renderForecastChart(forecastData);
        }
    } catch (error) {
        console.error('Error loading forecast data:', error);
        throw error;
    }
}

// Update current price display
function updateCurrentPrice(data) {
    if (!data.points || data.points.length === 0) return;

    const currentPrice = data.points[data.points.length - 1].price;
    const previousPrice = data.points.length > 1 ? data.points[data.points.length - 2].price : currentPrice;
    const change = currentPrice - previousPrice;
    const changePercent = (change / previousPrice) * 100;

    document.getElementById('currentPrice').textContent = `$${currentPrice.toFixed(2)}`;

    const priceChangeEl = document.getElementById('priceChange');
    const changeValueEl = priceChangeEl.querySelector('.change-value');

    const arrow = change >= 0 ? '↑' : '↓';
    changeValueEl.textContent = `${arrow} ${Math.abs(changePercent).toFixed(2)}%`;

    priceChangeEl.className = 'price-change ' + (change >= 0 ? 'up' : 'down');

    document.getElementById('lastUpdated').textContent =
        `Last updated: ${new Date(data.end_date).toLocaleDateString()}`;
}

// Update prediction cards
function updatePredictionCards(data) {
    const predictions = data.predictions;
    const currentPrice = data.current_price;

    updatePredictionCard('1d', predictions['1_day'], currentPrice);
    updatePredictionCard('7d', predictions['7_day'], currentPrice);
    updatePredictionCard('30d', predictions['30_day'], currentPrice);
    updatePredictionCard('60d', predictions['60_day'], currentPrice);
}

function updatePredictionCard(id, prediction, currentPrice) {
    if (!prediction) return;

    const valueEl = document.getElementById(`pred${id}`);
    const changeEl = document.getElementById(`change${id}`);

    valueEl.textContent = `$${prediction.predicted_price.toFixed(2)}`;

    const changePercent = prediction.change_percent;
    const arrow = changePercent >= 0 ? '↑' : '↓';
    changeEl.textContent = `${arrow} ${Math.abs(changePercent).toFixed(2)}%`;
    changeEl.className = 'prediction-change ' + (changePercent >= 0 ? 'up' : 'down');
}

// Render historical chart
function renderHistoricalChart(data) {
    const ctx = document.getElementById('historicalChart').getContext('2d');

    const dates = data.points.map(p => p.date);
    const prices = data.points.map(p => p.price);
    const label = COMMODITY_LABELS[currentCommodity] || currentCommodity.toUpperCase();

    if (historicalChart) {
        historicalChart.destroy();
    }

    historicalChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: `${label} Price`,
                data: prices,
                borderColor: 'rgb(102, 126, 234)',
                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 5,
                pointHoverBackgroundColor: 'rgb(102, 126, 234)',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    titleColor: '#f8fafc',
                    bodyColor: '#f8fafc',
                    borderColor: 'rgba(102, 126, 234, 0.5)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        title: function (context) {
                            return new Date(context[0].label).toLocaleDateString('en-US', {
                                month: 'short', day: 'numeric', year: 'numeric'
                            });
                        },
                        label: function (context) {
                            return `Price: $${context.parsed.y.toFixed(2)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(148, 163, 184, 0.1)', drawBorder: false },
                    ticks: {
                        color: '#94a3b8',
                        maxTicksLimit: 8,
                        callback: function (value, index, values) {
                            const date = new Date(this.getLabelForValue(value));
                            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                        }
                    }
                },
                y: {
                    grid: { color: 'rgba(148, 163, 184, 0.1)', drawBorder: false },
                    ticks: {
                        color: '#94a3b8',
                        callback: function (value) { return '$' + value.toFixed(0); }
                    }
                }
            },
            interaction: { mode: 'nearest', axis: 'x', intersect: false }
        }
    });
}

// Render forecast chart
function renderForecastChart(data) {
    const ctx = document.getElementById('forecastChart').getContext('2d');

    if (!historicalData || !historicalData.points) return;

    const historicalPoints = historicalData.points.slice(-30);
    const lastDate = new Date(historicalPoints[historicalPoints.length - 1].date);
    const lastPrice = historicalPoints[historicalPoints.length - 1].price;

    const predictions = data.predictions;
    const forecastPoints = [
        { days: 0,  date: lastDate,              price: lastPrice },
        { days: 1,  date: addDays(lastDate, 1),  price: predictions['1_day']?.predicted_price },
        { days: 7,  date: addDays(lastDate, 7),  price: predictions['7_day']?.predicted_price },
        { days: 30, date: addDays(lastDate, 30), price: predictions['30_day']?.predicted_price },
        { days: 60, date: addDays(lastDate, 60), price: predictions['60_day']?.predicted_price }
    ].filter(p => p.price !== undefined);

    const allDates = [
        ...historicalPoints.map(p => p.date),
        ...forecastPoints.slice(1).map(p => formatDate(p.date))
    ];

    const historicalPrices = [
        ...historicalPoints.map(p => p.price),
        ...new Array(forecastPoints.length - 1).fill(null)
    ];

    const forecastPrices = [
        ...new Array(historicalPoints.length - 1).fill(null),
        ...forecastPoints.map(p => p.price)
    ];

    if (forecastChart) {
        forecastChart.destroy();
    }

    forecastChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: allDates,
            datasets: [
                {
                    label: 'Historical',
                    data: historicalPrices,
                    borderColor: 'rgb(102, 126, 234)',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    spanGaps: false
                },
                {
                    label: 'Forecast',
                    data: forecastPrices,
                    borderColor: 'rgb(16, 185, 129)',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    fill: false,
                    tension: 0.4,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointBackgroundColor: 'rgb(16, 185, 129)',
                    spanGaps: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    titleColor: '#f8fafc',
                    bodyColor: '#f8fafc',
                    borderColor: 'rgba(102, 126, 234, 0.5)',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        title: function (context) {
                            return new Date(context[0].label).toLocaleDateString('en-US', {
                                month: 'short', day: 'numeric', year: 'numeric'
                            });
                        },
                        label: function (context) {
                            if (context.parsed.y === null) return null;
                            return `${context.dataset.label}: $${context.parsed.y.toFixed(2)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(148, 163, 184, 0.1)', drawBorder: false },
                    ticks: {
                        color: '#94a3b8',
                        maxTicksLimit: 10,
                        callback: function (value, index, values) {
                            const date = new Date(this.getLabelForValue(value));
                            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                        }
                    }
                },
                y: {
                    grid: { color: 'rgba(148, 163, 184, 0.1)', drawBorder: false },
                    ticks: {
                        color: '#94a3b8',
                        callback: function (value) { return '$' + value.toFixed(0); }
                    }
                }
            },
            interaction: { mode: 'nearest', axis: 'x', intersect: false }
        }
    });
}

// Utility functions
function addDays(date, days) {
    const result = new Date(date);
    result.setDate(result.getDate() + days);
    return result;
}

function formatDate(date) {
    if (typeof date === 'string') return date;
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function showLoading() {
    document.getElementById('loadingOverlay').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.add('hidden');
}
