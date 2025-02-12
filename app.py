import os
import re
import sys
import json
import shutil
import random
import zipfile
import importlib
from datetime import datetime
from hashlib import md5
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import BackgroundTasks
from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import concurrent.futures

from core.game import Instance

############################
# Global Settings & Directories
############################

# Maximum file upload size (10MB).
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

# Updated upload destination (code will be extracted to "./src" now)
SRC_FOLDER = Path("src")
SRC_FOLDER.mkdir(exist_ok=True)

ACCOUNTS_FILE = Path("accounts.json")
MATCHES_FILE = Path("matches.json")
MAPS_FOLDER = Path("maps")
REPLAYS_FOLDER = Path("replays")

for folder in [MAPS_FOLDER, REPLAYS_FOLDER]:
    folder.mkdir(exist_ok=True)

############################
# Utility functions & Persistence (same as before)
############################

def load_json(file: Path) -> Any:
    if file.exists():
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {} if file == ACCOUNTS_FILE else []

def save_json(file: Path, data: Any) -> None:
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_accounts() -> Dict[str, Any]:
    return load_json(ACCOUNTS_FILE)

def save_accounts(accounts: Dict[str, Any]) -> None:
    save_json(ACCOUNTS_FILE, accounts)

def get_matches() -> List[Any]:
    return load_json(MATCHES_FILE)

def save_matches(matches: List[Any]) -> None:
    save_json(MATCHES_FILE, matches)

############################
# Game Engine Runner Function
############################

def run_small_match(map_file: str, players: List[str]) -> Dict[str, Any]:
    game = Instance(players, map_file, game_round=1000, debug=False)
    # Create a .rpl file
    replay_filename = f"replay_{players[0]}_{players[1]}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.rpl"
    replay_fullpath = REPLAYS_FOLDER / replay_filename
    game.replay_path = str(replay_fullpath)
    winner, reason, _ = game.run()
    
    # Compress the .rpl file into a zip archive
    zip_filename = replay_filename.rsplit('.', 1)[0] + ".zip"
    zip_fullpath = REPLAYS_FOLDER / zip_filename
    with zipfile.ZipFile(zip_fullpath, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(replay_fullpath, arcname=replay_filename)
    # Optionally remove the original .rpl file.
    replay_fullpath.unlink(missing_ok=True)
    
    # Return the zip filename instead.
    return {"winner": winner, "replay": zip_filename}

############################
# FastAPI Application Setup
############################

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="!secret_key_change_this!")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

############################
# Authentication Dependencies
############################

def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    username = request.session.get("username")
    if not username:
        return None
    accounts = get_accounts()
    return accounts.get(username)

def require_user(request: Request) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录。")
    return user

############################
# Routes
############################

@app.get("/")
async def index(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

# Updated registration endpoint: check if the username is a legal Python module name.
@app.post("/register")
async def register_post(request: Request, username: str = Form(...), password: str = Form(...)):
    if not re.match(r"^[A-Za-z_]\w*$", username):
        return templates.TemplateResponse("register.html", {"request": request, "error": "用户名必须是一个合法的Python模块名（只能包含字母、数字、下划线，且不能以数字开头）。"})
    if username in ["static", "templates", "replays", "src", "maps", "None", "True", "False"]:
        return templates.TemplateResponse("register.html", {"request": request, "error": "用户名无效。"})
    accounts = get_accounts()
    if username in accounts:
        return templates.TemplateResponse("register.html", {"request": request, "error": "用户名已存在。"})
    # Create new account with 1000 pts. Set code_module equal to the account name.
    accounts[username] = {"username": username, "password": md5(password), "points": 1000, "code_module": None, "match_history": []}
    save_accounts(accounts)
    return RedirectResponse(url="/login", status_code=302)

@app.get("/register")
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/login")
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    accounts = get_accounts()
    account = accounts.get(username)
    if not account or account["password"] != md5(password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "用户名或密码无效。"})
    request.session["username"] = username
    return RedirectResponse(url="/dashboard", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)

@app.get("/dashboard")
async def dashboard(request: Request, user: dict = Depends(require_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})

