import os
import sys
import json
import subprocess
import shutil
import base64
import mimetypes
import urllib.request
import urllib.parse
import re
import webview
import time
import zipfile
import tarfile
import threading
import psutil
import stat

try:
    import patoolib
    HAS_PATOOL = True
except ImportError:
    HAS_PATOOL = False

DEFAULT_INSTALL_FOLDER = os.path.join(os.path.expanduser("~"), "Documents", "CrackInstallerGames")
DATA_FILE = os.path.join(os.path.expanduser("~"), "steam_library_save.json")
DEFAULT_SGDB_KEY = "d3c4056d553717be351c140815af1bb0"

window = None

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def clean_game_name(raw_name):
    name = re.sub(r'\([^)]*\)|\[[^\]]*\]', '', raw_name)
    name = re.split(r'\b(by|-)\b', name, flags=re.IGNORECASE)[0]
    return name.strip(' -_')

def get_dir_size(folder_path):
    """Calcule la taille totale du dossier en octets."""
    total_size = 0
    if not os.path.exists(folder_path):
        return 0
    for root, _, files in os.walk(folder_path):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.exists(fp):
                try:
                    total_size += os.path.getsize(fp)
                except Exception:
                    pass
    return total_size

def find_extractor_executable():
    """Détecte WinRAR, 7-Zip ou NanaZip installés sur le système."""
    candidates = [
        r"C:\Program Files\WinRAR\WinRAR.exe",
        r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"C:\Program Files\WindowsApps\NanaZip.exe",
        r"C:\Program Files\NanaZip\NanaZip.exe",
        r"C:\Program Files\NanaZip\nana-zip.exe"
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    
    for tool in ["winrar", "7z", "nanazip", "nana-zip"]:
        exe = shutil.which(tool)
        if exe:
            return exe
    return None

def estimate_uncompressed_size(archive_path):
    """Calcule ou estime la taille décompressée du fichier."""
    ext = os.path.splitext(archive_path)[1].lower()
    if ext == '.zip':
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                return sum(file.file_size for file in zf.infolist())
        except Exception:
            pass
    return int(os.path.getsize(archive_path) * 2.5)

def force_delete_folder(folder_path):
    """Supprime un dossier et son contenu de manière agressive en débloquant les droits."""
    if not os.path.exists(folder_path):
        return
    
    def remove_readonly(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    for _ in range(5):
        try:
            shutil.rmtree(folder_path, onerror=remove_readonly)
            if not os.path.exists(folder_path):
                break
        except Exception:
            time.sleep(0.3)

class SteamAPI:
    def __init__(self):
        self.games = {}
        self.settings = {
            "install_dir": DEFAULT_INSTALL_FOLDER,
            "rar_scan_folder": "",
            "theme": "dark",
            "lang": "fr",
            "auto_scan": False,
            "smooth_transitions": True,
            "sgdb_api_key": DEFAULT_SGDB_KEY
        }
        self.cancel_flag = False
        self.pause_flag = False
        self.background_mode = False
        self.current_process = None
        self.install_progress = {"percent": 0, "status": "idle", "game": ""}
        
        self.load_data()
        os.makedirs(self.settings["install_dir"], exist_ok=True)
        
        if self.settings.get("auto_scan", False):
            self.scan_installed_games()
            self.scan_rar_folder()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content: return
                    saved = json.loads(content)
                    self.games = saved.get("games", {})
                    self.settings.update(saved.get("settings", {}))
            except Exception as e:
                print("Erreur chargement JSON:", e)
                self.games = {}

    def save_data(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "games": self.games,
                    "settings": self.settings
                }, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("Erreur sauvegarde JSON:", e)

    def _get_base64_image(self, file_path_or_url):
        if not file_path_or_url: return ""
        if file_path_or_url.startswith("http") or file_path_or_url.startswith("data:"): return file_path_or_url
        if not os.path.exists(file_path_or_url): return ""
        try:
            mime_type, _ = mimetypes.guess_type(file_path_or_url)
            mime_type = mime_type or "image/png"
            with open(file_path_or_url, "rb") as image_file:
                return f"data:{mime_type};base64,{base64.b64encode(image_file.read()).decode('utf-8')}"
        except Exception:
            return ""

    def get_settings(self):
        return self.settings

    def save_settings(self, new_settings):
        was_auto_scan = self.settings.get("auto_scan", False)
        self.settings.update(new_settings)
        os.makedirs(self.settings["install_dir"], exist_ok=True)

        if was_auto_scan and not self.settings["auto_scan"]:
            to_remove = [k for k, v in self.games.items() if isinstance(v, dict) and v.get("source") == "installed"]
            for k in to_remove: del self.games[k]

        self.save_data()

        if self.settings["auto_scan"]:
            self.scan_installed_games()
            self.scan_rar_folder()
        return self.settings

    def select_install_folder(self):
        global window
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if result:
            self.settings["install_dir"] = result[0]
            self.save_data()
            return self.settings["install_dir"]
        return None

    def select_rar_folder(self):
        global window
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if result:
            self.settings["rar_scan_folder"] = result[0]
            self.save_data()
            self.scan_rar_folder()
            return self.settings["rar_scan_folder"]
        return None

    def scan_rar_folder(self):
        folder = self.settings.get("rar_scan_folder")
        if not folder or not os.path.exists(folder): return self.get_games()
        
        found = False
        valid_extensions = ('.zip', '.rar', '.7z', '.tar', '.gz')
        
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(valid_extensions):
                    path = os.path.join(root, f)
                    name = clean_game_name(os.path.splitext(f)[0])
                    
                    if name not in self.games:
                        self.games[name] = {
                            "rar_path": path, 
                            "icon_path": "", 
                            "banner_path": "",
                            "category": "Archives Auto", 
                            "source": "archive"
                        }
                        found = True
                    else:
                        if isinstance(self.games[name], dict):
                            self.games[name]["rar_path"] = path

        if found:
            self.save_data()
        return self.get_games()

    def select_custom_exe(self, game_name):
        global window
        result = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=('Fichiers Exécutables (*.exe)', 'Tous les fichiers (*.*)'))
        if result:
            if isinstance(self.games[game_name], str): self.games[game_name] = {"rar_path": self.games[game_name]}
            self.games[game_name]["exe_path"] = result[0]
            self.games[game_name]["folder_path"] = os.path.dirname(result[0])
            self.save_data()
            return {"status": "success", "exe_path": result[0], "games": self.get_games()}
        return {"status": "cancelled"}

    def set_custom_game_folder(self, game_name):
        global window
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if result:
            target_folder = result[0]
            exe_found = ""
            ignored_exes = ["unins", "setup", "crash", "reporter", "update", "redist", "directx"]
            for root, _, files in os.walk(target_folder):
                for file in files:
                    if file.lower().endswith(".exe") and not any(ign in file.lower() for ign in ignored_exes):
                        exe_found = os.path.join(root, file)
                        break
                if exe_found: break

            if isinstance(self.games[game_name], str): self.games[game_name] = {"rar_path": self.games[game_name]}
            self.games[game_name]["folder_path"] = target_folder
            self.games[game_name]["exe_path"] = exe_found
            self.games[game_name]["source"] = "installed" if not self.games[game_name].get("rar_path") else "archive"
            self.save_data()
            return {"status": "success", "games": self.get_games(), "exe_found": bool(exe_found)}
        return {"status": "cancelled"}

    def get_games(self):
        result = []
        for name, data in list(self.games.items()):
            if isinstance(data, str): data = {"rar_path": data, "category": "Non classé", "source": "archive"}
            
            rar_path = data.get("rar_path", "")
            folder_path = data.get("folder_path", "")
            exe_path = data.get("exe_path", "")
            source = data.get("source", "archive")
            
            target_folder = os.path.join(self.settings["install_dir"], name)
            
            # Vérification stricte : le jeu est installé si on a un executable valide ou un dossier d'installation effectif non vide
            has_valid_folder = bool(folder_path and os.path.exists(folder_path)) or (os.path.isdir(target_folder) and len(os.listdir(target_folder)) > 0)
            has_valid_exe = bool(exe_path and os.path.exists(exe_path))
            
            is_installed = (source == "installed") or (has_valid_folder and has_valid_exe)
            install_path = folder_path or target_folder if is_installed else ""

            result.append({
                "name": name, 
                "rar_path": rar_path, 
                "has_rar": bool(rar_path and os.path.exists(rar_path)),
                "icon_base64": self._get_base64_image(data.get("icon_path")),
                "banner_base64": self._get_base64_image(data.get("banner_path")),
                "installed": is_installed, 
                "install_path": install_path, 
                "exe_path": exe_path,
                "folder_path": folder_path, 
                "category": data.get("category", "Non classé"), 
                "source": source,
                "last_played": data.get("last_played", "")
            })
        return result

    def rename_game(self, old_name, new_name):
        if not new_name or old_name not in self.games: return {"status": "error", "message": "Nom invalide"}
        self.games[new_name] = self.games.pop(old_name)
        self.save_data()
        return {"status": "success", "games": self.get_games()}

    def set_game_category(self, game_name, category_name):
        if game_name in self.games:
            if isinstance(self.games[game_name], str): self.games[game_name] = {"rar_path": self.games[game_name]}
            self.games[game_name]["category"] = category_name
            self.save_data()
            return {"status": "success", "games": self.get_games()}
        return {"status": "error", "message": "Jeu introuvable."}

    def set_game_image(self, game_name, img_type):
        global window
        result = window.create_file_dialog(webview.OPEN_DIALOG, file_types=('Images (*.jpg;*.jpeg;*.png;*.webp)', 'Tous les fichiers (*.*)'))
        if result:
            if isinstance(self.games[game_name], str): self.games[game_name] = {"rar_path": self.games[game_name]}
            self.games[game_name][f"{img_type}_path"] = result[0]
            self.save_data()
            return {"status": "success", "games": self.get_games()}
        return {"status": "cancelled"}

    def fetch_steamgriddb_images(self, game_name):
        api_key = self.settings.get("sgdb_api_key", DEFAULT_SGDB_KEY).strip()
        headers = {"Authorization": f"Bearer {api_key}", "User-Agent": "Mozilla/5.0"}
        try:
            query = urllib.parse.quote(clean_game_name(game_name))
            req_search = urllib.request.Request(f"https://www.steamgriddb.com/api/v2/search/autocomplete/{query}", headers=headers)
            with urllib.request.urlopen(req_search) as resp:
                data_search = json.loads(resp.read().decode('utf-8'))
            
            if not data_search.get("success") or not data_search.get("data"): return {"status": "error", "message": "Introuvable sur SteamGridDB."}
            game_id = data_search["data"][0]["id"]
            
            banner_url, icon_url = "", ""
            try:
                with urllib.request.urlopen(urllib.request.Request(f"https://www.steamgriddb.com/api/v2/heroes/game/{game_id}", headers=headers)) as resp:
                    banner_url = json.loads(resp.read().decode('utf-8'))["data"][0]["url"]
            except Exception: pass
            
            try:
                with urllib.request.urlopen(urllib.request.Request(f"https://www.steamgriddb.com/api/v2/icons/game/{game_id}", headers=headers)) as resp:
                    icon_url = json.loads(resp.read().decode('utf-8'))["data"][0]["url"]
            except Exception: pass

            if isinstance(self.games[game_name], str): self.games[game_name] = {"rar_path": self.games[game_name]}
            if banner_url: self.games[game_name]["banner_path"] = banner_url
            if icon_url: self.games[game_name]["icon_path"] = icon_url
            
            self.save_data()
            return {"status": "success", "games": self.get_games()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete_game_rar(self, game_name):
        if game_name in self.games:
            data = self.games[game_name]
            rar_path = data.get("rar_path") if isinstance(data, dict) else data
            if rar_path and os.path.exists(rar_path): os.remove(rar_path)
            
            if isinstance(data, dict): data["rar_path"] = ""
            else: self.games[game_name] = {"rar_path": "", "icon_path": "", "banner_path": "", "category": "Non classé", "source": "archive"}
            
            self.save_data()
            return {"status": "success", "games": self.get_games()}
        return {"status": "error"}

    def delete_game_from_list(self, game_name):
        if game_name in self.games:
            del self.games[game_name]
            self.save_data()
            return {"status": "success", "games": self.get_games()}
        return {"status": "error"}

    def add_game_dialog(self):
        global window
        result = window.create_file_dialog(webview.OPEN_DIALOG, file_types=('Archives et Jeux (*.rar;*.zip;*.7z;*.exe)', 'Tous les fichiers (*.*)'))
        if result:
            file_path = result[0]
            game_name = clean_game_name(os.path.splitext(os.path.basename(file_path))[0])
            is_exe = file_path.lower().endswith(".exe")
            
            self.games[game_name] = {
                "rar_path": "" if is_exe else file_path,
                "exe_path": file_path if is_exe else "",
                "folder_path": os.path.dirname(file_path) if is_exe else "",
                "icon_path": "", "banner_path": "",
                "category": "Non classé", "source": "installed" if is_exe else "archive"
            }
            self.save_data()
            self.fetch_steamgriddb_images(game_name)
            return self.get_games()
        return None

    def scan_installed_games(self):
        found_games = {}
        candidate_folders = []

        drives = [f"{d}:\\" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")]
        for drive in drives:
            candidate_folders.extend([
                os.path.join(drive, "Program Files (x86)", "Steam", "steamapps", "common"),
                os.path.join(drive, "Program Files", "Epic Games"),
                os.path.join(drive, "GOG Games"), os.path.join(drive, "Games")
            ])

        for folder in candidate_folders:
            if not os.path.exists(folder): continue
            try:
                for game_dir in os.listdir(folder):
                    full_game_path = os.path.join(folder, game_dir)
                    if not os.path.isdir(full_game_path) or game_dir.startswith("."): continue
                    
                    exe_found = ""
                    for root, _, files in os.walk(full_game_path):
                        for file in files:
                            if file.lower().endswith(".exe") and not any(ign in file.lower() for ign in ["unins", "setup", "crash"]):
                                exe_found = os.path.join(root, file)
                                break
                        if exe_found: break

                    clean_dir = clean_game_name(game_dir)
                    if exe_found and clean_dir not in self.games:
                        found_games[clean_dir] = {"rar_path": "", "icon_path": "", "banner_path": "", "exe_path": exe_found, "category": "Jeux installés", "source": "installed"}
            except Exception: pass

        if found_games:
            self.games.update(found_games)
            self.save_data()
        return self.get_games()

    def toggle_pause_install(self):
        self.pause_flag = not self.pause_flag
        if self.current_process and self.current_process.poll() is None:
            try:
                p = psutil.Process(self.current_process.pid)
                if self.pause_flag:
                    p.suspend()
                else:
                    p.resume()
            except Exception:
                pass
        return {"paused": self.pause_flag}

    def set_execution_mode(self, background):
        self.background_mode = background
        p_app = psutil.Process(os.getpid())
        if background:
            p_app.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == 'nt' else 10)
        else:
            p_app.nice(psutil.HIGH_PRIORITY_CLASS if os.name == 'nt' else -10)
            
        if self.current_process and self.current_process.poll() is None:
            try:
                p_ext = psutil.Process(self.current_process.pid)
                if background:
                    p_ext.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == 'nt' else 10)
                else:
                    p_ext.nice(psutil.REALTIME_PRIORITY_CLASS if os.name == 'nt' else -15)
            except Exception:
                pass

        return {"background": self.background_mode}

    def cancel_install(self):
        self.cancel_flag = True
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.kill()
                self.current_process.wait()
            except Exception:
                pass
        return {"status": "success"}

    def get_install_progress(self):
        return self.install_progress

    def install_game(self, game_name):
        self.cancel_flag = False
        self.pause_flag = False
        self.background_mode = False
        self.install_progress = {"percent": 0, "status": "running", "game": game_name}

        game_data = self.games.get(game_name)
        if not game_data: return {"status": "error", "message": "Jeu introuvable."}

        rar_path = game_data.get("rar_path") if isinstance(game_data, dict) else game_data
        if not rar_path or not os.path.exists(rar_path): return {"status": "error", "message": "Archive RAR introuvable sur le disque."}

        target_folder = os.path.join(self.settings.get("install_dir"), game_name)
        os.makedirs(target_folder, exist_ok=True)

        def _extract_task():
            extractor_exe = find_extractor_executable()
            total_expected_size = estimate_uncompressed_size(rar_path)

            monitoring = True
            def _monitor_size():
                nonlocal monitoring
                while monitoring and not self.cancel_flag:
                    curr_size = get_dir_size(target_folder)
                    if total_expected_size > 0:
                        pct = int((curr_size / total_expected_size) * 100)
                        self.install_progress["percent"] = min(99, max(0, pct))
                    time.sleep(0.3)

            monitor_thread = threading.Thread(target=_monitor_size, daemon=True)
            monitor_thread.start()

            try:
                ext = os.path.splitext(rar_path)[1].lower()

                if extractor_exe:
                    extractor_name = os.path.basename(extractor_exe).lower()
                    if "winrar" in extractor_name:
                        cmd = [extractor_exe, "x", "-ibck", "-y", rar_path, target_folder]
                    else:  # 7z ou NanaZip
                        cmd = [extractor_exe, "x", rar_path, f"-o{target_folder}", "-y"]

                    self.current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    self.set_execution_mode(False)

                    while self.current_process.poll() is None:
                        if self.cancel_flag:
                            self.current_process.kill()
                            break
                        time.sleep(0.2)
                    
                    if not self.cancel_flag and self.current_process.returncode != 0:
                        raise Exception("L'extraction externe a échoué.")

                elif HAS_PATOOL:
                    patoolib.extract_archive(rar_path, outdir=target_folder)

                elif ext == '.zip':
                    with zipfile.ZipFile(rar_path, 'r') as zip_ref:
                        for file in zip_ref.infolist():
                            while self.pause_flag:
                                if self.cancel_flag: break
                                time.sleep(0.2)
                            if self.cancel_flag: break
                            zip_ref.extract(file, target_folder)

                else:
                    shutil.unpack_archive(rar_path, target_folder)

                monitoring = False

                if self.cancel_flag:
                    time.sleep(0.5)
                    force_delete_folder(target_folder)
                    if isinstance(self.games[game_name], dict):
                        self.games[game_name]["exe_path"] = ""
                        self.games[game_name]["folder_path"] = ""
                    self.save_data()
                    self.install_progress = {"percent": 0, "status": "cancelled", "game": game_name}
                    return

                # Recherche de l'exécutable
                exe_found = ""
                ignored_exes = ["unins", "setup", "crash", "reporter", "update", "redist", "directx"]
                for root, _, files in os.walk(target_folder):
                    for file in files:
                        if file.lower().endswith(".exe") and not any(ign in file.lower() for ign in ignored_exes):
                            exe_found = os.path.join(root, file)
                            break
                    if exe_found: break

                if isinstance(self.games[game_name], str): self.games[game_name] = {"rar_path": rar_path}
                self.games[game_name]["exe_path"] = exe_found
                self.games[game_name]["folder_path"] = target_folder
                self.games[game_name]["source"] = "archive"
                self.save_data()

                self.install_progress = {"percent": 100, "status": "finished", "game": game_name}

            except Exception as e:
                monitoring = False
                force_delete_folder(target_folder)
                if isinstance(self.games.get(game_name), dict):
                    self.games[game_name]["exe_path"] = ""
                    self.games[game_name]["folder_path"] = ""
                self.save_data()

                if self.cancel_flag:
                    self.install_progress = {"percent": 0, "status": "cancelled", "game": game_name}
                else:
                    self.install_progress = {"percent": 0, "status": "error", "message": str(e), "game": game_name}

        threading.Thread(target=_extract_task, daemon=True).start()
        return {"status": "started"}

    def play_game(self, game_name):
        game_data = self.games.get(game_name, {})
        if isinstance(game_data, str):
            game_data = {"rar_path": game_data}
            self.games[game_name] = game_data

        flags = 0x08000000 if os.name == 'nt' else 0
        exe = game_data.get("exe_path")
        
        target_exe = None
        if exe and os.path.exists(exe):
            target_exe = exe
        else:
            folder = game_data.get("folder_path") or os.path.join(self.settings["install_dir"], game_name)
            if os.path.exists(folder):
                for root, _, files in os.walk(folder):
                    for file in files:
                        if file.endswith(".exe") and not file.startswith("unins"):
                            target_exe = os.path.join(root, file)
                            self.games[game_name]["exe_path"] = target_exe
                            break
                    if target_exe: break

        if target_exe:
            try:
                subprocess.Popen([target_exe], cwd=os.path.dirname(target_exe), creationflags=flags)
                self.games[game_name]["last_played"] = time.strftime("%d/%m/%Y à %H:%M")
                self.save_data()
                return {"status": "success"}
            except Exception as e:
                return {"status": "error", "message": f"Échec du lancement : {str(e)}"}
                
        return {"status": "error", "message": "Exécutable introuvable."}

    def uninstall_game(self, game_name):
        game_data = self.games.get(game_name, {})
        if (game_data.get("source") if isinstance(game_data, dict) else "archive") == "installed":
            del self.games[game_name]
            self.save_data()
            return {"status": "success"}

        target_folder = game_data.get("folder_path") or os.path.join(self.settings["install_dir"], game_name)
        try:
            force_delete_folder(target_folder)
            if isinstance(game_data, dict):
                game_data["exe_path"] = ""
                game_data["folder_path"] = ""
            self.save_data()
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

if __name__ == '__main__':
    api = SteamAPI()
    html_path = get_resource_path("index.html")
    
    icon_candidate = get_resource_path("icon_12.ico")
    if not os.path.exists(icon_candidate):
        icon_candidate = get_resource_path("icon.ico")
    
    app_icon = icon_candidate if os.path.exists(icon_candidate) else None

    window = webview.create_window(
        title='PG Launcher',
        url=html_path,
        js_api=api,
        width=1240,
        height=820,
        resizable=True,
        background_color='#0b0f17',
    )
    webview.start()