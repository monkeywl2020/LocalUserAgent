import pika
import json

# RabbitMQ 消息队列服务器地址
RABBITMQ_SERVER_HOST = 'localhost'
# 消息队列的名称，使用具体的公司信息，不要重复即可，可以用公司缩写加编码
RABBITMQ_QUEUE_NAME = 'company_wl_msgque'

def callback(ch, method, properties, body):
    """处理消息的回调函数"""
    try:
        # 将接收到的消息转换为字典
        message = json.loads(body)
        print(f"接收到的消息: {message}")
    except Exception as e:
        print(f"处理消息时发生错误: {e}")

def consume_messages(queue_name=RABBITMQ_QUEUE_NAME, rabbitmq_host=RABBITMQ_SERVER_HOST):
    """从 RabbitMQ 消息队列中消费消息"""
    try:
        # 连接到 RabbitMQ
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbitmq_host))
        channel = connection.channel()

        # 声明队列
        channel.queue_declare(queue=queue_name, durable=True, arguments={'x-message-ttl': 604800000})  # TTL: 7天 (604800000 ms)

        # 设置消费回调
        channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)

        # 等待并消费消息
        print("开始等待消息...")
        channel.start_consuming()
    except Exception as e:
        print(f"连接 RabbitMQ 时发生错误: {e}")

def main():
    while True:
        # 持续监听消息队列并处理
        consume_messages()

# 队列处理出错可以使用命令删除队列重新创建队列，否则要等7天超时
# 删除队列命令：删除company_wl_msgque
#  sudo rabbitmqctl delete_queue company_wl_msgque

if __name__ == "__main__":
    main()
