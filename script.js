let currentGames = [];
let selectedGame = null;
let currentSettings = {};
let installInterval = null;
let isPaused = false;
let isBackground = false;

const translations = {
    fr: {
        library: "Bibliothèque", addGame: "➕ Ajouter un jeu", scan: "🔍 Scanner l'ordinateur",
        selectGame: "Sélectionne un jeu", noGame: "Aucun jeu sélectionné", settings: "Paramètres"
    },
    en: {
        library: "Library", addGame: "➕ Add a Game", scan: "🔍 Scan Computer",
        selectGame: "Select a game", noGame: "No game selected", settings: "Settings"
    }
};

function init() {
    if (window.pywebview && window.pywebview.api) {
        loadSettings(); loadGames();
    } else { setTimeout(init, 100); }
}

document.addEventListener('DOMContentLoaded', () => {
    init();
    window.addEventListener('click', (e) => {
        if (!e.target.closest('.dropdown')) {
            const dropdown = document.getElementById('game-options-dropdown');
            if (dropdown) dropdown.classList.remove('open');
        }
    });
});

function showCustomPopup(message, type = 'alert', defaultValue = '') {
    return new Promise((resolve) => {
        const overlay = document.getElementById('custom-popup');
        const textEl = document.getElementById('custom-popup-text');
        const progressContainer = document.getElementById('custom-popup-progress-container');
        const inputContainer = document.getElementById('custom-popup-input-container');
        const buttonsContainer = document.getElementById('custom-popup-buttons');

        textEl.textContent = message;
        progressContainer.innerHTML = '';
        inputContainer.innerHTML = ''; 
        buttonsContainer.innerHTML = '';
        let inputEl = null;

        if (type === 'installing') {
            progressContainer.innerHTML = `
                <div class="progress-box">
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" id="install-bar-fill"></div>
                    </div>
                    <div class="progress-text" id="install-txt-percent">0%</div>
                    <div class="install-controls-row">
                        <button onclick="togglePauseInstall()" id="btn-pause-install" class="btn">Pause ⏸️</button>
                        <button onclick="toggleBackgroundInstall()" id="btn-bg-install" class="btn">Arrière-plan ⚙️</button>
                    </div>
                </div>
            `;

            const btnCancel = document.createElement('button');
            btnCancel.className = 'btn';
            btnCancel.textContent = 'Annuler l\'installation';
            btnCancel.style.color = '#ef4444';
            btnCancel.onclick = async () => {
                btnCancel.disabled = true;
                btnCancel.textContent = 'Nettoyage...';
                
                // 1. Déclenche l'annulation Python
                await pywebview.api.cancel_install();
                
                // 2. Arrête la boucle de vérification
                if (installInterval) clearInterval(installInterval);
                
                // 3. Ferme l'overlay pour débloquer l'interface
                overlay.classList.remove('active');
                
                // 4. Informe l'utilisateur et actualise l'affichage
                showCustomPopup("Installation annulée et nettoyage effectué.", "alert");
                loadGames();
            };
            buttonsContainer.appendChild(btnCancel);

        } else if (type === 'prompt') {
            inputEl = document.createElement('input');
            inputEl.type = 'text'; inputEl.className = 'custom-popup-input';
            inputEl.value = defaultValue; inputContainer.appendChild(inputEl);
            setTimeout(() => inputEl.focus(), 50);

            const btnCancel = document.createElement('button');
            btnCancel.className = 'btn'; btnCancel.textContent = 'Annuler';
            btnCancel.onclick = () => { overlay.classList.remove('active'); resolve(null); };

            const btnOk = document.createElement('button');
            btnOk.className = 'btn'; btnOk.textContent = 'OK'; btnOk.style.color = '#10b981';
            btnOk.onclick = () => { overlay.classList.remove('active'); resolve(inputEl.value); };

            buttonsContainer.appendChild(btnCancel);
            buttonsContainer.appendChild(btnOk);

        } else {
            const btnCancel = document.createElement('button');
            btnCancel.className = 'btn'; btnCancel.textContent = 'Annuler';
            btnCancel.style.display = (type === 'alert') ? 'none' : 'inline-block';
            btnCancel.onclick = () => { overlay.classList.remove('active'); resolve(false); };

            const btnOk = document.createElement('button');
            btnOk.className = 'btn'; btnOk.textContent = 'OK'; btnOk.style.color = '#10b981';
            btnOk.onclick = () => { overlay.classList.remove('active'); resolve(true); };

            buttonsContainer.appendChild(btnCancel);
            buttonsContainer.appendChild(btnOk);
        }

        overlay.classList.add('active');
    });
}

