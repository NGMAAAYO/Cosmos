import os
import io
import re
import sys
import json
import uuid
import time
import shutil
import random
import zipfile
import threading
import importlib
from datetime import datetime
from hashlib import md5
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import BackgroundTasks, Response
from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
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
MATCH_LOCK = threading.Lock()

for folder in [MAPS_FOLDER, REPLAYS_FOLDER]:
    folder.mkdir(exist_ok=True)

def get_global_manager():
    global global_manager, ongoing_matches
    try:
        global_manager
    except NameError:
        from multiprocessing import Manager
        global_manager = Manager()
        ongoing_matches = global_manager.dict()
    return global_manager, ongoing_matches

############################
# Utility functions & Persistence
############################

def load_json(file: Path) -> Any:
    if file.exists():
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        # 对于 accounts.json 返回字典，对于 matches.json 返回字典
        if file == ACCOUNTS_FILE or file == MATCHES_FILE:
            return {}
        else:
            return []

def save_json(file: Path, data: Any) -> None:
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_accounts() -> Dict[str, Any]:
    return load_json(ACCOUNTS_FILE)

def save_accounts(accounts: Dict[str, Any]) -> None:
    save_json(ACCOUNTS_FILE, accounts)

def get_matches() -> Dict[str, Any]:
    return load_json(MATCHES_FILE)

def save_matches(matches: Dict[str, Any]) -> None:
    save_json(MATCHES_FILE, matches)

############################
# Game Engine Runner Function
############################

def run_small_match(map_file: str, players: List[str], match_id: str, mini_index: int, shared_dict: Dict[str, Any]) -> Dict[str, Any]:
    game = Instance(players, map_file, game_round=1000, debug=False)

    replay_filename = f"replay_{players[0]}_{players[1]}_{match_id}_{mini_index}.rpl"
    replay_fullpath = REPLAYS_FOLDER / replay_filename
    game.replay_path = str(replay_fullpath)

    game.new_replay()
    for i in range(1000):
        game.next_round()
        shared_dict[match_id][mini_index] = i + 1
        if game.game_end_flag:
            break
    game.counting_result()
    shared_dict[match_id][mini_index] = 1000

    try:
        zip_filename = replay_filename.rsplit('.', 1)[0] + ".zip"
        zip_fullpath = REPLAYS_FOLDER / zip_filename
        with zipfile.ZipFile(zip_fullpath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(replay_fullpath, arcname=replay_filename)
        replay_fullpath.unlink(missing_ok=True)
    except Exception as e:
        print(f"Failed to create zip file: {e}")
        zip_filename = replay_filename

    return {"winner": game.replay["winner"], "replay": zip_filename}

############################
# FastAPI Application Setup
############################

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="!secret_key_change_this!")

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
    accounts[username] = {"username": username, "password": md5(password.encode()).hexdigest(), "points": 1000, "code_module": None, "match_history": []}
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
    if not account or account["password"] != md5(password.encode()).hexdigest():
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

# Leaderboard, Match History endpoints remain similar.
@app.get("/leaderboard")
async def leaderboard(request: Request, user: dict = Depends(get_current_user)):
    accounts = get_accounts()
    sorted_accounts = sorted(accounts.values(), key=lambda a: a["points"], reverse=True)
    return templates.TemplateResponse("leaderboard.html", {"request": request, "accounts": sorted_accounts, "user": user})

@app.get("/match_history")
async def match_history(request: Request, user: dict = Depends(require_user)):
    matches = get_matches()
    match_history = []
    for match_id in user.get("match_history", []):
        if match_id in matches:
            m = matches[match_id].copy()
            m["opponent"] = m["player_B"] if m["player_A"] == user["username"] else m["player_A"]
            if m["player_A"] != user["username"]:
                m["score"] = ":".join(reversed(m["score"].split(":")))
            match_history.append(m)

    match_history = sorted(match_history, key=lambda m: m["timestamp"], reverse=True)
    return templates.TemplateResponse("match_history.html", {"request": request, "match_history": match_history, "user": user})