# Updated Upload Code endpoint.
@app.get("/upload_code")
async def upload_code_get(request: Request, user: dict = Depends(require_user)):
    return templates.TemplateResponse("upload_code.html", {"request": request, "user": user})

@app.post("/upload_code")
async def upload_code_post(request: Request, file: UploadFile = File(...), user: dict = Depends(require_user)):
    # Limit file size to 10MB.
    if file.content_type != "application/x-zip-compressed":
        return templates.TemplateResponse("upload_code.html", {"request": request, "error": "请上传zip文件。", "user": user})
    if file.headers.get("content-length"):
        content_length = int(file.headers.get("content-length"))
        if content_length > MAX_UPLOAD_SIZE:
            return templates.TemplateResponse("upload_code.html", {"request": request, "error": "文件大小超出10MB限制。", "user": user})
    # Save the file temporarily.
    tmp_zip_path = SRC_FOLDER / f"{user['username']}_upload.zip"
    with tmp_zip_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        with zipfile.ZipFile(tmp_zip_path, 'r') as zip_ref:
            namelist = zip_ref.namelist()
            if not namelist:
                raise Exception("Zip文件为空。")
            # Determine the common prefix for all files.
            common_prefix = os.path.commonprefix(namelist)
            # If the common prefix ends with "/" then remove it.
            common_prefix = common_prefix.rstrip("/")
            # If there is a common prefix that is not empty, then expect it to be a directory
            # and we will strip it from all file names.
            extract_dir = SRC_FOLDER / user["username"]
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir(parents=True)
            for member in zip_ref.infolist():
                # Skip directories.
                if member.is_dir():
                    continue
                member_path = Path(member.filename)
                # Remove the common prefix if present.
                if common_prefix and member_path.parts[0] == common_prefix:
                    rel_path = Path(*member_path.parts[1:])
                else:
                    rel_path = member_path
                # Construct destination file path.
                dest_file_path = extract_dir / rel_path
                dest_file_path.parent.mkdir(parents=True, exist_ok=True)
                with zip_ref.open(member) as source, dest_file_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
    except Exception as e:
        tmp_zip_path.unlink(missing_ok=True)
        return templates.TemplateResponse("upload_code.html", {"request": request, "error": f"解压zip文件失败：{e}", "user": user})
    finally:
        if tmp_zip_path.exists():
            tmp_zip_path.unlink()
            
    # --- Validation Step: Ensure that main.py in the uploaded code defines a class Player with a run() method ---    
    try:
        # We expect the extracted code to be in src/{username}/main.py.
        # Ensure that the "src" folder is on sys.path.
        sys.path.insert(0, str(SRC_FOLDER))
        module_path = f"src.{user['username']}.main"
        # Alternatively, if you prefer to import as a top-level package, you can
        # do: module = importlib.import_module(f"{user['username']}.main")
        module = importlib.import_module(module_path)
        if not hasattr(module, "Player"):
            raise ImportError("上传的代码中 main.py 未定义 Player 类。")
        PlayerClass = getattr(module, "Player")
        if not callable(PlayerClass):
            raise ImportError("Player 不是可调用对象；它应当是一个类。")
        player_instance = PlayerClass()
        if not hasattr(player_instance, "run") or not callable(getattr(player_instance, "run")):
            raise ImportError("Player 类中没有可调用的 run() 方法。")
        # Optionally, you can call the run() method to test its execution.
        # player_instance.run()
    except Exception as e:
        # Remove the extracted folder on validation failure.
        shutil.rmtree(extract_dir)
        return templates.TemplateResponse("upload_code.html", {"request": request, "error": f"验证错误：{e}", "user": user})
    finally:
        # Remove the SRC_FOLDER path from sys.path if it was added.
        if sys.path[0] == str(SRC_FOLDER):
            sys.path.pop(0)
            
    # If validation passed, then update account data.
    accounts = get_accounts()
    accounts[user["username"]]["code_module"] = user["username"]
    save_accounts(accounts)
    return templates.TemplateResponse("upload_code.html", {"request": request, "message": "上传及解压成功。", "user": accounts[user["username"]]})