async function togglePauseInstall() {
    const res = await pywebview.api.toggle_pause_install();
    isPaused = res.paused;
    const btn = document.getElementById('btn-pause-install');
    if (btn) btn.textContent = isPaused ? "Reprendre ▶️" : "Pause ⏸️";
}

async function toggleBackgroundInstall() {
    isBackground = !isBackground;
    await pywebview.api.set_execution_mode(isBackground);
    const btn = document.getElementById('btn-bg-install');
    if (btn) btn.textContent = isBackground ? "Premier plan 🚀" : "Arrière-plan ⚙️";
}

async function installGame(name) {
    isPaused = false;
    isBackground = false;
    await pywebview.api.install_game(name);
    
    showCustomPopup(`Extraction et installation de "${name}"...`, "installing");

    installInterval = setInterval(async () => {
        const prog = await pywebview.api.get_install_progress();
        const fill = document.getElementById('install-bar-fill');
        const txt = document.getElementById('install-txt-percent');

        if (fill && txt) {
            fill.style.width = prog.percent + '%';
            txt.textContent = prog.percent + '%';
        }

        if (prog.status === 'finished') {
            clearInterval(installInterval);
            document.getElementById('custom-popup').classList.remove('active');
            showCustomPopup("Installation terminée avec succès !", "alert");
            loadGames();
        } else if (prog.status === 'cancelled') {
            clearInterval(installInterval);
            document.getElementById('custom-popup').classList.remove('active');
            showCustomPopup("Installation annulée et dossier supprimé.", "alert");
            loadGames();
        } else if (prog.status === 'error') {
            clearInterval(installInterval);
            document.getElementById('custom-popup').classList.remove('active');
            showCustomPopup("Erreur : " + prog.message, "alert");
            loadGames();
        }
    }, 300);
}

async function loadSettings() {
    try {
        currentSettings = await pywebview.api.get_settings();
        applySettingsUI();
    } catch (e) { console.error("Erreur chargement paramètres:", e); }
}

function applySettingsUI() {
    if (!currentSettings) return;

    document.getElementById('setting-lang').value = currentSettings.lang || 'fr';
    document.getElementById('setting-theme').value = currentSettings.theme || 'dark';
    document.getElementById('setting-install-dir').value = currentSettings.install_dir || '';
    document.getElementById('setting-rar-dir').value = currentSettings.rar_scan_folder || '';
    document.getElementById('setting-autoscan').checked = !!currentSettings.auto_scan;
    
    const smoothTransitions = currentSettings.smooth_transitions !== false;
    const transitionCheckbox = document.getElementById('setting-transitions');
    if (transitionCheckbox) transitionCheckbox.checked = smoothTransitions;

    if (smoothTransitions) document.body.classList.add('smooth-transitions');
    else document.body.classList.remove('smooth-transitions');

    document.body.className = document.body.className.replace(/\b(dark-theme|light-theme|liquid-theme)\b/g, '');
    if (currentSettings.theme === 'light') document.body.classList.add('light-theme');
    else if (currentSettings.theme === 'liquid') document.body.classList.add('liquid-theme');
    else document.body.classList.add('dark-theme');

    const t = translations[currentSettings.lang || 'fr'] || translations.fr;
    document.getElementById('txt-library').textContent = t.library;
    document.getElementById('btn-add-game').textContent = t.addGame;
    document.getElementById('btn-scan').textContent = t.scan;
    document.getElementById('txt-settings-title').textContent = t.settings;
    if (!selectedGame) document.getElementById('game-title-display').textContent = t.selectGame;
}

