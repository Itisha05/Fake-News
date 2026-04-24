// TRUTHGUARD DASHBOARD - MAIN JAVASCRIPT
// ============================================

// Global State Management
const AppState = {
    currentTab: 'dashboard',
    currentAnalysis: null,
    history: [],
    charts: {},
    preferences: {
        email: true,
        dark: false,
        autosave: true,
        confidence: true,
        sound: false
    },
    dateRange: '7days',
    isSaved: false,
    inputMode: 'text'
};

// Chart Colors Configuration
const chartColors = {
    real: '#16a34a',
    fake: '#dc2626',
    primary: '#d25176',
    secondary: '#8b5cf6',
    accent: '#f59e0b',
    warning: '#f97316'
};

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', function () {
    initializeApp();
    loadPreferences();
    initializeCharts();
    setupEventListeners();
    loadHistory();
    updateStats();
    startAutoRefresh();

    // Profile form handler
    const profileForm = document.getElementById('profile-form');
    if (profileForm) {
        profileForm.addEventListener('submit', function (e) {
            e.preventDefault();

            const nameEl = document.getElementById('setting-name');
            const phoneEl = document.getElementById('setting-phone');
            const countryEl = document.getElementById('setting-country');

            if (!nameEl || !phoneEl || !countryEl) return;

            const profileData = {
                name: nameEl.value,
                phone: phoneEl.value,
                country: countryEl.value
            };

            fetch('/save_profile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '' },
                body: JSON.stringify(profileData)
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data.success) {
                        showToast('Profile updated successfully!', 'success');
                    } else {
                        showToast('Failed to update profile', 'error');
                    }
                })
                .catch(function (err) {
                    console.error('Error saving profile:', err);
                    showToast('Failed to update profile', 'error');
                });
        });
    }
});

function initializeApp() {
    console.log('TruthGuard Dashboard Initialized');
    updateGreeting();
    checkNotifications();
    setupDragAndDrop();
}

// ============================================
// TAB NAVIGATION
// ============================================

function showTab(tabName) {
    // Remove active class from all tabs and nav items
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.nav-item').forEach(nav => {
        nav.classList.remove('active');
    });

    // Add active class to selected tab and nav
    const tab = document.getElementById('tab-' + tabName);
    const nav = document.getElementById('nav-' + tabName);

    if (tab && nav) {
        tab.classList.add('active');
        nav.classList.add('active');
        AppState.currentTab = tabName;
    }

    // Initialize specific tab content
    switch (tabName) {
        case 'analytics':
            setTimeout(function () {
                initAnalyticsCharts();
                refreshAnalytics();
            }, 100);
            break;
        case 'batch':
            setupBatchAnalysis();
            break;
        case 'history':
            refreshHistory();
            break;
    }

    // Close mobile sidebar
    if (window.innerWidth <= 768) {
        const sidebar = document.getElementById('sidebar');
        if (sidebar) sidebar.classList.remove('open');
    }

    // Smooth scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Save to localStorage
    localStorage.setItem('lastTab', tabName);
}

// ============================================
// SIDEBAR MANAGEMENT
// ============================================

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.classList.toggle('open');
    }
}

// Close sidebar when clicking outside on mobile
document.addEventListener('click', function (e) {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.querySelector('.mobile-menu-toggle');

    if (window.innerWidth <= 768 &&
        sidebar &&
        !sidebar.contains(e.target) &&
        toggle &&
        !toggle.contains(e.target) &&
        sidebar.classList.contains('open')) {
        sidebar.classList.remove('open');
    }
});

// ============================================
// ANALYZER FUNCTIONS
// ============================================

function focusAnalyzer() {
    showTab('dashboard');
    setTimeout(() => {
        const textarea = document.getElementById('news-content');
        if (textarea) {
            textarea.focus();
            textarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, 100);
}

function clearText() {
    const textarea = document.getElementById('news-content');
    if (textarea) {
        textarea.value = '';
        textarea.focus();
    }
    showToast('Text cleared', 'info');
}

async function pasteText() {
    try {
        const text = await navigator.clipboard.readText();
        const textarea = document.getElementById('news-content');
        if (textarea) {
            textarea.value = text;
            showToast('Text pasted successfully', 'success');
        }
    } catch (err) {
        console.error('Paste error:', err);
        showToast('Unable to paste. Please paste manually.', 'error');
    }
}

function setInputMode(mode) {
    AppState.inputMode = mode;

    const modeTextBtn = document.getElementById('mode-text');
    const modeUrlBtn = document.getElementById('mode-url');
    const textInputGroup = document.getElementById('text-input-group');
    const urlInputGroup = document.getElementById('url-input-group');

    if (mode === 'text') {
        modeTextBtn.classList.add('active');
        modeUrlBtn.classList.remove('active');
        textInputGroup.style.display = 'block';
        urlInputGroup.style.display = 'none';
    } else {
        modeTextBtn.classList.remove('active');
        modeUrlBtn.classList.add('active');
        textInputGroup.style.display = 'none';
        urlInputGroup.style.display = 'block';
    }
}

function clearUrl() {
    const urlInput = document.getElementById('news-url');
    if (urlInput) {
        urlInput.value = '';
        urlInput.focus();
    }
    showToast('URL cleared', 'info');
}

async function pasteUrl() {
    try {
        const text = await navigator.clipboard.readText();
        const urlInput = document.getElementById('news-url');
        if (urlInput) {
            urlInput.value = text.trim();
            showToast('URL pasted successfully', 'success');
        }
    } catch (err) {
        console.error('Paste error:', err);
        showToast('Unable to paste. Please paste manually.', 'error');
    }
}

function uploadFile() {
    const fileInput = document.getElementById('file-upload');
    if (fileInput) fileInput.click();
}

function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function (e) {
        const content = e.target.result;
        const textarea = document.getElementById('news-content');
        if (textarea) {
            textarea.value = content;
            showToast('File "' + file.name + '" loaded successfully', 'success');
        }
    };
    reader.onerror = function () {
        showToast('Failed to read file', 'error');
    };
    reader.readAsText(file);
}

function newAnalysis() {
    const resultPanel = document.getElementById('detailed-result');
    const textarea = document.getElementById('news-content');

    if (resultPanel) resultPanel.style.display = 'none';
    if (textarea) {
        textarea.value = '';
        textarea.focus();
    }

    AppState.currentAnalysis = null;
    AppState.isSaved = false;
    showToast('Ready for new analysis', 'info');
}

// ============================================
// ANALYSIS FORM SUBMISSION
// ============================================

const checkForm = document.getElementById('check-form');
if (checkForm) {
    checkForm.addEventListener('submit', async function (e) {
        e.preventDefault();

        // Hide previous results immediately
        const resultPanel = document.getElementById('detailed-result');
        if (resultPanel) resultPanel.style.display = 'none';

        AppState.isSaved = false;
        showLoading(true);
        updateLoadingProgress(0);

        try {
            const progressInterval = setInterval(() => {
                const bar = document.getElementById('loading-progress-bar');
                if (bar) {
                    const currentProgress = parseInt(bar.style.width || '0');
                    if (currentProgress < 90) {
                        updateLoadingProgress(currentProgress + 10);
                    }
                }
            }, 300);

            let response, data;

            if (AppState.inputMode === 'url') {
                const urlInput = document.getElementById('news-url');
                if (!urlInput || !urlInput.value.trim()) {
                    clearInterval(progressInterval);
                    showLoading(false);
                    showToast('Please enter a URL to analyze', 'warning');
                    return;
                }

                response = await fetch('/analyze_url', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '' },
                    body: JSON.stringify({
                        url: urlInput.value.trim()
                    })
                });
            } else {
                const content = document.getElementById('news-content');
                if (!content || !content.value.trim()) {
                    clearInterval(progressInterval);
                    showLoading(false);
                    showToast('Please enter some content to analyze', 'warning');
                    return;
                }

                const detailedAnalysis = document.getElementById('detailed-analysis');
                const factCheck = document.getElementById('fact-check');
                const sourceVerify = document.getElementById('source-verify');

                response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '' },
                    body: JSON.stringify({
                        content: content.value,
                        detailed: detailedAnalysis ? detailedAnalysis.checked : false,
                        factCheck: factCheck ? factCheck.checked : false,
                        sourceVerify: sourceVerify ? sourceVerify.checked : false
                    })
                });
            }

            clearInterval(progressInterval);
            updateLoadingProgress(100);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Analysis failed');
            }

            data = await response.json();

            if (data.source === 'scraping_failed') {
                clearInterval(progressInterval);
                showLoading(false);
                showToast(data.error || 'Failed to extract article from URL', 'error');
                return;
            }

            setTimeout(async () => {
                showLoading(false);
                displayResult(data);

                if (AppState.preferences.auto_save_history) {
                    await saveToHistory();
                }

                updateStats();
                refreshHistory();

                showToast('Analysis complete!', 'success');
            }, 500);

        } catch (err) {
            console.error('Analysis error:', err);
            showLoading(false);
            showToast(err.message || 'AI Engine disconnected. Please try again.', 'error');
        }
    });
}

