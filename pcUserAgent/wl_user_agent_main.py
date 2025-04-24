import sys
import os
import asyncio
import time
import httpx
import json
from typing import Any, Dict, Optional, Union,Literal
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import aio_pika
from datetime import datetime, timedelta
from pydantic import BaseModel

from loguru import logger

# 将项目的根目录添加到 sys.path 中
a = os.path.abspath(__file__)
print(a,flush=True)
b = os.path.dirname(a)  #返回上一级目录部分，去掉文件名
print(b,flush=True)
#sys.path.append(b)
c = os.path.dirname(b) #返回上一级目录部分
print(c,flush=True)

# 将上一级目录加入 添加到搜索路径中也 就是examples的上级目录
sys.path.append(c)
print(sys.path,flush=True)

from src.msg.message import Message
from src.agents.user_agent import UserAgent

# 默认配置
DEFAULT_CONFIG = {
    "wluseragent_filelog_enable": 0, # 0:日志输出到前台，1: 日志输出到文件
    "local_digitalman_id": 'wl_useragent_test',
    "rabbitmq_server_host":'localhost',
    "rabbitmq_que_name":'company_wl_msgque',
    "rabbitmq_user":'wllocaluserconsume',
    "rabbitmq_password":'LocalAgent20250425!',
    "local_serv_port":10009,
    "agent_addwx_srv_url":'http://localhost:7788/v1/wx/add',
    "agent_wxchat_srv_url":'http://localhost:7788/v1/wx/chat',
    "psuse_tool_srv_url":'http://localhost:10010/v1/serve',
    "apscheduler_srv_url":"http://localhost:10005/schedule",
    "apscheduler_base_url":"http://localhost:10005",
    "apscheduler_day":1,
    "apscheduler_hour":9,
    "apscheduler_minute":0,
    "apscheduler_retry_count":3,
    "server_llm":{
        "model_type": "postapi",
        'base_url': 'http://localhost:7788/v1/chat/completions',  
        'api_key': 'EMPTY'
    }
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
WL_USER_AGENT_LOG_OPEN = config.get("wluseragent_filelog_enable", DEFAULT_CONFIG["wluseragent_filelog_enable"])
# 动态构造相对路径
if WL_USER_AGENT_LOG_OPEN:
    log_dir = os.path.join("./", "usragentlog")
    log_path = os.path.join(log_dir, "wluseragent.log")
    # 目录不存在时会报错，需先创建：
    os.makedirs(log_dir, exist_ok=True)
    # 移除默认控制台输出
    logger.remove()

    # 配置日志文件
    logger.add(log_path, rotation="20 MB", retention=5)
#-----------------------------------------------------------------


#本 local agent所代理的用户的id
LOCAL_USER_ID = config.get("local_digitalman_id", DEFAULT_CONFIG["local_digitalman_id"]) #'wl_useragent_test'

#-------------------------------------------------
# RabbitMQ 消息队列服务器地址
#RABBITMQ_SERVER_HOST = '172.21.30.231'
RABBITMQ_SERVER_HOST = config.get("rabbitmq_server_host", DEFAULT_CONFIG["rabbitmq_server_host"])  # 'localhost'
# 消息队列的名称，使用具体的公司信息，不要重复即可，可以用公司缩写加编码
RABBITMQ_QUEUE_NAME = config.get("rabbitmq_que_name", DEFAULT_CONFIG["rabbitmq_que_name"]) # 'company_wl_msgque'
RABBITMQ_USER = config.get("rabbitmq_user", DEFAULT_CONFIG["rabbitmq_user"]) # 'wllocaluserconsume'
RABBITMQ_PASSWORD = config.get("rabbitmq_password", DEFAULT_CONFIG["rabbitmq_password"]) # 'LocalAgent20250425!'
#-------------------------------------------------
# 本地fast api服务监听端口
FASTAPI_PORT = config.get("local_serv_port", DEFAULT_CONFIG["local_serv_port"]) # 10009

# 添加微信好友功能端点URL
ADD_WX_DST_URL = config.get("agent_addwx_srv_url", DEFAULT_CONFIG["agent_addwx_srv_url"])  # 'http://localhost:7788/v1/wx/add'
# 与添加微信好友聊天功能端点URL
CHAT_WX_DST_URL = config.get("agent_wxchat_srv_url", DEFAULT_CONFIG["agent_wxchat_srv_url"])  # 'http://localhost:7788/v1/wx/chat'

# 与添加微信好友聊天功能端点URL
PC_USE_DST_URL = config.get("psuse_tool_srv_url", DEFAULT_CONFIG["psuse_tool_srv_url"])   # 'http://localhost:10010/v1/serve'
#-------------------------------------------------
APSCHEDULER_URL = config.get("apscheduler_srv_url", DEFAULT_CONFIG["apscheduler_srv_url"])   # "http://localhost:10005/schedule"  # 替换为实际 APScheduler 的 URL
APSCHEDULER_BASE_URL = config.get("apscheduler_base_url", DEFAULT_CONFIG["apscheduler_base_url"]) # "http://localhost:10005"  # 替换为实际 APScheduler 的 URL
SCHEDULE_DAY = config.get("apscheduler_day", DEFAULT_CONFIG["apscheduler_day"]) # 0表示当天调度，1表示明天，2表示后天，以此类推
# RETRY_HOUR + RETRY_MINUTE 表示 重试时间，比如 10:15 表示 10 点 15 分
RETRY_HOUR = config.get("apscheduler_hour", DEFAULT_CONFIG["apscheduler_hour"])   # 默认重试时间为早上 9 点
RETRY_MINUTE = config.get("apscheduler_minute", DEFAULT_CONFIG["apscheduler_minute"])  
RETRY_COUNT = config.get("apscheduler_retry_count", DEFAULT_CONFIG["apscheduler_retry_count"])   # 默认重试次数为 3
#-------------------------------------------------

# 定义userAgent的 模型服务配置
llm_cfg1 = {
    "model_type": "postapi",
    'base_url': 'http://172.200.2.21/ai-multimodal/v1/chat/completions2',  
    'api_key': 'EMPTY'
}

llm_cfg2 = {
    "model_type": "postapi",
    'base_url': 'http://localhost:7788/v1/chat/completions',  
    'api_key': 'EMPTY'
}

llm_cfg = config.get("server_llm", DEFAULT_CONFIG["server_llm"]) # 大模型配置

# APScheduler 调度请求模型
class ScheduleRequest(BaseModel):
    trigger_type: str                # 触发器类型: "cron" | "interval" | "date"
    trigger_args: Dict[str, Any]     # 触发器参数，例如 {"hour":12, "minute":0}
    notification_url: str       # 通知回调地址
    task_id: str                   # 用户自定义任务标识
    msg_type: str                  # 用户定义触发这个调度任务的消息类型（例如：添加微信好友 add_wx_friend ）
    user_info_ext: Dict[str, Any]    # 存放用户自定义扩展信息，包含触发次数信息。

# 定义lifespan上下文管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化资源
    logger.info("Starting application...")
    app.state.wl_user_agent = localUserAgent(
        name='wl_useragent_test',
        description='测试用户代理',
        rabbitmq_host=RABBITMQ_SERVER_HOST,
        queue_name=RABBITMQ_QUEUE_NAME,
        llm_config=llm_cfg
    )
    
    # 启动RabbitMQ消费者作为后台任务
    app.state.rabbitmq_task = asyncio.create_task(app.state.wl_user_agent.start_rabbitmq_consumer())
    logger.info("Application started successfully")
    yield  # 应用运行阶段
    
    # 关闭时清理资源
    logger.info("Shutting down application...")
    app.state.rabbitmq_task.cancel()
    try:
        await app.state.rabbitmq_task
    except asyncio.CancelledError:
        logger.info("RabbitMQ consumer task cancelled")
    
    # 关闭RabbitMQ连接
    await app.state.wl_user_agent.rabbitmq_client.close()
    logger.info("Application shutdown complete")

# 初始化FastAPI应用并绑定生命周期
app = FastAPI(lifespan=lifespan)

#------------------------------------------------------
#  消息队列RabbitMQ客户端，这个客户端是消费者用来处理消息的
#------------------------------------------------------
class RabbitMQClient:
    def __init__(self, host='localhost', queue_name='message_queue'):
        self.host = host
        self.queue_name = queue_name
        # 信号量限制了 同时可以处理的消息数，但它不会限制 消息的接收。
        # 也就是说，RabbitMQ 依然会接收到所有消息，只不过只有最大并发数个消息会同时被处理，其他的会排队等待。
        self.semaphore = asyncio.Semaphore(10)  # 限制并发任务的最大数量
        self.user_agent = None  # 将在 localUserAgent 中设置
        self.job_id_mapping = {}  # Mapping of wx_id to job_id
        self.connection = None  # 存储 RabbitMQ 连接对象

    async def consume_messages(self):
        """异步消费消息队列中的消息"""
        try:
            logger.info(f"Connecting to RabbitMQ server: {self.host}")
            self.connection = await aio_pika.connect_robust(f'amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{self.host}')# 建立 RabbitMQ 连接
            logger.info(f"RabbitMQ connection established: {self.connection}")
            async with self.connection:
                channel = await self.connection.channel()  # 创建频道
                queue = await channel.declare_queue(
                    self.queue_name, 
                    durable=True,
                    arguments={'x-message-ttl': 604800000} # 消息存活时间 7 天
                )  # 声明队列

                async for message in queue: # 异步遍历队列中的消息
                    async with message.process():
                        await self.Msgcallback(message)

        except ConnectionError as e:
            logger.error(f"网络连接失败: {e}")
        except AMQPError as e:
            logger.error(f"AMQP 错误: {e}")
        except Exception as e:
            logger.error(f"未知错误: {e}")

    async def Msgcallback(self, message):
        """处理消息"""
        try:
            logger.info(f"Received message: {message.body}")
            message_dict = json.loads(message.body)
            logger.info(f"Received message_dict: {message_dict}")
            # 使用信号量限制并发
            async with self.semaphore:#这个限制并发调用个数
                await self.process_message(message_dict)
        except json.JSONDecodeError:
            logger.error("Invalid JSON message received from RabbitMQ")
        except Exception as e:
            logger.error(f"Error while processing message: {e}")

    async def process_message(self, message: Dict):
        """处理消息并调用 UserAgent 进行交互"""
        try:
            logger.info(f"Processing message: {message}")
            # 假设 wlUserAgent 内部已经初始化了 UserAgent 实例
            #  
            response = await self.user_agent.handle_rabbitmq_input(message)
            logger.info(f"Processed message: {response}")
            await self.send_to_pc_use(message, response, "add_wx")  # 发送结果给 pcuse
        except Exception as e:
            logger.error(f"Error while processing message: {e}")
        
    # 发送消息给 pcuse 工具
    async def send_to_pc_use(self, message: Dict, msg_content: str, msg_type: str):
        """将结果异步发送给其他服务（如 HTTP 请求）"""
        # 这里面需要实现两个逻辑，一个将消息发送给apscheduler，定时到第二天早上9点，如果这期间加好友成功需要取消apscheduler的调度。
        # 如果没添加成功则第二天9点继续触发添加好友动作，最多添加三次。
        # 另一个逻辑是将消息发送给pcuse工具，pcuse工具是一个pc服务，pcuse工具会根据用户的联系方式和 给用户输入的内容发送给 pcuse工具
        try:
            # 将用户的联系方式和 给用户输入的内容发送给 pcuse工具
            pc_use_data = {
                "type": msg_type,  # 消息类型（add_wx 或 chat）
                "data": {
                    "sessionid": message.get('sessionid', 'session-id-xxx'),  # 会话 ID
                    "content": msg_content,  # 消息内容（响应）
                    "ext": {"wx_id": message.get('user_contact', message.get('wx_id', ''))}  # 扩展信息，包含微信名称
                }
            }
            async with httpx.AsyncClient() as client:  # 创建异步 HTTP 客户端
                resp = await client.post(PC_USE_DST_URL, json=pc_use_data)  # 发送 POST 请求
                if resp.status_code == 200:
                    logger.info(f"Sent to pcuse: {pc_use_data}")
                else:
                    logger.error(f"Failed to send to pcuse, status: {resp.status_code}, response: {resp.text}")
        except Exception as e:
            logger.error(f"Error while sending to pc use: {e}")  # 记录发送过程中的错误

        # 2. 发送定时任务给 APScheduler
        # 如果是添加微信好友消息，检查 retry_count 并创建调度任务
        try:
            if msg_type == "add_wx":
                # 首次创建调度任务的时候，message是没有 retry_count 参数的，没有说明是首次创建，不是调度回调的时候的消息 
                # 这里有2种情况：
                # 1）来自RabbitMQ的消息，这个是创建调度任务的时候调用的。
                # 2）来自调度任务notify的消息，这个是调度时候设置的消息，消息里面有retry_count参数，这个参数如果为0则表示不需要调度了
                retry_count = message.get('retry_count', RETRY_COUNT)  # 获取重试次数，如果没有重试次数则获取默认的次数
                # 如果获取到了次数，就判断这个次数是否大于0，大于0才创建调度任务，否则不创建
                if retry_count > 0:
                    job_id = await self.schedule_retry(message, msg_content)  # 创建调度任务并获取 job_id
                    wx_id = message.get('user_contact', message.get('wx_id', ''))
                    if job_id:
                        self.job_id_mapping[wx_id] = job_id
                        logger.info(f"Scheduled retry for {wx_id} with job_id {job_id}")
                    else:
                        logger.error(f"Failed to schedule retry for {wx_id}")
                else:
                    logger.info(f"Retry count for {message.get('user_contact', message.get('wx_id', ''))} is 0, skipping scheduling.")
        except Exception as e:
            logger.error(f"Error while sending to pc use: {e}")  # 记录发送过程中的错误

    # 创建 APScheduler 调度任务
    async def schedule_retry(self, message: Dict, response: str) -> Optional[str]:
        try:
            # 计算第二天 9 点的触发时间
            now = datetime.now()
            current_minute = now.minute
            new_minute = min(current_minute + RETRY_MINUTE, 59) # 重试的分钟回以当前的分钟为基准，这样就能进行测试。不考虑溢出情况
            next_day = now + timedelta(days=SCHEDULE_DAY)
            trigger_time = next_day.replace(hour=RETRY_HOUR, minute=new_minute, second=0, microsecond=0)
            trigger_args = {"run_date": trigger_time.isoformat()}  # 使用 ISO 格式指定触发时间
            task_id = f"retry_add_wx_{message.get('user_contact', '')}_{int(time.time())}"  # 生成唯一任务 ID
            user_info_ext = {
                "wx_id": message.get('user_contact', message.get('wx_id', '')),  # 微信用户名
                "retry_count": message.get('retry_count', RETRY_COUNT),  # 剩余重试次数
                "company_info": message.get('company_info', ''),  # 公司信息
                "chat_history": message.get('chat_history', ''),  # 聊天历史
                "response": response,  # 大模型响应
                "sessionid": message.get('sessionid', 'session-id-xxx')  # 会话 ID
            }
            schedule_data = ScheduleRequest(
                trigger_type="date",  # 使用 date 触发器
                trigger_args=trigger_args,  # 触发时间参数
                notification_url=f"http://localhost:{FASTAPI_PORT}/notify",  # 通知回调地址
                task_id=task_id,  # 任务 ID
                msg_type="add_wx_friend",  # 消息类型
                user_info_ext=user_info_ext  # 用户扩展信息
            ).model_dump()
            logger.info(f"Scheduling retry {schedule_data} to {APSCHEDULER_URL}")
            async with httpx.AsyncClient() as client:  # 创建异步 HTTP 客户端
                resp = await client.post(APSCHEDULER_URL, json=schedule_data)  # 发送调度请求
                logger.info(f"APScheduler response: {resp.status_code}, {resp.text}")
                # 响应的内容是 {"message": "Scheduled", "job_id": job_id}
                if resp.status_code == 200:  # 检查响应状态码
                    # 解析响应中的 job_id
                    try:
                        resp_json = resp.json()
                        job_id = resp_json.get("job_id")
                        if job_id:
                            logger.info(f"Scheduled retry task with job_id: {job_id}")
                            return job_id  # 返回 APScheduler 生成的 job_id
                        else:
                            logger.error("job_id not found in APScheduler response")
                            return None
                    except json.JSONDecodeError:
                        logger.error("Invalid JSON response from APScheduler")
                        return None
                else:
                    logger.error(f"Failed to schedule retry, status: {resp.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Error while scheduling retry: {e}")  # 记录调度过程中的错误

    # 关闭 RabbitMQ 连接
    async def close(self):
        """关闭 RabbitMQ 连接"""
        try:
            if hasattr(self, 'connection') and self.connection and not self.connection.is_closed:
                await self.connection.close()
                logger.info("RabbitMQ connection closed")
            else:
                logger.info("No RabbitMQ connection to close or already closed")
        except Exception as e:
            logger.error(f"Error while closing RabbitMQ connection: {e}")
            return None

# 本地用户代理类
class localUserAgent:
    def __init__(self, 
            name: str,
            description: str = None,
            rabbitmq_host: str ='localhost', 
            queue_name: str = 'message_queue',
            llm_config: Optional[Union[Dict, Literal[False]]] = None,
        ):
        # 初始化 RabbitMQ 客户端，创建实例
        self.rabbitmq_client = RabbitMQClient(host=rabbitmq_host, queue_name=queue_name)
        # 初始化 UserAgent 实例
        self.user_agent = UserAgent(
            name=name,
            llm_config=llm_config,
            description=description
        )
        self.rabbitmq_client.user_agent = self  # 设置 user_agent

    async def start_rabbitmq_consumer(self):
        """启动 RabbitMQ 消费者"""
        await self.rabbitmq_client.consume_messages()

    # 处理来自 pcuse 的消息
    async def handle_pcuse_input(self, message: Dict) -> Dict:
        """与大模型进行交互，处理用户输入"""
        dst_url = ''
        user_message = ''  # 用户消息内容
        ext_to_agent = {}  # 给后台服务器agent的扩展信息
        ext_to_pcuse = {"wx_id": message.get("data", {}).get("ext", {}).get("wx_id", "")}# 给pcuse的扩展信息
        sessionid = message.get("data", {}).get("sessionid", "session-id-xxx")  # 会话 ID
        msg_type = message.get("type", "")  # 获取消息类型

        if msg_type == "chat":  # 聊天消息
            user_message = message.get("data", {}).get("content", "")  # 用户输入内容
            # 构造扩展信息，这个是agent端使用的，其中msg_type 是用来给agent做合法性判断用的
            # 聊天就是  "msg_type":"chat_with_wx_friend"
            ext_to_agent = {"msg_type":"chat_with_wx_friend","wx_id": message.get("data", {}).get("ext", {}).get("wx_id", "")}  # 扩展信息
            dst_url = CHAT_WX_DST_URL  # 聊天目标 URL
        elif msg_type == "add_wx_result":  # 添加好友结果
            user_message = ""  # 无需用户消息
            # 聊天就是  "msg_type":"add_wx_friend"
            ext_to_agent = {"msg_type":"add_wx_friend_success", "wx_id": message.get("data", {}).get("ext", {}).get("wx_id", "")}  # 扩展信息
            dst_url = CHAT_WX_DST_URL  # 添加好友目标 URL
            await self.delete_apscheduler_task(ext_to_agent["wx_id"])  # 删除定时任务
        else:
            logger.error(f"Unknown msg_type from pc_use: {msg_type}")  # 未知消息类型的错误日志
            return {"code": 400, "msg": f"Unknown msg_type: {msg_type}", "type": msg_type, "data": {}}
        
        llm_rsp = await self.get_llm_response(user_message, ext_to_agent, dst_url, sessionid)  # 获取大模型响应
        pcuse_rsp = {
            "code": 200,
            "msg": "正常",
            "type": msg_type,  # 消息类型
            "data": {
                "sessionid": sessionid,  # 会话 ID
                "content": llm_rsp,  # 大模型响应内容
                "ext": ext_to_pcuse  # 扩展信息
            }
        }
        return pcuse_rsp

    # 处理来自 RabbitMQ 的消息
    async def handle_rabbitmq_input(self, message: Dict) -> str:
        user_message = ""  # 无需用户消息
        contact_type = message.get('contact_type', '')  # 联系方式类型
        user_contact = message.get('user_contact', '')  # 用户联系方式
        company_info = message.get('company_info', '')  # 公司信息
        chat_history = message.get('chat_history', '')  # 聊天历史
        sessionid = message.get('sessionid', 'session-id-xxx')  # 会话 ID
        # 目前只有添加微信好友的功能
        if contact_type == "wx":  # 如果是微信联系方式
            msg_type = "add_wx_friend"
        else:
            logger.error(f"Unknown contact_type: {contact_type}")  # 未知联系方式类型的错误日志
            return ""
        # 下面内容是要发给 nuwa agent进行处理的。
        ext = {"msg_type": msg_type, "user_contact": user_contact, "company_info": company_info, "chat_history": chat_history}  # 扩展信息
        dst_url = ADD_WX_DST_URL  # 添加好友目标 URL
        return await self.get_llm_response(user_message, ext, dst_url, sessionid)  # 获取大模型响应

    # 处理来自 APScheduler 的消息
    async def handle_schedule_input(self, message: Dict) -> Dict:
        schedule_req = message.get("scheduleReq", {})  # 定时任务请求
        msg_type = schedule_req.get("msg_type", "")  # 消息类型
        user_info_ext = schedule_req.get("user_info_ext", {})  # 用户信息扩展
        if msg_type == "add_wx_friend":  # 添加好友任务
            user_contact = user_info_ext.get("wx_id", "")  # 用户联系方式
            response = user_info_ext.get("response", "")  # 获取之前存储的大模型响应
            sessionid = user_info_ext.get("sessionid", "session-id-xxx")  # 会话 ID
            retry_count = user_info_ext.get("retry_count", 0)  # 获取剩余重试次数
            next_retry_count = max(retry_count - 1, 0) # retry_count 此时要减1。并确保 retry_count >= 0
            if retry_count > 0:  # 如果
                # 构造发送给 pcuse 的消息
                pc_use_message = {
                    "sessionid": sessionid,
                    "user_contact": user_contact,
                    "retry_count": next_retry_count,
                    "company_info": user_info_ext.get("company_info", ""),
                    "chat_history": user_info_ext.get("chat_history", "")
                }
                await self.rabbitmq_client.send_to_pc_use(pc_use_message, response, "add_wx")  # 发送给 pcuse
                return {
                    "code": 200,
                    "msg": "Notification processed",
                    "type": msg_type,
                    "data": {"sessionid": sessionid, "content": response, "ext": {"wx_id": user_contact}}
                }
            else:
                logger.info(f"Retry count exhausted for {user_contact}")  # 重试次数耗尽的日志
                return {
                    "code": 200,
                    "msg": "Retry count exhausted",
                    "type": msg_type,
                    "data": {"sessionid": sessionid, "content": "", "ext": {"wx_id": user_contact}}
                }
        else:
            logger.error(f"Unknown msg_type from apscheduler: {msg_type}")  # 未知消息类型的错误日志
            return {"code": 400, "msg": f"Unknown msg_type: {msg_type}", "type": msg_type, "data": {}}

    # 获取大模型响应的通用方法
    async def  get_llm_response(self, user_message: str, ext: Dict, dst_url: str, sessionid: str) -> str:
        messages = [
            {
                'type': 'agent',  # 消息类型
                'token': sessionid,  # 认证令牌
                'userid': LOCAL_USER_ID,  # 用户 ID
                'data': {
                    'sessionid': sessionid,  # 会话 ID
                    'intent': 'UNKNOWN',  # 意图未知
                    'knowledgeid': 'my_rag_partition',  # 知识库 ID
                    'content': user_message,  # 用户消息内容
                    'ext': ext  # 扩展信息
                }
            }
        ]

        logger.info(f"localUserAgent::get_llm_response: =======>{messages}") 
        first_packet_logged = False  # 标记是否记录了首个数据包
        start_time = time.perf_counter()  # 记录开始时间
        abc = await self.user_agent.a_generate_rsp(messages, dst_url=dst_url)  # 调用用户代理生成响应
        text = ''  # 存储响应文本
        async for response in abc:  # 异步处理响应流
            #----------------------------------------------------------
            # 大模型没响应的时候打开这个日志 (勿删)
            #logger.info(f"raw Response: =======>{response}")  # 记录原始响应
            #----------------------------------------------------------
            if response and response[0].content != '':  # 检查响应内容是否为空
                if not first_packet_logged:  # 如果是首个数据包
                    end_time = time.perf_counter()  # 记录结束时间
                    elapsed_time = end_time - start_time  # 计算耗时
                    logger.info(f"user--->Time to first packet: {elapsed_time:.3f} seconds")  # 记录首包耗时
                    first_packet_logged = True  # 更新标记
                text += response[0].content  # 拼接响应内容
                #----------------------------------------------------------
                # 大模型没响应的时候打开这个日志(勿删)
                #logger.info(f"user--->Response: {text}")  # 记录当前响应
                #----------------------------------------------------------
        logger.info(f"user Response: {text}")  # 记录最终响应
        think_content, response_content = self.separate_think_and_response(text)  # 分离思考和响应部分
        logger.info(f"user think_content:{think_content}  response_content: {response_content}")  # 记录分离结果
        return response_content  # 返回响应内容

    def separate_think_and_response(self, text):
        think_end_marker = "</think>\n\n"
        end_pos = text.rfind(think_end_marker)
        
        if end_pos != -1:
            think_part = text[:end_pos]
            response_part = text[end_pos + len(think_end_marker):]
            return think_part, response_part
        else:
            return "", text

    # 删除 APScheduler 定时任务
    async def delete_apscheduler_task(self, wx_id: str):
        try:
            job_id = self.rabbitmq_client.job_id_mapping.get(wx_id)
            if job_id:
                async with httpx.AsyncClient() as client:
                    resp = await client.delete(f"{APSCHEDULER_BASE_URL}/schedules/{job_id}")
                    if resp.status_code == 200:
                        logger.info(f"Deleted APScheduler task for {wx_id} with job_id {job_id}")
                        del self.rabbitmq_client.job_id_mapping[wx_id]
                    else:
                        logger.error(f"Failed to delete task, status: {resp.status_code}")
            else:
                logger.warning(f"No job_id found for wx_id {wx_id}")
        except Exception as e:
            logger.error(f"Error while deleting APScheduler task: {e}")

#--------------------------------------            
# 1. 处理大模型交互的接口 
# 这个是pc use工具的服务端口，所有来自 pc use的消息都是通过这个接口处理的，从pc use的接口有
#   1）添加好友成功消息 
#   2）wx好友聊天消息
#--------------------------------------
@app.post("/v1/serve")
async def receive_message(request: Request):
    """用于与大模型进行交互的接口"""
    try:
        data = await request.json()  # 解析 JSON 数据
        logger.info(f"Received pcuse input: {data}")
        wl_user_agent = request.app.state.wl_user_agent
        response = await wl_user_agent.handle_pcuse_input(data)
        return JSONResponse(content=response)
    except json.JSONDecodeError:
        logger.error("Invalid JSON input")
        return JSONResponse(content={"code": 400, "msg": "Invalid JSON input", "type": "", "data": {}}, status_code=400)
#--------------------------------------
# 2. 处理调度任务通知接口
#  这个接口是给 apscheduler 通知调用的，这里可以获取到当前是什么任务的通知，通知里面含所有信息，例如是什么消息触发的调度任务，
# 触发这个调度任务的wx用户信息等等，例如添加微信好友的msg。添加的是哪个wx好友，wx好友id信息等
#--------------------------------------
@app.post("/notify")
async def receive_notification(request: Request):
    """处理来自 APScheduler 的调度任务通知"""
    try:
        data = await request.json()
        logger.info(f"Received APScheduler notification: {data}")
        wl_user_agent = request.app.state.wl_user_agent
        response = await wl_user_agent.handle_schedule_input(data)
        return JSONResponse(content=response)
    except json.JSONDecodeError:
        logger.error("Invalid JSON notification received")
        return JSONResponse(
            content={"code": 400, "msg": "Invalid JSON notification", "type": "", "data": {}},
            status_code=400
        )

# 启动 FastAPI 和 RabbitMQ 消费者
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=FASTAPI_PORT)