def update_elo(r_a: int, r_b: int, map_results: tuple, k: int = 32, min_score: int = 100) -> tuple:
    """
    基于每张地图独立计算的ELO更新
    :param r_a: 玩家A当前分数
    :param r_b: 玩家B当前分数
    :param map_results: 三张地图的结果元组，每个元素为：
                       0表示A胜，1表示B胜，-1表示平局
                       例如 (0, 0, 1) 表示A赢前两张，B赢第三张
    :param k: 基础调整系数
    :return: 调整后的分数元组 (new_r_a, new_r_b)
    """
    delta_a_total = 0
    delta_b_total = 0
    current_r_a = r_a
    current_r_b = r_b

    # 逐张地图计算变动
    for result in map_results:
        # 计算单局期望值
        e_a = 1 / (1 + 10 ** ((current_r_b - current_r_a) / 400))
        e_b = 1 - e_a

        # 根据单局结果计算变动
        if result == 0:
            delta_a = k * (1 - e_a)
            delta_b = k * (0 - e_b)
        elif result == 1:
            delta_a = k * (0 - e_a)
            delta_b = k * (1 - e_b)
        else:  # 平局
            delta_a = k * (0.5 - e_a)
            delta_b = k * (0.5 - e_b)

        # 累加变动并实时更新临时分（影响后续地图计算）
        delta_a_total += delta_a
        delta_b_total += delta_b
        current_r_a += delta_a
        current_r_b += delta_b

    # 最终四舍五入并应用最低分保护
    new_r_a = max(round(r_a + delta_a_total), min_score)
    new_r_b = max(round(r_b + delta_b_total), min_score)

    return (new_r_a, new_r_b)

def update_elo_advanced(r_a, r_b, result, games_a=0, games_b=0):
    # 动态计算K值
    k_a = 40 if games_a < 10 else (24 if r_a > 2000 else 32)
    k_b = 40 if games_b < 10 else (24 if r_b > 2000 else 32)

    # 使用平均K值或分别计算
    k = (k_a + k_b) // 2
    return update_elo(r_a, r_b, result, k)

def process_match(username: str, opponent: str, chosen_maps: List[Path], players: List[str]):
    accounts = get_accounts()
    match_id = str(uuid.uuid4())
    # 在发起后台任务时，先将比赛记录写入，状态为“进行中”，同时初始化进度信息
    global_record = {
        "id": match_id,
        "timestamp": int(datetime.now().timestamp()),
        "player_A": username,
        "player_B": opponent,
        "score": "0:0",
        "replays": [],
        "status": "queued"
    }
    matches = get_matches()
    matches[match_id] = global_record
    save_matches(matches)
    
    # 保存本场比赛的 match_id 到双方历史记录中。
    accounts[username]["match_history"].append(match_id)
    accounts[opponent]["match_history"].append(match_id)
    save_accounts(accounts)

    with MATCH_LOCK:
        matches = get_matches()
        matches[match_id]["status"] = "ongoing"
        save_matches(matches)
        global_manager, ongoing_matches = get_global_manager()
        ongoing_matches[match_id] = global_manager.list([0, 0, 0])
        
        results = []
        with concurrent.futures.ProcessPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(run_small_match, str(map_path), players, match_id, i, ongoing_matches)
                    for i, map_path in enumerate(chosen_maps)]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        # 根据各局结果统计分数
        win_count = {players[0]: 0, players[1]: 0}
        replay_links = []
        result = []
        for res in results:
            if res["winner"] == username:
                win_count[res["winner"]] += 1
                result.append(0)
            elif res["winner"] == opponent:
                win_count[res["winner"]] += 1
                result.append(1)
            else:
                result.append(-1)
            replay_links.append(res["replay"])

        # 更新分数
        accounts = get_accounts()
        player_a = accounts[username]
        player_b = accounts[opponent]
        player_a["points"], player_b["points"] = update_elo(player_a["points"], player_b["points"], result)
        save_accounts(accounts)

        global_record["score"] = f"{win_count[players[0]]}:{win_count[players[1]]}"
        global_record["replays"] = replay_links
        global_record["status"] = "finished"
        matches = get_matches()
        matches[match_id] = global_record
        save_matches(matches)