function displayResult(data) {
    const resultPanel = document.getElementById('detailed-result');
    const statusText = document.getElementById('status-text');
    const statusIcon = document.getElementById('status-icon');
    const statusContainer = document.getElementById('status-container');
    const confidenceBar = document.getElementById('confidence-bar');
    const confidenceValue = document.getElementById('confidence-value');
    const resultSummary = document.getElementById('result-summary');
    const resultIndicators = document.getElementById('result-indicators');

    if (!resultPanel) return;

    // Store current analysis
    AppState.currentAnalysis = data;

    // Update status
    const isReal = data.status === 'Real';
    const isUncertain = data.status === 'Uncertain';
    if (statusText) statusText.textContent = (data.status === 'Uncertain' ? 'UNCERTAIN' : data.status.toUpperCase()) + ' NEWS';
    if (statusContainer) {
        statusContainer.className = 'result-status ' + (isReal ? 'success' : (isUncertain ? 'warning' : 'danger'));
    }
    if (statusIcon) {
        statusIcon.className = 'fas ' + (isReal ? 'fa-check-circle' : (isUncertain ? 'fa-question-circle' : 'fa-times-circle'));
    }

    // Update confidence
    const confidence = data.confidence || 50;
    const showConfPref = localStorage.getItem('pref_show_confidence') !== 'false';
    const confSection = document.querySelector('.confidence-section');

    if (showConfPref) {
        if (confSection) confSection.style.display = 'block';
        if (confidenceBar) {
            confidenceBar.style.width = confidence + '%';
            confidenceBar.className = 'confidence-bar ' + (isReal ? 'success' : (isUncertain ? 'warning' : 'danger'));
        }
        if (confidenceValue) {
            confidenceValue.textContent = parseFloat(confidence).toFixed(1) + '%';
        }
    } else {
        if (confSection) confSection.style.display = 'none';
    }

    // BERT dual probability bars
    const bertSection = document.getElementById('bert-probs-section');
    if (data.fake_prob !== undefined && data.real_prob !== undefined && bertSection) {
        const realBar = document.getElementById('bert-real-bar');
        const fakeBar = document.getElementById('bert-fake-bar');
        const realVal = document.getElementById('bert-real-val');
        const fakeVal = document.getElementById('bert-fake-val');
        if (realBar) realBar.style.width = parseFloat(data.real_prob).toFixed(1) + '%';
        if (fakeBar) fakeBar.style.width = parseFloat(data.fake_prob).toFixed(1) + '%';
        if (realVal) realVal.textContent = parseFloat(data.real_prob).toFixed(1) + '%';
        if (fakeVal) fakeVal.textContent = parseFloat(data.fake_prob).toFixed(1) + '%';
        bertSection.style.display = 'block';
    } else if (bertSection) {
        bertSection.style.display = 'none';
    }

    // Article title for URL mode
    const titleEl = document.getElementById('result-article-title');
    if (titleEl) {
        if (data.article_title) {
            titleEl.textContent = '\uD83D\uDCF0 ' + data.article_title;
            titleEl.style.display = 'block';
        } else {
            titleEl.style.display = 'none';
        }
    }

    // Update summary
    if (resultSummary) {
        const displayConfidence = parseFloat(data.confidence).toFixed(1);
        resultSummary.textContent = data.summary || 'This content appears to be ' + data.status.toLowerCase() + ' with ' + displayConfidence + '% confidence.';
    }

    // Add indicators
    if (resultIndicators) {
        resultIndicators.innerHTML = generateIndicators(data);
    }

    // Show result panel with animation
    resultPanel.style.display = 'block';
    setTimeout(() => {
        resultPanel.classList.add('show');
    }, 10);

    // Scroll to result
    resultPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // Auto-save feature
    if (localStorage.getItem('pref_auto_save_history') === 'true') {
        setTimeout(() => { saveToHistory(); }, 500); // slight delay to ensure AppState is ready
    }
}