async function saveCurrentSettings() {
    currentSettings = await pywebview.api.save_settings({
        lang: document.getElementById('setting-lang').value,
        theme: document.getElementById('setting-theme').value,
        install_dir: document.getElementById('setting-install-dir').value,
        rar_scan_folder: document.getElementById('setting-rar-dir').value,
        auto_scan: document.getElementById('setting-autoscan').checked,
        smooth_transitions: document.getElementById('setting-transitions').checked
    });
    applySettingsUI(); loadGames();
}

async function browseInstallFolder() {
    const f = await pywebview.api.select_install_folder();
    if (f) { document.getElementById('setting-install-dir').value = f; await saveCurrentSettings(); }
}

async function browseRarFolder() {
    const f = await pywebview.api.select_rar_folder();
    if (f) { document.getElementById('setting-rar-dir').value = f; await saveCurrentSettings(); }
}

function toggleSettingsModal(show) {
    const m = document.getElementById('settings-modal');
    if (m) show ? m.classList.add('active') : m.classList.remove('active');
}

async function loadGames() {
    try {
        currentGames = await pywebview.api.get_games();
        renderGames(currentGames);
    } catch (e) { console.error("Erreur:", e); }
}

function renderGames(games) {
    currentGames = games || [];
    const list = document.getElementById('games-list');
    if (!list) return;
    list.innerHTML = '';

    const categories = {};
    currentGames.forEach(g => {
        const cat = g.category || "Non classé";
        if (!categories[cat]) categories[cat] = [];
        categories[cat].push(g);
    });

    Object.keys(categories).sort().forEach(catName => {
        const section = document.createElement('div');
        section.innerHTML = `<div class="category-title">${catName}</div>`;
        const container = document.createElement('div');
        container.className = 'category-games';
        
        categories[catName].forEach(g => {
            const item = document.createElement('div');
            item.className = `game-item ${selectedGame && selectedGame.name === g.name ? 'active' : ''}`;
            item.innerHTML = `${g.icon_base64 ? `<img src="${g.icon_base64}" class="game-icon"/>` : '<div class="game-icon"></div>'}
                              <span class="game-title">${g.name}</span>`;
            item.onclick = () => { selectGame(g); };
            container.appendChild(item);
        });
        section.appendChild(container); list.appendChild(section);
    });

    if (selectedGame && currentGames.find(g => g.name === selectedGame.name)) selectGame(currentGames.find(g => g.name === selectedGame.name));
    else if (currentGames.length > 0) selectGame(currentGames[0]);
    else clearGameDetails();
}

function selectGame(game) {
    selectedGame = game;
    const bannerEl = document.getElementById('game-banner');
    if (bannerEl) bannerEl.style.backgroundImage = game.banner_base64 ? `url('${game.banner_base64}')` : 'none';
    
    document.getElementById('game-title-display').textContent = game.name;
    document.getElementById('game-options-dropdown').style.display = 'inline-block';

    const lastPlayedEl = document.getElementById('game-last-played');
    if (game.last_played) {
        lastPlayedEl.style.display = 'block';
        lastPlayedEl.textContent = `Dernière partie : ${game.last_played}`;
    } else {
        lastPlayedEl.style.display = 'none';
    }

    let actions = '';
    
    if (game.installed) {
        actions += `<button onclick="playGame('${escapeQuotes(game.name)}')" class="btn" style="color:#10b981; border-color:#10b981;">Jouer</button>`;
    } else {
        actions += `<button onclick="installGame('${escapeQuotes(game.name)}')" class="btn" style="color:#10b981; border-color:#10b981;">Installer</button>`;
    }
    
    if (game.has_rar) actions += `<button onclick="deleteGameRar('${escapeQuotes(game.name)}')" class="btn" style="color:#f59e0b; border-color:#f59e0b;">Supprimer Archive</button>`;
    actions += `<button onclick="removeGameFromList('${escapeQuotes(game.name)}')" class="btn">Retirer liste</button>`;
    if (game.installed && game.source !== 'installed') {
        actions += `<button onclick="uninstallGame('${escapeQuotes(game.name)}')" class="btn" style="color:#ef4444; border-color:#ef4444;">Désinstaller</button>`;
    }
    
    document.getElementById('game-actions').innerHTML = actions;

    document.querySelectorAll('.game-item').forEach(el => {
        if (el.textContent.trim() === game.name) el.classList.add('active'); else el.classList.remove('active');
    });
}