@app.get("/match_progress/{match_id}")
async def match_progress(match_id: str, user: dict = Depends(require_user)):
    global_manager, ongoing_matches = get_global_manager()
    matches = get_matches()
    if match_id not in matches:
        raise HTTPException(status_code=404, detail="比赛不存在。")
    
    if matches[match_id]["status"] == "queued":
        return {"match_id": match_id, "progress": [0, 0, 0], "status": "queued"}
    
    if user["username"] not in [matches[match_id]["player_A"], matches[match_id]["player_B"]]:
        raise HTTPException(status_code=403, detail="您不是比赛的参与者。")
    
    progress_list = ongoing_matches.get(match_id)
    if progress_list is None:
        progress_list = [0, 0, 0]

    return {"match_id": match_id, "progress": list(progress_list), "status": matches[match_id].get("status", "ongoing")}

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
    if len(available_maps) < 1:
        return templates.TemplateResponse("dashboard.html", {"request": request, "error": "没有足够的地图。", "user": user})
    chosen_maps = [random.choice(available_maps) for _ in range(3)]
    players = [username, opponent]

    # 将比赛任务放入后台执行。
    background_tasks.add_task(process_match, username, opponent, chosen_maps, players)

    # 立即返回响应
    return templates.TemplateResponse("dashboard.html", {"request": request, "message": "比赛已开始！比赛结果将在比赛结束后更新。", "user": user})

@app.get("/replay/{replay_filename}")
async def get_replay(replay_filename: str, _user: dict = Depends(require_user)):
    replay_path = REPLAYS_FOLDER / replay_filename
    if not replay_path.exists():
        raise HTTPException(status_code=404, detail="未找到回放。")
    file_size = os.path.getsize(replay_path)
    headers = {
        "Content-Length": str(file_size),
        "Cache-Control": "public, max-age=31536000, immutable"
    }
    stream = open(replay_path, "rb")
    return StreamingResponse(stream, media_type="application/octet-stream", headers=headers)

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

@app.get("/visualizer")
async def visualizer(request: Request):
    return FileResponse("visualizer/index.html")

visualizer_cache = {}

def load_visualizer_files():
    build_folder = Path("visualizer/Build")
    if not build_folder.exists():
        raise RuntimeError("visualizer/Build folder does not exist.")
    for file in build_folder.iterdir():
        if file.is_file():
            visualizer_cache[file.name] = file.read_bytes()

load_visualizer_files()

@app.get("/visualizer/res/{filename}")
async def visualizer_res(filename: str):
    if filename not in visualizer_cache:
        file_path = Path("visualizer/Build") / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found.")
        visualizer_cache[filename] = file_path.read_bytes()

    content = visualizer_cache[filename]
    stream = io.BytesIO(content)
    headers = {"Cache-Control": "public, max-age=86400"}
    if filename.endswith(".gz"):
        headers["Content-Encoding"] = "gzip"
    return StreamingResponse(stream, headers=headers, media_type="application/octet-stream")

@app.get("/favicon.ico")
async def favicon():
    file_path = "static/favicon.ico"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Favicon not found.")
    file_size = os.path.getsize(file_path)
    headers = {
        "Content-Length": str(file_size),
        "Cache-Control": "public, max-age=31536000, immutable"
    }
    stream = open(file_path, "rb")
    return StreamingResponse(stream, headers=headers, media_type="image/x-icon")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=4536, reload=True)