function generateIndicators(data) {
    const indicators = [
        { icon: 'fa-bullseye', label: 'Confidence', value: parseFloat(data.confidence).toFixed(2) + '%' },
        { icon: 'fa-language', label: 'Sentiment', value: data.sentiment || 'Neutral' },
        { icon: 'fa-tags', label: 'Subject', value: data.subject || 'General' },
        { icon: 'fa-link', label: 'Sources', value: data.sources || 'N/A' }
    ];

    if (data.detailed) {
        if (data.detailed.complexity) indicators.push({ icon: 'fa-microscope', label: 'Complexity', value: data.detailed.complexity });
        if (data.detailed.word_count) indicators.push({ icon: 'fa-file-alt', label: 'Word Count', value: data.detailed.word_count });
    }

    if (data.fake_prob !== undefined && data.real_prob !== undefined) {
        indicators.push({ icon: 'fa-check-circle', label: 'Real Prob', value: data.real_prob.toFixed(2) + '%' });
        indicators.push({ icon: 'fa-times-circle', label: 'Fake Prob', value: data.fake_prob.toFixed(2) + '%' });
        indicators.push({ icon: 'fa-brain', label: 'Model', value: 'BERT' });
    } else if (data.raw_prob !== undefined) {
        indicators.push({ icon: 'fa-microchip', label: 'Model Prob', value: data.raw_prob.toFixed(6) });
    }

    indicators.push({ icon: 'fa-clock', label: 'Analyzed', value: new Date().toLocaleTimeString() });

    return indicators.map(function (ind) {
        return '<div class="result-indicator"><i class="fas ' + ind.icon + '"></i><div><span class="indicator-label">' + ind.label + '</span><span class="indicator-value">' + ind.value + '</span></div></div>';
    }).join('');
}

// ============================================
// RESULT ACTIONS
// ============================================

async function saveToHistory() {
    if (!AppState.currentAnalysis) {
        showToast('No analysis to save', 'warning');
        return;
    }

    if (AppState.isSaved) {
        showToast('This analysis has already been auto-saved!', 'info');
        return;
    }

    // In URL mode use the scraped article title + content from the API response
    let savedContent;
    if (AppState.inputMode === 'url') {
        const title = AppState.currentAnalysis.article_title || '';
        const snippet = AppState.currentAnalysis.scraped_content || '';
        savedContent = title ? (title + (snippet ? ' — ' + snippet : '')) : snippet;
        if (!savedContent) {
            const urlInput = document.getElementById('news-url');
            savedContent = urlInput ? urlInput.value : '';
        }
    } else {
        const textEl = document.getElementById('news-content');
        savedContent = textEl ? textEl.value : '';
    }

    const historyItem = {
        content: savedContent,
        status: AppState.currentAnalysis.status,
        confidence: AppState.currentAnalysis.confidence,
        timestamp: new Date().toLocaleString(),
        summary: AppState.currentAnalysis.summary,
        sentiment: AppState.currentAnalysis.sentiment,
        subject: AppState.currentAnalysis.subject,
        sources: AppState.currentAnalysis.sources,
        fake_prob: AppState.currentAnalysis.fake_prob,
        real_prob: AppState.currentAnalysis.real_prob,
        detection_method: AppState.currentAnalysis.detection_method || 'bert_model'
    };

    return fetch('/save_history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '' },
        body: JSON.stringify(historyItem)
    })
        .then(function (response) { return response.json(); })
        .then(function (data) {
            if (data.success) {
                AppState.isSaved = true;
                showToast('Analysis saved to history!', 'success');
                updateStats();
                refreshHistory();
                refreshAnalytics();
            }
            return data;
        })
        .catch(function (err) {
            console.error('Save error:', err);
            showToast('Failed to save to history', 'error');
            throw err;
        });
}

function shareResult() {
    if (!AppState.currentAnalysis) {
        showToast('No analysis to share', 'warning');
        return;
    }

    const shareText = 'TruthGuard Analysis: ' + AppState.currentAnalysis.status + ' News (' + AppState.currentAnalysis.confidence + '% confidence)';

    if (navigator.share) {
        navigator.share({
            title: 'TruthGuard Analysis',
            text: shareText,
            url: window.location.href
        })
            .then(function () { showToast('Shared successfully!', 'success'); })
            .catch(function (err) {
                if (err.name !== 'AbortError') {
                    copyToClipboard(shareText);
                }
            });
    } else {
        copyToClipboard(shareText);
    }
}

function downloadReport() {
    if (!AppState.currentAnalysis) {
        showToast('No analysis to download', 'warning');
        return;
    }

    const content = document.getElementById('news-content');
    const report = {
        content: content ? content.value : '',
        analysis: AppState.currentAnalysis,
        timestamp: new Date().toISOString(),
        generatedBy: 'TruthGuard AI'
    };

    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'truthguard-report-' + Date.now() + '.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast('Report downloaded!', 'success');
}

// ============================================
// HISTORY MANAGEMENT
// ============================================

