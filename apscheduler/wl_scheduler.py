import httpx
import uuid
import os
import re
import sys
import json
from urllib.parse import urlparse
from typing import Dict, List,Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.base import JobLookupError
from loguru import logger

#-----------------------------------------------------------------
# 默认配置
#-----------------------------------------------------------------
DEFAULT_CONFIG = {
    "schedulersrv_filelog_enable": 0,# 0:日志输出到前台，1: 日志输出到文件
    "scheduler_srv_port": 10005
}

# 从命令行参数加载配置
if len(sys.argv) > 1:
    config = json.loads(sys.argv[1])
else:
    config = DEFAULT_CONFIG

#-----------------------------------------------------------------
# 配置日志处理，设置为 5M 每个文件，一共5个。循环覆盖
#-----------------------------------------------------------------
# 通过配置文件中的开关来控制是否将日志输出到文件
SCHEDULER_LOG_OPEN = config.get("schedulersrv_filelog_enable", DEFAULT_CONFIG["schedulersrv_filelog_enable"])
# 动态构造相对路径
if SCHEDULER_LOG_OPEN:
    log_dir = os.path.join("./", "schedulerlog")
    log_path = os.path.join(log_dir, "wlscheduler.log")
    # 目录不存在时会报错，需先创建：
    os.makedirs(log_dir, exist_ok=True)
    # 移除默认控制台输出
    logger.remove()

    # 配置日志文件
    logger.add(log_path, rotation="20 MB", retention=5)
#-----------------------------------------------------------------

# ----------------- FastAPI 初始化 -----------------
app = FastAPI()
scheduler = AsyncIOScheduler()

from contextlib import asynccontextmanager

SCHEDULER_SRV_PORT = config.get("scheduler_srv_port", DEFAULT_CONFIG["scheduler_srv_port"])

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    logger.info("Scheduler started")
    logger.info(f"Scheduler started with {len(scheduler.get_jobs())} jobs")
    yield
    scheduler.shutdown(wait=False)# 强行关闭
    logger.info("Scheduler stopped")

app = FastAPI(lifespan=lifespan)

# ----------------- 请求与响应模型 -----------------
class ScheduleRequest(BaseModel):
    trigger_type: str                # 触发器类型: "cron" | "interval" | "date"
    trigger_args: Dict[str, Any]     # 触发器参数，例如 {"hour":12, "minute":0}
    notification_url: HttpUrl       # 通知回调地址
    task_id: str                   # 用户自定义任务标识
    msg_type: str                  # 用户定义触发这个调度任务的消息类型（例如：添加微信好友 add_wx_friend ）
    user_info_ext: Dict[str, Any]       # 存放用户自定义扩展信息

class ScheduleInfo(BaseModel):
    id: str                         # 作业 ID
    task_id: str                    # 用户任务 ID
    trigger_type: str              # 触发器类型
    trigger_args: Dict             # 触发器参数
    notification_url: str          # 回调地址
    next_run_time: str             # 下次运行时间
    user_scheduleRequest: str      # 用户自定义的请求信息 # JSON 格式的 ScheduleRequest 数据

# ----------------- URL 转为安全任务 ID -----------------
def normalize_url_for_task_id(url: str) -> str:
    # 使用urlparse解析URL为组件（协议、主机名、路径等）
    p = urlparse(url)
    # 检查URL是否包含有效的主机名（hostname），若无则抛出错误
    if not p.hostname:
        raise ValueError("Invalid URL: no hostname")
    
    # 提取主机名（如 example.com）
    host = p.hostname
    # 如果URL包含端口（如 :8080），则格式化为 "_端口号"，否则留空
    port = f"_{p.port}" if p.port else ""

    # 处理路径部分：
    # 1. 移除开头的斜杠 "/" 
    # 2. 将剩余斜杠 "/" 替换为下划线 "_"
    # 3. 如果路径为空（如根路径 "/"），则用 "root" 代替
    path = p.path.lstrip("/").replace("/", "_") or "root"

    # 组合主机名、端口、路径为原始任务ID字符串（格式：host_port_path）
    raw = f"{host}{port}_{path}"

    # 使用正则表达式清理非法字符：
    # 保留字母、数字、下划线 "_" 和短横线 "-"
    # 其他字符（如冒号、点、特殊符号等）统一替换为下划线
    return re.sub(r"[^\w\-]", "_", raw)

# ----------------- 通知客户端 -----------------
async def notify_client(url: str,req: ScheduleRequest, schedule_id: str, user_task: str):
    try:
        # 构建通知数据
        notification_data = {
            "scheduleReq": {
                "trigger_type": req.trigger_type,
                "trigger_args": req.trigger_args,
                "notification_url": str(req.notification_url),  # 转换为字符串
                "task_id": req.task_id,
                "msg_type": req.msg_type,
                "user_info_ext": req.user_info_ext
            },
            "task_id": user_task,
            "schedule_id": schedule_id
        }
        logger.info(f"notify_client: {notification_data}")
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=notification_data)
        if resp.status_code == 200:
            logger.info(f"[{user_task}/{schedule_id}] notification succeeded")
        else:
            logger.error(f"[{user_task}/{schedule_id}] status {resp.status_code}")
    except Exception as e:
        logger.error(f"[{user_task}/{schedule_id}] error sending to {url}: {e}", exc_info=True)