# Leaderboard, Match History endpoints remain the same.
@app.get("/leaderboard")
async def leaderboard(request: Request, user: dict = Depends(get_current_user)):
    accounts = get_accounts()
    sorted_accounts = sorted(accounts.values(), key=lambda a: a["points"], reverse=True)
    return templates.TemplateResponse("leaderboard.html", {"request": request, "accounts": sorted_accounts, "user": user})

@app.get("/match_history")
async def match_history(request: Request, user: dict = Depends(require_user)):
    return templates.TemplateResponse("match_history.html", {"request": request, "match_history": user.get("match_history", []), "user": user})

def process_match(username: str, opponent: str, chosen_maps: List[Path], players: List[str]):
    accounts = get_accounts()
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_small_match, str(map_path), players) for map_path in chosen_maps]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    win_count = {players[0]: 0, players[1]: 0}
    replay_links = []
    print(results)
    for res in results:
        if res["winner"] != "None":
            win_count[res["winner"]] += 1
        replay_links.append(res["replay"])

    diff = (win_count[players[0]] - win_count[players[1]]) * 100
    accounts[username]["points"] += diff
    accounts[opponent]["points"] -= diff

    match_record = {
        "timestamp": datetime.now().isoformat(),
        "opponent": opponent,
        "score": f"{win_count[players[0]]}:{win_count[players[1]]}",
        "replays": replay_links
    }
    accounts[username]["match_history"].append(match_record)
    opp_record = {  # record for opponent
        "timestamp": datetime.now().isoformat(),
        "opponent": username,
        "score": f"{win_count[players[1]]}:{win_count[players[0]]}",
        "replays": replay_links
    }
    accounts[opponent]["match_history"].append(opp_record)
    save_accounts(accounts)

    matches = get_matches()
    global_record = {
        "timestamp": datetime.now().isoformat(),
        "player_A": username,
        "player_B": opponent,
        "score": f"{win_count[players[0]]}:{win_count[players[1]]}",
        "replays": replay_links
    }
    matches.append(global_record)
    save_matches(matches)
    # You could also log the result or send updates via websocket if needed.

@app.post("/start_match")
async def start_match(request: Request,
                      background_tasks: BackgroundTasks,
                      opponent: str = Form(...),
                      user: dict = Depends(require_user)):
    accounts = get_accounts()
    username = user["username"]

    if opponent == username:
        return templates.TemplateResponse("dashboard.html", {"request": request, "error": "不能与自己比赛。", "user": user})
    if opponent not in accounts:
        return templates.TemplateResponse("dashboard.html", {"request": request, "error": "未找到对手。", "user": user})
    if not accounts[username].get("code_module"):
        return templates.TemplateResponse("dashboard.html", {"request": request, "error": "您必须先上传您的玩家代码。", "user": user})
    if not accounts[opponent].get("code_module"):
        return templates.TemplateResponse("dashboard.html", {"request": request, "error": "对手尚未上传玩家代码。", "user": user})

    available_maps = list(MAPS_FOLDER.glob("*.json"))
    if len(available_maps) < 3:
        return templates.TemplateResponse("dashboard.html", {"request": request, "error": "没有足够的地图。", "user": user})
    chosen_maps = random.sample(available_maps, 3)
    players = [username, opponent]

    # Instead of processing the match inline, add it as a background task.
    background_tasks.add_task(process_match, username, opponent, chosen_maps, players)

    # Immediately return a response.
    return templates.TemplateResponse("dashboard.html", {"request": request, "message": "比赛已开始！比赛结果将在比赛结束后更新。", "user": user})


@app.get("/replay/{replay_filename}")
async def get_replay(replay_filename: str, user: dict = Depends(require_user)):
    replay_path = REPLAYS_FOLDER / replay_filename
    if not replay_path.exists():
        raise HTTPException(status_code=404, detail="未找到回放。")
    return FileResponse(path=str(replay_path), filename=replay_filename)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    context = {"request": request, "error": exc.detail}
    return templates.TemplateResponse("error.html", context, status_code=exc.status_code)

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    # Optionally log the error here
    context = {"request": request, "error": str(exc)}
    return templates.TemplateResponse("error.html", context, status_code=500)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    context = {"request": request, "error": exc.errors()}
    return templates.TemplateResponse("error.html", context, status_code=400)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=4396)