function loadHistory() {
    fetch('/get_history')
        .then(function (response) {
            if (response.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return response.json();
        })
        .then(function (data) {
            if (data && data.history) {
                AppState.history = data.history;
                renderHistory();
            }
        })
        .catch(function (err) {
            console.error('History load error:', err);
        });
}

function refreshHistory() {
    loadHistory();
    updateStats();
}

function renderHistory() {
    const historyList = document.getElementById('history-list');
    if (!historyList) return;

    if (AppState.history.length === 0) {
        historyList.innerHTML = '<div class="empty-state"><div class="empty-icon"><i class="fas fa-history"></i></div><h3>No History Yet</h3><p>Start by verifying some news articles!</p><button onclick="showTab(\'dashboard\')" class="btn-primary"><i class="fas fa-plus"></i> Start Analyzing</button></div>';
        return;
    }

    historyList.innerHTML = AppState.history.map(function (item, index) {
        return '<div class="history-card" data-status="' + item.status + '" data-confidence="' + item.confidence + '" data-content="' + item.content.toLowerCase() + '" data-date="' + item.timestamp + '"><div class="history-main"><div class="history-status-icon ' + (item.status === 'Real' ? 'success' : 'danger') + '"><i class="fas ' + (item.status === 'Real' ? 'fa-check' : 'fa-times') + '"></i></div><div class="history-content"><p class="history-text">' + item.content + '</p><div class="history-meta"><span><i class="fas fa-calendar"></i> ' + item.timestamp + '</span><span><i class="fas fa-chart-line"></i> ' + item.confidence + '% confidence</span></div></div></div><div class="history-actions"><span class="history-badge ' + (item.status === 'Real' ? 'success' : 'danger') + '">' + item.status + '</span><button class="btn-icon-small" onclick="viewDetails(' + index + ')" title="View Details"><i class="fas fa-eye"></i></button><button class="btn-icon-small" onclick="reanalyze(' + index + ')" title="Reanalyze"><i class="fas fa-redo"></i></button><button class="btn-icon-small" onclick="deleteItem(' + index + ')" title="Delete"><i class="fas fa-trash"></i></button></div></div>';
    }).join('');
}

function filterHistory() {
    const searchTerm = document.getElementById('history-search');
    const statusFilter = document.getElementById('filter-status');
    const confidenceFilter = document.getElementById('filter-confidence');
    const dateFilter = document.getElementById('filter-date');

    const searchValue = searchTerm ? searchTerm.value.toLowerCase() : '';
    const statusValue = statusFilter ? statusFilter.value : '';
    const confidenceValue = confidenceFilter ? confidenceFilter.value : '';
    const dateValue = dateFilter ? dateFilter.value : '';

    const cards = document.querySelectorAll('.history-card');

    cards.forEach(function (card) {
        const content = card.getAttribute('data-content') || '';
        const status = card.getAttribute('data-status') || '';
        const confidence = parseInt(card.getAttribute('data-confidence') || '0');
        const date = new Date(card.getAttribute('data-date') || '');

        let show = true;

        // Search filter
        if (searchValue && !content.includes(searchValue)) {
            show = false;
        }

        // Status filter
        if (statusValue && status !== statusValue) {
            show = false;
        }

        // Confidence filter
        if (confidenceValue) {
            if (confidenceValue === 'high' && confidence <= 80) show = false;
            if (confidenceValue === 'medium' && (confidence < 50 || confidence > 80)) show = false;
            if (confidenceValue === 'low' && confidence >= 50) show = false;
        }

        // Date filter
        if (dateValue) {
            const now = new Date();
            const daysDiff = Math.floor((now - date) / (1000 * 60 * 60 * 24));

            if (dateValue === 'today' && daysDiff > 0) show = false;
            if (dateValue === 'week' && daysDiff > 7) show = false;
            if (dateValue === 'month' && daysDiff > 30) show = false;
        }

        card.style.display = show ? 'flex' : 'none';
    });
}

function viewDetails(index) {
    const item = AppState.history[index];
    if (!item) return;

    const bertProbs = (item.real_prob !== undefined && item.fake_prob !== undefined)
        ? '<div class="modal-bert-probs">'
        + '<h4><i class="fas fa-brain"></i> BERT Model Probabilities</h4>'
        + '<div class="modal-prob-row"><span class="prob-real-label"><i class="fas fa-check-circle"></i> Real</span>'
        + '<div class="modal-prob-track"><div class="modal-prob-fill real" style="width:' + parseFloat(item.real_prob).toFixed(1) + '%"></div></div>'
        + '<span class="prob-num">' + parseFloat(item.real_prob).toFixed(1) + '%</span></div>'
        + '<div class="modal-prob-row"><span class="prob-fake-label"><i class="fas fa-times-circle"></i> Fake</span>'
        + '<div class="modal-prob-track"><div class="modal-prob-fill fake" style="width:' + parseFloat(item.fake_prob).toFixed(1) + '%"></div></div>'
        + '<span class="prob-num">' + parseFloat(item.fake_prob).toFixed(1) + '%</span></div>'
        + '</div>'
        : '';

    showModal({
        title: 'Analysis Details',
        content: '<div class="modal-detail">'
            + '<h4>Content:</h4><p>' + item.content + '</p>'
            + '<h4>Status:</h4><p class="' + (item.status === 'Real' ? 'text-success' : 'text-danger') + '">' + item.status + '</p>'
            + '<h4>Confidence:</h4><p>' + parseFloat(item.confidence).toFixed(1) + '%</p>'
            + bertProbs
            + '<h4>Sentiment:</h4><p>' + (item.sentiment || 'Neutral') + '</p>'
            + '<h4>Subject:</h4><p>' + (item.subject || 'General') + '</p>'
            + '<h4>Sources:</h4><p>' + (item.sources || 'None Detected') + '</p>'
            + '<h4>Timestamp:</h4><p>' + item.timestamp + '</p>'
            + (item.summary ? '<h4>Summary:</h4><p>' + item.summary + '</p>' : '')
            + '</div>',
        buttons: [
            { text: 'Close', class: 'btn-secondary', action: 'close' }
        ]
    });
}

function reanalyze(index) {
    const item = AppState.history[index];
    if (!item) return;

    showTab('dashboard');
    setTimeout(function () {
        const textarea = document.getElementById('news-content');
        if (textarea) {
            textarea.value = item.content;
            const form = document.getElementById('check-form');
            if (form) form.dispatchEvent(new Event('submit'));
        }
    }, 100);
}

function deleteItem(index) {
    showModal({
        title: 'Confirm Deletion',
        content: '<p>Are you sure you want to delete this item?</p>',
        buttons: [
            { text: 'Cancel', class: 'btn-secondary', action: 'close' },
            {
                text: 'Delete',
                class: 'btn-danger',
                action: function () {
                    fetch('/delete_history/' + index, { method: 'DELETE' })
                        .then(function (response) { return response.json(); })
                        .then(function (data) {
                            if (data.success) {
                                showToast('Item deleted', 'success');
                                refreshHistory();
                            }
                        })
                        .catch(function (err) {
                            console.error('Delete error:', err);
                            showToast('Failed to delete item', 'error');
                        });
                }
            }
        ]
    });
}

function exportHistory() {
    if (AppState.history.length === 0) {
        showToast('No history to export', 'warning');
        return;
    }

    const data = {
        exported: new Date().toISOString(),
        totalItems: AppState.history.length,
        history: AppState.history
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'truthguard-history-' + Date.now() + '.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast('History exported successfully!', 'success');
}

function clearHistory() {
    showModal({
        title: 'Clear All History',
        content: '<p>Are you sure you want to clear all history? This action cannot be undone.</p>',
        buttons: [
            { text: 'Cancel', class: 'btn-secondary', action: 'close' },
            {
                text: 'Clear All',
                class: 'btn-danger',
                action: function () {
                    fetch('/clear_history', { method: 'POST' })
                        .then(function (response) { return response.json(); })
                        .then(function (data) {
                            if (data.success) {
                                showToast('History cleared!', 'success');
                                refreshHistory();
                            }
                        })
                        .catch(function (err) {
                            console.error('Clear error:', err);
                            showToast('Failed to clear history', 'error');
                        });
                }
            }
        ]
    });
}

// ============================================
// CHARTS
// ============================================

function initializeCharts() {
    // Distribution Chart
    const reliabilityCtx = document.getElementById('reliabilityChart');
    if (reliabilityCtx) {
        AppState.charts.reliability = new Chart(reliabilityCtx, {
            type: 'doughnut',
            data: {
                labels: ['Real', 'Fake'],
                datasets: [{
                    data: [0, 0],
                    backgroundColor: [chartColors.real, chartColors.fake],
                    borderWidth: 0,
                    hoverOffset: 8
                }]
            },
            options: {
                cutout: '75%',
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1
                    }
                },
                animation: {
                    animateRotate: true,
                    animateScale: true
                }
            }
        });
    }
}

