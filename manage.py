import subprocess
import os
import sys
import signal
import psutil 
from loguru import logger

# PID 文件路径
PID_USER_AGENT = "pid_user_agent.pid"
PID_SCHEDULER = "pid_scheduler.pid"

def start_services():
    """启动服务"""
    logger.info("Starting services...")
    try:
        subprocess.run(['python', 'launcher.py'], check=True)
        logger.info("Services started successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to start services: {e}")
        sys.exit(1)

def stop_services():
    """停止服务"""
    logger.info("Stopping services...")
    for pid_file in [PID_USER_AGENT, PID_SCHEDULER]:
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                if psutil.pid_exists(pid):
                    process = psutil.Process(pid)
                    process.send_signal(signal.SIGTERM)
                    process.wait(timeout=5)
                    logger.info(f"Stopped process with PID {pid} from {pid_file}")
                os.remove(pid_file)
            except (ValueError, IOError, psutil.NoSuchProcess, psutil.TimeoutExpired) as e:
                logger.error(f"Failed to stop process in {pid_file}: {e}")
                if os.path.exists(pid_file):
                    os.remove(pid_file)
        else:
            logger.warning(f"PID file {pid_file} not found")

def main():
    #--------------------------------------------------------
    # 这个脚本是用来管理服务的启动和停止的，实际执行的是 python3 launcher.py 这个文件。只是利用了launcher保存了两个程序的 pid，stop就是利用这两个文件来停止程序的。
    # 用法：python3 manage.py [start|stop]
    # - 启动：python3 manage.py start
    # - 停止：python3 manage.py stop
    #--------------------------------------------------------
    if len(sys.argv) != 2 or sys.argv[1] not in ['start', 'stop']:
        print("Usage: python3 manage.py [start|stop]")
        sys.exit(1)

    command = sys.argv[1]
    if command == 'start':
        start_services()
    elif command == 'stop':
        stop_services()

if __name__ == "__main__":
    main()