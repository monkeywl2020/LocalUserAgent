import pika
import json

# RabbitMQ 消息队列服务器地址
RABBITMQ_SERVER_HOST = 'localhost'
# 消息队列的名称，使用具体的公司信息，不要重复即可，可以用公司缩写加编码
RABBITMQ_QUEUE_NAME = 'company_wl_msgque'

def get_input():
    """获取用户输入的联系人信息"""
    user_contact = input("请输入用户联系方式（例如：手机号或邮箱），输入 'exit' 退出程序：").strip()
    return user_contact

def create_message(user_contact, company_info, chat_history):
    """创建消息内容，按指定格式生成消息"""
    message = {
        "contact_type": "wx",
        "user_contact": user_contact,
        "company_info": company_info,
        "chat_history": chat_history
    }
    return message

def send_message_to_rabbitmq(message, queue_name= RABBITMQ_QUEUE_NAME, rabbitmq_host= RABBITMQ_SERVER_HOST):
    """将消息发送到 RabbitMQ 队列"""
    try:
        # 连接到 RabbitMQ
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbitmq_host))
        channel = connection.channel()

        # 声明队列，设置队列的 TTL 为 7 天
        channel.queue_declare(queue=queue_name, durable=True, arguments={'x-message-ttl': 604800000})  # TTL: 7天 (604800000 ms)

        # 发送消息
        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                content_type='application/json'
            )
        )
        print("消息发送成功！")
    except Exception as e:
        print(f"发送消息时发生错误: {e}")
    finally:
        # 关闭连接
        connection.close()

def main():
    # 设置公司信息和聊天历史（根据需要修改或从配置文件读取）
    company_info = "公司信息：BY Corp.，主营产品为云pc和数字人，致力于创新科技。"
    chat_history = "用户：你好！\n客服：您好，有什么可以帮助您的？\n用户：我需要了解数字人产品的价格。"
    
    while True:
        # 获取用户输入
        user_contact = get_input()

        if user_contact.lower() == 'exit':
            print("退出程序。")
            break

        # 创建消息
        message = create_message(user_contact, company_info, chat_history)

        # 发送消息到 RabbitMQ
        send_message_to_rabbitmq(message)

if __name__ == "__main__":
    main()