function initAnalyticsCharts() {
    const chartDataEl = document.getElementById('chart-data');
    let activityData = [2, 4, 3, 5, 2, 4, 3];
    let realTrend = [5, 8, 6, 10];
    let fakeTrend = [2, 3, 4, 2];
    let highConf = 60;
    let medConf = 30;
    let lowConf = 10;
    let activityLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

    if (chartDataEl) {
        const activityAttr = chartDataEl.getAttribute('data-activity-data');
        const realTrendAttr = chartDataEl.getAttribute('data-real-trend');
        const fakeTrendAttr = chartDataEl.getAttribute('data-fake-trend');
        const highConfAttr = chartDataEl.getAttribute('data-high-confidence');
        const medConfAttr = chartDataEl.getAttribute('data-med-confidence');
        const lowConfAttr = chartDataEl.getAttribute('data-low-confidence');
        const labelsAttr = chartDataEl.getAttribute('data-activity-labels');

        if (activityAttr) {
            try { activityData = JSON.parse(activityAttr); } catch (e) { }
        }
        if (realTrendAttr) {
            try { realTrend = JSON.parse(realTrendAttr); } catch (e) { }
        }
        if (fakeTrendAttr) {
            try { fakeTrend = JSON.parse(fakeTrendAttr); } catch (e) { }
        }
        if (highConfAttr) highConf = parseInt(highConfAttr);
        if (medConfAttr) medConf = parseInt(medConfAttr);
        if (lowConfAttr) lowConf = parseInt(lowConfAttr);
        if (labelsAttr) {
            try { activityLabels = JSON.parse(labelsAttr); } catch (e) { }
        }
    }

    if (activityData.length === 0) activityData = [0, 0, 0, 0, 0, 0, 0];
    if (realTrend.length === 0) realTrend = [0, 0, 0, 0];
    if (fakeTrend.length === 0) fakeTrend = [0, 0, 0, 0];

    const totalConf = highConf + medConf + lowConf;
    if (totalConf === 0) {
        highConf = 60;
        medConf = 30;
        lowConf = 10;
    }

    // Activity Chart
    const activityCtx = document.getElementById('activityChart');
    if (activityCtx) {
        if (AppState.charts.activity) {
            AppState.charts.activity.destroy();
        }
        AppState.charts.activity = new Chart(activityCtx, {
            type: 'line',
            data: {
                labels: activityLabels,
                datasets: [{
                    label: 'Checks',
                    data: activityData,
                    borderColor: chartColors.primary,
                    backgroundColor: 'rgba(210, 81, 118, 0.1)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(0,0,0,0.05)' },
                        ticks: { precision: 0 }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    }

    // Trends Chart
    const trendsCtx = document.getElementById('trendsChart');
    if (trendsCtx) {
        if (AppState.charts.trends) {
            AppState.charts.trends.destroy();
        }
        AppState.charts.trends = new Chart(trendsCtx, {
            type: 'bar',
            data: {
                labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
                datasets: [{
                    label: 'Real',
                    data: realTrend,
                    backgroundColor: chartColors.real
                }, {
                    label: 'Fake',
                    data: fakeTrend,
                    backgroundColor: chartColors.fake
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { usePointStyle: true, padding: 15 }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(0,0,0,0.05)' },
                        ticks: { precision: 0 }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    }

    // Confidence Chart
    const confidenceCtx = document.getElementById('confidenceChart');
    if (confidenceCtx) {
        if (AppState.charts.confidence) {
            AppState.charts.confidence.destroy();
        }
        AppState.charts.confidence = new Chart(confidenceCtx, {
            type: 'doughnut',
            data: {
                labels: ['High (>90%)', 'Medium (70-90%)', 'Low (<70%)'],
                datasets: [{
                    data: [highConf, medConf, lowConf],
                    backgroundColor: [chartColors.real, chartColors.accent, chartColors.fake],
                    borderWidth: 0,
                    hoverOffset: 6
                }]
            },
            options: {
                cutout: '60%',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { usePointStyle: true, font: { size: 11 }, padding: 12 }
                    }
                }
            }
        });
    }
}

function refreshChart(chartName) {
    showToast('Refreshing chart...', 'info');
    updateStats();
    refreshAnalytics();
}

function refreshAnalytics() {
    fetch('/get_analytics?range=' + AppState.dateRange)
        .then(function (response) {
            if (response.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return response.json();
        })
        .then(function (data) {
            if (data && data.success) {
                updateAnalyticsCharts(data);
                updateAnalyticsStats(data);
            }
        })
        .catch(function (err) {
            console.error('Analytics refresh error:', err);
        });
}

function updateChartData() {
    if (AppState.charts.reliability) {
        fetch('/get_stats')
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data && data.success) {
                    AppState.charts.reliability.data.datasets[0].data = [data.real_count, data.fake_count];
                    AppState.charts.reliability.update();
                }
            })
            .catch(function (err) {
                console.error('Chart update error:', err);
            });
    }
}

// ============================================
// STATS UPDATE
// ============================================

function updateStats() {
    fetch('/get_stats')
        .then(function (response) {
            if (response.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return response.json();
        })
        .then(function (data) {
            if (!data || !data.success) return;

            // Update main stats
            updateElement('total-checks', data.total_checks);
            updateElement('real-count', data.real_count);
            updateElement('fake-count', data.fake_count);
            updateElement('avg-confidence', data.avg_confidence + '%');
            updateElement('real-percentage', data.real_percentage + '%');
            updateElement('fake-percentage', data.fake_percentage + '%');

            // Update sidebar stats
            updateElement('sidebar-real-count', data.real_count);
            updateElement('sidebar-fake-count', data.fake_count);

            // Update chart
            updateElement('chart-total', data.total_checks);
            updateElement('legend-real', data.real_count);
            updateElement('legend-fake', data.fake_count);

            // Update badge
            updateElement('nav-dashboard-badge', data.total_checks);

            // Update charts
            updateChartData();
        })
        .catch(function (err) {
            console.error('Stats update error:', err);
        });
}

function updateElement(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = value;
    }
}

// ============================================
// BATCH ANALYSIS
// ============================================

function setupBatchAnalysis() {
    const uploadZone = document.getElementById('batch-upload-zone');
    const fileInput = document.getElementById('batch-file-input');

    if (uploadZone) {
        uploadZone.addEventListener('click', function () {
            if (fileInput) fileInput.click();
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', handleBatchUpload);
    }
}

function setupDragAndDrop() {
    const uploadZone = document.getElementById('batch-upload-zone');
    if (!uploadZone) return;

    uploadZone.addEventListener('dragover', function (e) {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });

    uploadZone.addEventListener('dragleave', function () {
        uploadZone.classList.remove('dragover');
    });

    uploadZone.addEventListener('drop', function (e) {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        const files = e.dataTransfer.files;
        processBatchFiles(files);
    });
}

function handleBatchUpload(event) {
    const files = event.target.files;
    processBatchFiles(files);
}

async function processBatchFiles(files) {
    if (!files || files.length === 0) return;

    const batchResults = document.getElementById('batch-results');
    const batchList = document.getElementById('batch-list');

    if (batchResults) batchResults.style.display = 'block';
    if (batchList) batchList.innerHTML = '';

    const items = [];

    for (let i = 0; i < files.length; i++) {
        const content = await readFileContent(files[i]);
        items.push({ content: content, filename: files[i].name });
    }

    let completed = 0;
    const total = items.length;

    for (let i = 0; i < items.length; i++) {
        try {
            const response = await fetch('/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '' },
                body: JSON.stringify({ content: items[i].content })
            });

            const result = await response.json();
            addBatchResult(items[i].filename, result);

            completed++;
            updateBatchProgress(completed, total);
        } catch (err) {
            console.error('Batch analysis error:', err);
            addBatchResult(items[i].filename, { status: 'Error', confidence: 0 });
            completed++;
            updateBatchProgress(completed, total);
        }
    }

    showToast('Batch analysis complete!', 'success');
}

function readFileContent(file) {
    return new Promise(function (resolve, reject) {
        const reader = new FileReader();
        reader.onload = function (e) { resolve(e.target.result); };
        reader.onerror = reject;
        reader.readAsText(file);
    });
}

function addBatchResult(filename, result) {
    const batchList = document.getElementById('batch-list');
    if (!batchList) return;

    const item = document.createElement('div');
    item.className = 'batch-item';
    item.innerHTML = '<div class="batch-item-icon ' + (result.status === 'Real' ? 'success' : 'danger') + '"><i class="fas ' + (result.status === 'Real' ? 'fa-check' : 'fa-times') + '"></i></div><div class="batch-item-content"><span class="batch-item-name">' + filename + '</span><span class="batch-item-status">' + result.status + ' - ' + result.confidence + '%</span></div>';
    batchList.appendChild(item);
}

function updateBatchProgress(completed, total) {
    const progressFill = document.getElementById('batch-progress-fill');
    const progressText = document.getElementById('batch-progress-text');

    const percentage = (completed / total) * 100;

    if (progressFill) progressFill.style.width = percentage + '%';
    if (progressText) progressText.textContent = completed + ' / ' + total;
}

// ============================================
// SETTINGS & PREFERENCES
// ============================================

function loadPreferences() {
    fetch('/get_settings')
        .then(function (response) {
            if (response.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return response.json();
        })
        .then(function (data) {
            if (data && data.success) {
                applyUserSettings(data);
            }
        })
        .catch(function (err) {
            console.error('Error loading settings:', err);
        });
}

function applyUserSettings(data) {
    if (!data.user) return;

    const nameEl = document.getElementById('setting-name');
    const emailEl = document.getElementById('setting-email');
    const phoneEl = document.getElementById('setting-phone');
    const countryEl = document.getElementById('setting-country');

    if (nameEl) nameEl.value = data.user.name || '';
    if (emailEl) emailEl.value = data.user.email || '';
    if (phoneEl) phoneEl.value = data.user.phone || '';
    if (countryEl) countryEl.value = data.user.country || '';

    if (data.preferences) {
        AppState.preferences = {
            email: data.preferences.email_notifications || false,
            dark: data.preferences.dark_mode || false,
            autosave: data.preferences.auto_save_history || false,
            confidence: data.preferences.show_confidence || false
        };

        const prefEmail = document.getElementById('pref-email');
        const prefDark = document.getElementById('pref-dark');
        const prefAutosave = document.getElementById('pref-autosave');
        const prefConfidence = document.getElementById('pref-confidence');

        if (prefEmail) prefEmail.checked = data.preferences.email_notifications !== false;
        if (prefDark) prefDark.checked = data.preferences.dark_mode === true;
        if (prefAutosave) prefAutosave.checked = data.preferences.auto_save_history !== false;
        if (prefConfidence) prefConfidence.checked = data.preferences.show_confidence !== false;

        if (data.preferences.dark_mode) {
            document.body.classList.add('dark-mode');
        }
    }
}

function savePreference(key, value) {
    const preferenceKeyMap = {
        'email_notifications': 'email',
        'dark_mode': 'dark',
        'auto_save_history': 'autosave',
        'show_confidence': 'confidence'
    };

    AppState.preferences[preferenceKeyMap[key] || key] = value;

    const backendPrefs = {
        email_notifications: document.getElementById('pref-email').checked,
        dark_mode: document.getElementById('pref-dark').checked,
        auto_save_history: document.getElementById('pref-autosave').checked,
        show_confidence: document.getElementById('pref-confidence').checked
    };

    fetch('/save_preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '' },
        body: JSON.stringify({ preferences: backendPrefs })
    })
        .then(function (response) { return response.json(); })
        .then(function (data) {
            if (data.success) {
                localStorage.setItem('preferences', JSON.stringify(AppState.preferences));
                showToast('Preference saved', 'success');
            }
        })
        .catch(function (err) {
            console.error('Error saving preference:', err);
            localStorage.setItem('preferences', JSON.stringify(AppState.preferences));
            showToast('Preference saved locally', 'info');
        });
}

function applyPreferences() {
    Object.keys(AppState.preferences).forEach(function (key) {
        const checkbox = document.getElementById('pref-' + key);
        if (checkbox) {
            checkbox.checked = AppState.preferences[key];
        }
    });

    if (AppState.preferences.dark) {
        document.body.classList.add('dark-mode');
    }
}

function toggleDarkMode(enabled) {
    document.body.classList.toggle('dark-mode', enabled);
    savePreference('dark_mode', enabled);
    showToast(enabled ? 'Dark mode enabled' : 'Dark mode disabled', 'info');
}

function setDateRange(range) {
    AppState.dateRange = range;

    document.querySelectorAll('.range-btn').forEach(function (btn) {
        btn.classList.remove('active');
    });

    const activeBtn = document.querySelector('.range-btn[data-range="' + range + '"]');
    if (activeBtn) {
        activeBtn.classList.add('active');
    }

    fetch('/get_analytics?range=' + range)
        .then(function (response) {
            if (response.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return response.json();
        })
        .then(function (data) {
            if (data && data.success) {
                updateAnalyticsCharts(data);
                updateAnalyticsStats(data);
            }
        })
        .catch(function (err) {
            console.error('Error fetching analytics:', err);
            showToast('Failed to load analytics data', 'error');
        });
}

function updateAnalyticsCharts(data) {
    const labels = AppState.dateRange === '7days'
        ? ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        : (AppState.dateRange === '30days'
            ? Array.from({ length: 30 }, (_, i) => (i + 1).toString())
            : ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']);

    if (AppState.charts.activity) {
        AppState.charts.activity.data.labels = labels;
        AppState.charts.activity.data.datasets[0].data = data.activity_data || [0, 0, 0, 0, 0, 0, 0];
        AppState.charts.activity.update();
    }

    if (AppState.charts.trends) {
        AppState.charts.trends.data.datasets[0].data = data.real_trend || [0, 0, 0, 0];
        AppState.charts.trends.data.datasets[1].data = data.fake_trend || [0, 0, 0, 0];
        AppState.charts.trends.update();
    }

    if (AppState.charts.confidence) {
        const totalConf = (data.high_confidence || 0) + (data.med_confidence || 0) + (data.low_confidence || 0);
        if (totalConf > 0) {
            AppState.charts.confidence.data.datasets[0].data = [
                data.high_confidence || 0,
                data.med_confidence || 0,
                data.low_confidence || 0
            ];
            AppState.charts.confidence.update();
        }
    }
}

function updateAnalyticsStats(data) {
    if (!data) return;

    const trustScoreEl = document.getElementById('trust-score-value');
    if (trustScoreEl) {
        trustScoreEl.textContent = data.trust_score + '%';
        const parent = trustScoreEl.closest('.analytics-stat-card');
        if (parent) {
            const progressBar = parent.querySelector('.progress-bar');
            if (progressBar) {
                progressBar.style.width = data.trust_score + '%';
            }
        }
    }

    const fakeRateEl = document.getElementById('fake-rate-value');
    if (fakeRateEl) {
        fakeRateEl.textContent = data.fake_percentage + '%';
        const parent = fakeRateEl.closest('.analytics-stat-card');
        if (parent) {
            const progressBar = parent.querySelector('.progress-bar');
            if (progressBar) {
                progressBar.style.width = data.fake_percentage + '%';
            }
        }
    }

    const accuracyEl = document.getElementById('accuracy-value');
    if (accuracyEl) {
        accuracyEl.textContent = data.avg_confidence + '%';
        const parent = accuracyEl.closest('.analytics-stat-card');
        if (parent) {
            const progressBar = parent.querySelector('.progress-bar');
            if (progressBar) {
                progressBar.style.width = data.avg_confidence + '%';
            }
        }
    }

    const rankEl = document.getElementById('rank-value');
    if (rankEl) {
        rankEl.textContent = 'Top ' + (100 - data.user_rank_percentile) + '%';
    }

    const activeDayEl = document.getElementById('active-day');
    if (activeDayEl) {
        activeDayEl.textContent = data.most_active_day || 'N/A';
    }

    const peakHourEl = document.getElementById('peak-hour');
    if (peakHourEl) {
        peakHourEl.textContent = (data.most_active_hour || 12) + ':00';
    }

    const streakEl = document.getElementById('streak');
    if (streakEl) {
        streakEl.textContent = (data.streak_days || 0) + ' days';
    }

    const platformAvgEl = document.getElementById('platform-avg');
    if (platformAvgEl) {
        platformAvgEl.textContent = (data.platform_avg_checks || 0) + ' checks';
    }
}

// ============================================
// SECURITY FUNCTIONS
// ============================================

function openPasswordModal() {
    showModal({
        title: 'Change Password',
        content: '<form id="password-form" class="modal-form"><div class="form-group"><label>Current Password</label><input type="password" id="current-password" required></div><div class="form-group"><label>New Password</label><input type="password" id="new-password" required></div><div class="form-group"><label>Confirm Password</label><input type="password" id="confirm-password" required></div></form>',
        buttons: [
            { text: 'Cancel', class: 'btn-secondary', action: 'close' },
            {
                text: 'Update Password',
                class: 'btn-primary',
                action: function () {
                    const currentPassword = document.getElementById('current-password').value;
                    const newPassword = document.getElementById('new-password').value;
                    const confirmPassword = document.getElementById('confirm-password').value;
                    const form = document.getElementById('password-form');

                    if (!form.checkValidity()) {
                        form.reportValidity();
                        return false;
                    }

                    if (newPassword !== confirmPassword) {
                        showToast('Passwords do not match', 'error');
                        return false;
                    }

                    if (newPassword.length < 6) {
                        showToast('Password must be at least 6 characters', 'error');
                        return false;
                    }

                    fetch('/change_password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '' },
                        body: JSON.stringify({
                            current_password: currentPassword,
                            new_password: newPassword
                        })
                    })
                        .then(function (response) { return response.json(); })
                        .then(function (data) {
                            if (data.success) {
                                showToast('Password updated successfully!', 'success');
                            } else {
                                showToast(data.message || 'Failed to change password', 'error');
                                return false;
                            }
                        })
                        .catch(function (err) {
                            console.error('Error changing password:', err);
                            showToast('Failed to change password', 'error');
                            return false;
                        });
                }
            }
        ]
    });
}

function enable2FA() {
    showModal({
        title: 'Enable Two-Factor Authentication',
        content: '<p>Scan the QR code with your authenticator app.</p><div class="qr-placeholder" style="text-align: center; padding: 20px; background: #f5f5f5; border-radius: 8px; margin: 15px 0;"><i class="fas fa-qrcode" style="font-size: 100px; color: #333;"></i></div><p style="text-align: center; color: #666;">Two-factor authentication adds an extra layer of security to your account.</p>',
        buttons: [
            { text: 'Cancel', class: 'btn-secondary', action: 'close' },
            { text: 'Enable', class: 'btn-primary', action: function () { showToast('2FA feature coming soon!', 'info'); } }
        ]
    });
}

function viewLoginHistory() {
    showModal({
        title: 'Login History',
        content: '<div class="login-history-list"><div class="login-item" style="display: flex; align-items: center; gap: 15px; padding: 12px; border-bottom: 1px solid #eee;"><i class="fas fa-desktop" style="font-size: 24px; color: #4CAF50;"></i><div><strong style="display: block;">Desktop - Chrome</strong><span style="color: #666; font-size: 13px;">Today at 10:30 AM</span></div></div><div class="login-item" style="display: flex; align-items: center; gap: 15px; padding: 12px; border-bottom: 1px solid #eee;"><i class="fas fa-mobile" style="font-size: 24px; color: #2196F3;"></i><div><strong style="display: block;">Mobile - Safari</strong><span style="color: #666; font-size: 13px;">Yesterday at 3:45 PM</span></div></div><div class="login-item" style="display: flex; align-items: center; gap: 15px; padding: 12px;"><i class="fas fa-laptop" style="font-size: 24px; color: #9C27B0;"></i><div><strong style="display: block;">Desktop - Firefox</strong><span style="color: #666; font-size: 13px;">3 days ago</span></div></div></div>',
        buttons: [{ text: 'Close', class: 'btn-secondary', action: 'close' }]
    });
}

function manageSessions() {
    showToast('Session management coming soon!', 'info');
}

function exportAllData() {
    fetch('/export_user_data')
        .then(function (response) { return response.json(); })
        .then(function (result) {
            if (result.success) {
                const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'truthguard-data-' + Date.now() + '.json';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                showToast('Data exported successfully!', 'success');
            } else {
                const userName = document.getElementById('setting-name');
                const data = {
                    exported: new Date().toISOString(),
                    user: userName ? userName.value : '',
                    history: AppState.history,
                    preferences: AppState.preferences
                };
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'truthguard-data-' + Date.now() + '.json';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                showToast('Data exported successfully!', 'success');
            }
        })
        .catch(function (err) {
            console.error('Export error:', err);
            showToast('Failed to export data', 'error');
        });
}


function confirmDeleteAccount() {
    showModal({
        title: 'Delete Account',
        content: '<p class="text-danger"><strong>Warning:</strong> This action is permanent and cannot be undone. All your data will be deleted.</p><p>Type "DELETE" to confirm:</p><input type="text" id="delete-confirm" class="form-control">',
        buttons: [
            { text: 'Cancel', class: 'btn-secondary', action: 'close' },
            {
                text: 'Delete Account',
                class: 'btn-danger',
                action: function () {
                    const input = document.getElementById('delete-confirm');
                    if (input && input.value === 'DELETE') {
                        fetch('/delete_account', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '' }
                        })
                            .then(function (response) { return response.json(); })
                            .then(function (data) {
                                if (data.success) {
                                    showToast('Account deleted successfully', 'success');
                                    window.location.href = '/login';
                                } else {
                                    showToast('Failed to delete account', 'error');
                                }
                            })
                            .catch(function (err) {
                                console.error('Delete account error:', err);
                                showToast('Failed to delete account', 'error');
                            });
                    } else {
                        showToast('Please type DELETE to confirm', 'error');
                        return false;
                    }
                }
            }
        ]
    });
}

// ============================================
// UI UTILITIES
// ============================================

function showLoading(show) {
    const overlay = document.getElementById('analysis-loading');
    if (overlay) {
        overlay.style.display = show ? 'flex' : 'none';
    }
}

function updateLoadingProgress(percent) {
    const bar = document.getElementById('loading-progress-bar');
    if (bar) {
        bar.style.width = percent + '%';
    }

    const subtexts = [
        'Scanning for patterns...',
        'Analyzing language structure...',
        'Checking credibility indicators...',
        'Comparing with known sources...',
        'Finalizing analysis...'
    ];

    const index = Math.min(Math.floor(percent / 20), subtexts.length - 1);
    const subtext = document.getElementById('loading-subtext');
    if (subtext) {
        subtext.textContent = subtexts[index];
    }
}

function showToast(message, type) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-times-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.innerHTML = '<i class="fas ' + icons[type] + '"></i><span>' + message + '</span><button class="toast-close" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>';

    container.appendChild(toast);

    setTimeout(function () { toast.classList.add('show'); }, 10);
    setTimeout(function () {
        toast.classList.remove('show');
        setTimeout(function () { toast.remove(); }, 300);
    }, 3000);
}

function showModal(config) {
    const modalContainer = document.getElementById('modal-container');
    if (!modalContainer) return;

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = '<div class="modal-content"><div class="modal-header"><h3>' + config.title + '</h3><button class="modal-close" onclick="closeModal()"><i class="fas fa-times"></i></button></div><div class="modal-body">' + config.content + '</div><div class="modal-footer">' + config.buttons.map(function (btn, idx) {
        return '<button class="btn ' + btn.class + '" data-idx="' + idx + '">' + btn.text + '</button>';
    }).join('') + '</div></div>';

    modalContainer.innerHTML = '';
    modalContainer.appendChild(modal);

    // Add click handlers
    modal.querySelectorAll('.modal-footer button').forEach(function (btn, idx) {
        btn.addEventListener('click', function () {
            const action = config.buttons[idx].action;
            if (action === 'close') {
                closeModal();
            } else if (typeof action === 'function') {
                const result = action();
                if (result !== false) {
                    closeModal();
                }
            }
        });
    });

    setTimeout(function () { modal.classList.add('show'); }, 10);
}

function closeModal() {
    const modal = document.querySelector('.modal-overlay');
    if (modal) {
        modal.classList.remove('show');
        setTimeout(function () { modal.remove(); }, 300);
    }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text)
        .then(function () { showToast('Copied to clipboard!', 'success'); })
        .catch(function () { showToast('Failed to copy', 'error'); });
}

// ============================================
// AUTO-REFRESH & UPDATES
// ============================================

function startAutoRefresh() {
    setInterval(function () {
        updateStats();
        if (AppState.currentTab === 'analytics') {
            refreshAnalytics();
        }
    }, 30000);

    setInterval(updateGreeting, 60000);
}

function updateGreeting() {
    const hour = new Date().getHours();
    let greeting;

    if (hour < 12) greeting = 'Good Morning';
    else if (hour < 18) greeting = 'Good Afternoon';
    else greeting = 'Good Evening';

    const greetingEl = document.getElementById('greeting');
    if (greetingEl) {
        greetingEl.textContent = greeting;
    }
}

function checkNotifications() {
    // Placeholder for notification checking
    const count = 0;
    const dot = document.getElementById('notification-count');
    if (dot) {
        dot.style.display = count > 0 ? 'block' : 'none';
        dot.textContent = count;
    }
}

// (Duplicate mock definitions removed — the working API-connected
//  versions are defined earlier in this file)

// ============================================
// EVENT LISTENERS
// ============================================

function setupEventListeners() {
    // Global search
    const globalSearch = document.getElementById('global-search');
    if (globalSearch) {
        globalSearch.addEventListener('input', handleGlobalSearch);
    }

    // Notifications
    const notifBtn = document.getElementById('notifications-btn');
    if (notifBtn) {
        notifBtn.addEventListener('click', showNotifications);
    }

    // Profile form handler is already set up in the DOMContentLoaded block above.

    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboardShortcuts);
}

function handleGlobalSearch(e) {
    const query = e.target.value.toLowerCase();
    // Implement global search logic
    console.log('Searching for:', query);
}

function showNotifications() {
    showModal({
        title: 'Notifications',
        content: '<p>No new notifications</p>',
        buttons: [{ text: 'Close', class: 'btn-secondary', action: 'close' }]
    });
}

// handleProfileUpdate removed — profile save is handled by the
// DOMContentLoaded event listener that calls /save_profile API.

function handleKeyboardShortcuts(e) {
    // Ctrl/Cmd + K for search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const search = document.getElementById('global-search');
        if (search) search.focus();
    }

    // Ctrl/Cmd + N for new analysis
    if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        focusAnalyzer();
    }

    // ESC to close modal
    if (e.key === 'Escape') {
        closeModal();
    }
}