function toggleDropdown() { document.getElementById('game-options-dropdown').classList.toggle('open'); }
function openGameSettings() {
    if (!selectedGame) return;
    document.getElementById('game-options-dropdown').classList.remove('open');
    document.getElementById('gs-input-exepath').value = selectedGame.exe_path || '';
    document.getElementById('game-settings-modal').classList.add('active');
}
function toggleGameSettingsModal(show) { document.getElementById('game-settings-modal').classList[show?'add':'remove']('active'); }

async function browseCustomExe() {
    const res = await pywebview.api.select_custom_exe(selectedGame.name);
    if (res.status === "success") { document.getElementById('gs-input-exepath').value = res.exe_path; renderGames(res.games); }
}
async function linkCustomGameFolder() {
    const res = await pywebview.api.set_custom_game_folder(selectedGame.name);
    if (res.status === "success") { showCustomPopup(res.exe_found ? "Dossier associé !" : "Dossier associé (aucun .exe trouvé)", "alert"); renderGames(res.games); }
}
async function renameCurrentGame() {
    const newName = await showCustomPopup("Nouveau nom :", "prompt", selectedGame.name);
    if (newName && newName !== selectedGame.name) {
        const res = await pywebview.api.rename_game(selectedGame.name, newName.trim());
        if (res.status === "success") renderGames(res.games);
    }
}
async function changeCategoryPrompt() {
    const newCat = await showCustomPopup("Catégorie :", "prompt", selectedGame.category || "Non classé");
    if (newCat !== null) {
        const res = await pywebview.api.set_game_category(selectedGame.name, newCat.trim() || "Non classé");
        if (res.status === "success") renderGames(res.games);
    }
}
async function changeImage(imgType) {
    const res = await pywebview.api.set_game_image(selectedGame.name, imgType);
    if (res.status === "success") renderGames(res.games);
}
async function triggerAutoImages() {
    const res = await pywebview.api.fetch_steamgriddb_images(selectedGame.name);
    if (res.status === "success") renderGames(res.games); else showCustomPopup("Erreur : " + res.message, "alert");
}

function escapeQuotes(str) { return str.replace(/'/g, "\\'"); }
async function deleteGameRar(name) {
    if (await showCustomPopup(`Supprimer l'archive de "${name}" ?`, "confirm")) {
        const res = await pywebview.api.delete_game_rar(name);
        if (res.status === "success") renderGames(res.games);
    }
}
async function removeGameFromList(name) {
    if (await showCustomPopup(`Retirer "${name}" de la liste ?`, "confirm")) {
        const res = await pywebview.api.delete_game_from_list(name);
        if (res.status === "success") { selectedGame = null; renderGames(res.games); }
    }
}
async function playGame(name) {
    const res = await pywebview.api.play_game(name);
    if (res.status === "error") {
        showCustomPopup(res.message, "alert");
    } else {
        loadGames();
    }
}

async function uninstallGame(name) {
    if (await showCustomPopup(`Désinstaller "${name}" ?`, "confirm")) {
        const res = await pywebview.api.uninstall_game(name);
        if (res.status === "success") loadGames();
    }
}

async function scanGames() {
    showCustomPopup("Scan en cours...", "alert"); 
    const res = await pywebview.api.scan_installed_games();
    renderGames(res);
}

async function addGameArchive() {
    const updated = await pywebview.api.add_game_dialog();
    if (updated) renderGames(updated);
}
function clearGameDetails() {
    selectedGame = null;
    document.getElementById('game-title-display').textContent = translations[currentSettings.lang || 'fr'].noGame;
    document.getElementById('game-actions').innerHTML = '';
    document.getElementById('game-banner').style.backgroundImage = 'none';
    document.getElementById('game-options-dropdown').style.display = 'none';
    document.getElementById('game-last-played').style.display = 'none';
}