# ----------------- 创建调度任务 -----------------
@app.post("/schedule")
async def schedule_task(req: ScheduleRequest):
    try:
        logger.info(f"received a schedule_task: {req}")
        # 生成唯一任务 ID：规范化 URL + 用户提供的 task_id + UUID
        normalized = normalize_url_for_task_id(str(req.notification_url))
        job_id = f"{normalized}_{req.task_id}_{uuid.uuid4()}"

        # 根据请求类型创建触发器
        if req.trigger_type == "cron":
            trigger = CronTrigger(**req.trigger_args)  # 周期性任务（如每天8点）
        elif req.trigger_type == "interval":
            trigger = IntervalTrigger(**req.trigger_args)# 间隔任务（如每5秒）
        elif req.trigger_type == "date":
            trigger = DateTrigger(**req.trigger_args)  # 单次任务（指定日期时间）
        else:
            raise HTTPException(400, detail="Unsupported trigger type")

        # 向调度器添加任务
        job = scheduler.add_job(
            func=notify_client, # 要执行的异步函数
            trigger=trigger, # 触发规则
            id=job_id, # 任务唯一标识
            # 这里传入整个 req，让 notify_client 拿到原始请求
            args=[str(req.notification_url), req, job_id, req.task_id], # 传递给函数的参数
            replace_existing=False, # 禁止覆盖已有任务（避免ID冲突）
            misfire_grace_time=30  # 允许30秒内错过的任务被补发
        )
        #logger.info(f"Created job {job_id} with next run time: {job.next_run_time}")

        return JSONResponse(
            content={"message": "Scheduled", "job_id": job_id},
            status_code=200
        )
    except Exception as e:
        logger.error(f"Schedule creation failed: {e}")
        raise HTTPException(400, detail=str(e))

# ----------------- 查询所有任务 -----------------
@app.get("/schedules", response_model=List[ScheduleInfo])
def get_schedules():
    try:
        jobs = scheduler.get_jobs()
        result = []
        for job in jobs:
            trigger = job.trigger
            # 根据触发器类型提取参数
            if isinstance(trigger, CronTrigger):
                # CronTrigger 使用 fields 属性
                trigger_args = {field.name: str(field) for field in trigger.fields}
            elif isinstance(trigger, IntervalTrigger):
                # IntervalTrigger 提取 interval、start_date、end_date
                trigger_args = {
                    "interval": str(trigger.interval),
                    "start_date": str(trigger.start_date) if trigger.start_date else None,
                    "end_date": str(trigger.end_date) if trigger.end_date else None
                }
            elif isinstance(trigger, DateTrigger):
                # DateTrigger 提取 run_date
                trigger_args = {"run_date": str(trigger.run_date)}
            else:
                # 未知触发器类型，记录空字典并警告
                logger.warning(f"Unknown trigger type: {type(trigger).__name__}")
                trigger_args = {}

            # 从 job.args 中提取 ScheduleRequest 对象
            user_req_info = ''
            if len(job.args) >= 2 and isinstance(job.args[1], ScheduleRequest):
                req = job.args[1]  # req 是 args 中的第二个元素
                user_req_info = req.model_dump_json()  # 转换为 JSON 字符串
            else:
                logger.warning(f"No ScheduleRequest found in job {job.id} args")
                
            result.append(ScheduleInfo(
                id=job.id,
                task_id=job.args[3],
                trigger_type=trigger.__class__.__name__.lower().replace("trigger", ""),
                trigger_args=trigger_args,
                notification_url=str(job.args[0]),
                next_run_time=str(job.next_run_time) if job.next_run_time else "N/A",
                user_scheduleRequest= user_req_info
            ))
        logger.info(f"Retrieved {len(result)} schedules")
        return result
    except Exception as e:
        logger.exception("get_schedules failed")
        raise HTTPException(status_code=500, detail="Cannot retrieve schedules")

# ----------------- 删除任务 -----------------
@app.delete("/schedules/{job_id}")
def delete_schedule(job_id: str):
    try:
        scheduler.remove_job(job_id)
        return {"message": f"Job {job_id} deleted"}
    except JobLookupError:
        raise HTTPException(404, detail="Job not found")

# ----------------- 暂停任务 -----------------
@app.post("/schedules/{job_id}/pause")
def pause_schedule(job_id: str):
    try:
        scheduler.pause_job(job_id)
        return {"message": f"Job {job_id} paused"}
    except JobLookupError:
        raise HTTPException(404, detail="Job not found")

# ----------------- 恢复任务 -----------------
@app.post("/schedules/{job_id}/resume")
def resume_schedule(job_id: str):
    try:
        scheduler.resume_job(job_id)
        return {"message": f"Job {job_id} resumed"}
    except JobLookupError:
        raise HTTPException(404, detail="Job not found")

# ----------------- 启动 -----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SCHEDULER_SRV_PORT)
