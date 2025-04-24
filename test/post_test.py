import gradio as gr
import requests
import json
import time
from typing import Generator

# 服务器地址
SERVER_URL = "http://172.200.2.21/ai-multimodal/v1/chat/completions2"

# 处理流式响应的函数
def stream_response(message: str, history: list) -> Generator[str, None, None]:
    # 设置固定的 user_id 和 session_id
    user_id = "wl_useragent_test"
    token = "121213313"
    session_id = "session1"
    knowledgeid =  "my_rag_partition"

    # 构造请求数据
    payload = {
        "type": "agent",
        "token": token,
        "userid": user_id,
        "data": {
            "sessionid": session_id,
            "intent": "UNKNOWN",  # 固定值为 "A"
            "knowledgeid": knowledgeid,  # 替换为实际知识库 ID
            "content": message  # 用户输入的内容
        }
    }
    
    #print(f"===========stream_response:{message}")
    # 记录开始时间
    start_time = time.time()

    # 发送 POST 请求，启用流式响应
    try:
        response = requests.post(
            SERVER_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            stream=True
        )
        response.raise_for_status()

        # 处理流式响应
        current_response = ""
        first_packet_time = None  # 用于记录首条报文时间

        for line in response.iter_lines():
            if line:
                # 解码并移除 "data: " 前缀
                decoded_line = line.decode("utf-8").replace("data: ", "")
                #print(f"=====decoded_line:{decoded_line}")
                try:
                    data = json.loads(decoded_line)
                    content = data.get("data", {}).get("content", "") 

                    # 更新当前响应
                    current_response += content

                    # 处理 think 标签
                    if current_response:
                        # 设置蓝色样式直到 </think> 出现的位置
                        if "</think>" in current_response:
                            before_think, after_think = current_response.split("</think>", 1)
                            # 替换换行符为 <br>
                            before_think = before_think.strip().replace("\n", "<br>")
                            formatted_content = (
                                f"<span style='color:blue'>{before_think.strip()}</span> "  # 蓝色部分
                                f"\n\n"
                                f"{after_think.strip()}"  # 恢复默认颜色
                            )
                        else:
                            # 将回车换行替换成 <br>
                            display_rsp =  current_response.strip().replace("\n", "<br>")
                            # 如果没有 </think>，全部内容设置为蓝色
                            formatted_content = f"<span style='color:blue'>{display_rsp}</span>"

                        # 移除 <think> 和 </think> 标签
                        formatted_content = formatted_content.replace("<think>", "").replace("</think>", "")


                    # 如果是首条报文，记录时间
                    if first_packet_time is None:
                        first_packet_time = time.time() - start_time
                        yield f"{formatted_content}<br><br>首条报文响应时间: {first_packet_time:.2f}秒"
                    else:
                        #print(f"=====yield:{current_response}")
                        # 后续报文只更新内容，不重复显示时间
                        yield f"{formatted_content}<br><br>首条报文响应时间: {first_packet_time:.2f}秒"
                except json.JSONDecodeError:
                    continue
    except requests.RequestException as e:
        yield f"请求失败: {str(e)}"

# Gradio 聊天界面
def create_chat_interface():
    with gr.Blocks(title="大模型响应速度测试") as demo:
        gr.Markdown("# 大模型响应速度测试工具")
        gr.Markdown("输入消息内容，测试模型的流式响应速度。蓝色文字为 `think` 内容，仅显示首条报文时间。")

        # 使用 Chatbot 组件展示对话
        chatbot = gr.Chatbot(label="对话历史", height=400)

        # 输入框和发送按钮
        msg = gr.Textbox(label="输入消息", placeholder="请输入消息内容，例如：你好")
        submit_btn = gr.Button("发送")

        # 定义流式响应的逻辑
        def respond(message, chat_history):
            # 将用户消息添加到历史
            chat_history.append([message, None])
            # 生成流式响应
            for response in stream_response(message, chat_history):
                chat_history[-1][1] = response  # 更新最后一条消息的响应
                #print(f"==========chat_history:{chat_history}")
                yield chat_history, ""  # 返回更新后的历史记录和空字符串以清空输入框

        # 点击发送按钮触发响应，并清空输入框
        submit_btn.click(
            fn=respond,
            inputs=[msg, chatbot],
            outputs=[chatbot, msg],  # 输出到 chatbot 和 msg，清空输入框
        )

        # 按回车键也可以触发，并清空输入框
        msg.submit(
            fn=respond,
            inputs=[msg, chatbot],
            outputs=[chatbot, msg],  # 输出到 chatbot 和 msg，清空输入框
        )

    return demo

# 启动 Gradio 应用，指定地址和端口
if __name__ == "__main__":
    interface = create_chat_interface()
    interface.launch(
        server_name="0.0.0.0",  # 监听地址，改为本地监听
        server_port=7677       # 监听端口
    )