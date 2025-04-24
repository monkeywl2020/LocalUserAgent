import aio_pika
import json
import asyncio
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RabbitMQ 配置
RABBITMQ_SERVER_HOST = '172.21.30.231'  # 替换为远程 RabbitMQ 服务器地址
RABBITMQ_PORT = 5672  # 默认端口，可根据需要修改
RABBITMQ_USERNAME = 'wllocaluserproducer'
RABBITMQ_PASSWORD = 'LocalAgent20250425!'
RABBITMQ_QUEUE_NAME = 'company_wl_msgque'

class RabbitMQAsyncProducer:
    def __init__(self, host=RABBITMQ_SERVER_HOST, port=RABBITMQ_PORT, 
                 username=RABBITMQ_USERNAME, password=RABBITMQ_PASSWORD, 
                 queue_name=RABBITMQ_QUEUE_NAME):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.queue_name = queue_name
        self.connection = None
        self.channel = None

    async def connect(self):
        """异步连接到 RabbitMQ"""
        try:
            logger.info(f"Connecting to RabbitMQ server: {self.host}")
            # 使用凭据建立连接
            self.connection = await aio_pika.connect_robust(
                f"amqp://{self.username}:{self.password}@{self.host}:{self.port}/"
            )
            logger.info(f"RabbitMQ connection established: {self.connection}")
            self.channel = await self.connection.channel()
            # 声明队列，设置 TTL 为 7 天
            await self.channel.declare_queue(
                self.queue_name, 
                durable=True, 
                arguments={'x-message-ttl': 604800000}  # TTL: 7天
            )
            logger.info(f"Queue {self.queue_name} declared")
        except Exception as e:
            logger.error(f"连接 RabbitMQ 失败: {e}")
            raise

    async def send_message(self, message):
        """异步发送消息到 RabbitMQ"""
        try:
            if not self.channel:
                await self.connect()
            # 将消息转换为 JSON 字节
            message_body = json.dumps(message).encode()
            # 创建消息
            exchange = await self.channel.get_exchange('')
            await exchange.publish(
                aio_pika.Message(
                    body=message_body,
                    content_type='application/json'
                ),
                routing_key=self.queue_name
            )
            logger.info("消息发送成功！")
            return True
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False

    async def close(self):
        """关闭连接"""
        try:
            if self.channel:
                await self.channel.close()
            if self.connection:
                await self.connection.close()
            logger.info("RabbitMQ connection closed")
        except Exception as e:
            logger.error(f"关闭 RabbitMQ 连接失败: {e}")

def create_message(user_contact, company_info, chat_history):
    """创建消息内容，按指定格式生成消息"""
    message = {
        "contact_type": "wx",
        "user_contact": user_contact,
        "company_info": company_info,
        "chat_history": chat_history
    }
    return message

async def main():
    # 设置公司信息和聊天历史
    company_info = "公司信息：BY Corp.，主营产品为云pc和数字人，致力于创新科技。"
    chat_history = "用户：你好！\n客服：您好，有什么可以帮助您的？\n用户：我需要了解数字人产品的价格。"
    
    # 初始化 RabbitMQ 生产者
    producer = RabbitMQAsyncProducer()

    try:
        # 连接 RabbitMQ
        await producer.connect()

        while True:
            # 获取用户输入
            user_contact = input("请输入用户联系方式（例如：手机号或邮箱），输入 'exit' 退出程序：").strip()

            if user_contact.lower() == 'exit':
                logger.info("退出程序")
                break

            # 创建消息
            message = create_message(user_contact, company_info, chat_history)

            # 发送消息
            await producer.send_message(message)

    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    finally:
        # 清理连接
        await producer.close()

if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())