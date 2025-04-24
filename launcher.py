import subprocess
import os
import json
import platform
from loguru import logger
import sys


# PID 文件路径
PID_USER_AGENT = "pid_user_agent.pid"
PID_SCHEDULER = "pid_scheduler.pid"

# 获取 config.json 路径
def get_config_path():
    # 获取可执行文件所在目录
    if getattr(sys, 'frozen', False):
        # 打包后的可执行文件
        base_dir = os.path.dirname(sys.executable)
    else:
        # 开发环境，脚本所在目录
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'config.json')

# 读取配置文件
try:
    config_path = get_config_path()
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        raise FileNotFoundError(config_path)
    with open(config_path, 'r') as f:
        config = json.load(f)
    logger.info(f"Successfully loaded config from {config_path}")
except Exception as e:
    logger.error(f"Failed to load config.json: {e}")
    raise

# 获取两个程序的路径
user_agent_path = os.path.join(os.path.dirname(__file__), 'pcUserAgent', 'wl_user_agent_main.py')
scheduler_path = os.path.join(os.path.dirname(__file__), 'apscheduler', 'wl_scheduler.py')

# 验证路径是否存在
if not os.path.exists(user_agent_path):
    logger.error(f"User agent path does not exist: {user_agent_path}")
    raise FileNotFoundError(user_agent_path)
if not os.path.exists(scheduler_path):
    logger.error(f"Scheduler path does not exist: {scheduler_path}")
    raise FileNotFoundError(scheduler_path)

# 将配置序列化为 JSON 字符串
config_str = json.dumps(config)

# 根据操作系统选择启动方式
is_windows = platform.system() == "Windows"

# 启动子进程的参数
if is_windows:
    #creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    #popen_kwargs = {"creationflags": creationflags}
    popen_kwargs = {}
else:
    popen_kwargs = {"start_new_session": True}

# 检查是否已有进程运行
def is_process_running(pid_file):
    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                logger.warning(f"Process already running with PID {pid} in {pid_file}")
                return True
        except (ValueError, IOError):
            logger.warning(f"Invalid or stale PID file {pid_file}, removing it")
            os.remove(pid_file)
    return False

# 启动并记录 PID
def start_process(cmd, pid_file):
    if is_process_running(pid_file):
        logger.info(f"Skipping start for {pid_file} as process is already running")
        return
    try:
        process = subprocess.Popen(cmd, **popen_kwargs)
        with open(pid_file, 'w') as f:
            f.write(str(process.pid))
        logger.info(f"Started process with PID {process.pid} and saved to {pid_file}")
    except Exception as e:
        logger.error(f"Failed to start process with command {cmd}: {e}")
        raise

# 启动 wl_user_agent_main.py
start_process(['python', user_agent_path, config_str], PID_USER_AGENT)

# 启动 wl_scheduler.py
start_process(['python', scheduler_path, config_str], PID_SCHEDULER)