// ============================================
// EXPORT FOR GLOBAL ACCESS
// ============================================

window.TruthGuard = {
    showTab: showTab,
    toggleSidebar: toggleSidebar,
    focusAnalyzer: focusAnalyzer,
    clearText: clearText,
    pasteText: pasteText,
    uploadFile: uploadFile,
    handleFileUpload: handleFileUpload,
    newAnalysis: newAnalysis,
    saveToHistory: saveToHistory,
    shareResult: shareResult,
    downloadReport: downloadReport,
    filterHistory: filterHistory,
    viewDetails: viewDetails,
    reanalyze: reanalyze,
    deleteItem: deleteItem,
    exportHistory: exportHistory,
    clearHistory: clearHistory,
    refreshChart: refreshChart,
    savePreference: savePreference,
    toggleDarkMode: toggleDarkMode,
    setDateRange: setDateRange,
    openPasswordModal: openPasswordModal,
    enable2FA: enable2FA,
    viewLoginHistory: viewLoginHistory,
    manageSessions: manageSessions,
    exportAllData: exportAllData,
    confirmDeleteAccount: confirmDeleteAccount,
    updateStats: updateStats,
    initAnalyticsCharts: initAnalyticsCharts
};

console.log('TruthGuard Dashboard Loaded Successfully');
