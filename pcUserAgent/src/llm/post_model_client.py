# -*- coding: utf-8 -*-
"""Model wrapper for post-based inference apis."""
import json
import time
from abc import ABC
from typing import Any, Callable, Dict, List, Optional, Generator, Tuple, Union,Sequence,Iterator,AsyncIterator
import requests
import aiohttp
import asyncio

from loguru import logger

from ..tools.base import NuwaBaseTool
from .core.base import BaseChatModelClient, register_llm
from ..msg.message import  Message,ASSISTANT,FUNCTION,TOOL

@register_llm('postapi')
class PostAPIChatModelClient(BaseChatModelClient):
    """The base model wrapper for the model deployed on the POST API."""

    # llm 客户端适配
    def __init__(self, 
                 config_list: Optional[Dict[str, Any]] = None, 
                 **kwargs: Any):
        logger.info("PostAPIChatModelClient-----------__init__")
        if config_list:
            # 如果有内容，直接展开作为参数传入 BaseChatModelClient 作为关键字保存
            super().__init__(config_list=config_list, **config_list, **kwargs)
        else:
            super().__init__(config_list=config_list, **kwargs)

        # 设置 max_tokens，默认值 4096
        self.max_tokens = kwargs.get('max_tokens', 4096)
        
    # 异步生成响应
    async def a_generate_rsp(
        self,
        messages: List[Union[Message, Dict]],
        tools: Optional[List[Dict]] = None,
        stream: bool = True,
        delta_stream: bool = False,
        **kwargs: Any,
    ) -> Union[List[Message], List[Dict], AsyncIterator[List[Message]], AsyncIterator[List[Dict]]]:
        """生成响应，支持流式和非流式输出（异步版本）"""
        logger.info("PostAPIChatModelClient::a_generate_rsp --- begin!")
        headers = {"Content-Type": "application/json"}

        # 检查是否有 dst_url参数，如果有则使用dst_url，否则使用base_url
        dst_url = kwargs.pop('dst_url')
        if dst_url:
             url = dst_url
        else:
            url = self.base_url
        logger.info(f"PostAPIChatModelClient::a_generate_rsp --- url:{url}!")
        #------------------------------------------------------
        # 直接将message给postapikwargs
        postapikwargs = messages[0]

        # nuawagent暂不支持tool处理
        if tools:
            postapikwargs["tools"] = tools
        postapikwargs.update(kwargs) # 将kwargs的键和值更新到 postapikwargs 中去，如果有相同的键直接kwargs 覆盖掉，没有的就添加

        logger.info(f"PostAPIChatModelClient::a_generate_rsp: postapikwargs:\n{postapikwargs}")
        # 记录调用开始时间
        start_time = time.perf_counter()
        response = requests.post(url, headers=headers, json=postapikwargs, stream=True)
        if stream:
            # 当 stream=True 时，返回异步生成器以支持流式处理
            return self.parse_stream_response_async(response, start_time=start_time)
            #logger.info(f"OpenAiChatModelClient::a_generate_rsp: parse_stream_response_async abc: {abc}")
            #return abc
        
        else:
            # 当 stream=False 时，返回完整的消息列表
            return self.parse_non_stream_response(response)

        #----------------------------------------------------------------------------------------------------------
        # 异步方式调用http请求并且获取响应,测试发现星云不支持
        if 0:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=None, data=json.dumps(postapikwargs)) as response:
                #response = requests.post(url, headers=headers, json=postapikwargs, stream=True)  # 请求星云模型
                    logger.info(f"PostAPIChatModelClient::a_generate_rsp: response: {response}")
                    if stream:
                        # 当 stream=True 时，返回异步生成器以支持流式处理
                        return self.parse_stream_response_async(response, start_time=start_time)
                        #logger.info(f"OpenAiChatModelClient::a_generate_rsp: parse_stream_response_async abc: {abc}")
                        #return abc
                    
                    else:
                        # 当 stream=False 时，返回完整的消息列表
                        return self.parse_non_stream_response(response)
        #----------------------------------------------------------------------------------------------------------

    # 异步解析流式响应
    async def parse_stream_response_async(self, response: Any, start_time: float) -> AsyncIterator[List[Message]]:
        logger.info("PostAPIChatModelClient::parse_stream_response_async --- begin!")
        """解析 postapi 流式响应的结果（异步版本）"""
        tool_calls = []  # 存储多个工具调用
        first_packet_logged = False  # 标记是否已记录第一个报文时间

        # 使用异步迭代器遍历流式响应
        for line in response.iter_lines():
            try:
                #----------------------------------------------------------
                # 大模型没响应的时候打开这个日志 (勿删)
                #logger.info(f"postapi rsp:==>{line}")
                #----------------------------------------------------------
                line = line.decode('utf-8').strip()  # 解码字节流并去掉首尾空格
                #if not line or not line.startswith("data: "):
                if not line:
                    continue  # 跳过空行和非数据行

                # 特殊处理最后的数据行 [DONE]
                if line[6:] == '[DONE]':
                    logger.info("Received [DONE] - Stream Ended")
                    break  # 数据流结束，跳出循环

                #chunk = json.loads(line[6:])  # 解析 JSON 数据（去掉 "data: " 前缀）
                chunk = json.loads(line)
                #logger.info(f"postapi json rsp:==>{chunk}")

                # 记录第一个有效报文的时间
                if not first_packet_logged:
                    end_time = time.perf_counter()
                    elapsed_time = end_time - start_time
                    logger.info(f"=========>Time to first packet: {elapsed_time:.3f} seconds")
                    first_packet_logged = True

                # 直接从 data 字段中提取 content
                rsp_data = chunk['data']
                if rsp_data.get('content') is not None:
                    content = rsp_data['content']
                    yield [Message(role=ASSISTANT, content=content)]  # 逐步返回生成内容

                elif rsp_data.get('tool_calls'):
                    tool_call_data = rsp_data['tool_calls'][0]
                    index = tool_call_data.get('index', 0)

                    while len(tool_calls) <= index:
                        tool_calls.append(tool_call_data)

                    if tool_call_data['function']['arguments'] in ["", None]:
                        continue
                    else:
                        if tool_calls[index]['function']['arguments'] is None:
                            # 第一个消息是空的，直接赋值覆盖
                            tool_calls[index]['function']['arguments'] = tool_call_data['function']['arguments']
                        else:
                            tool_calls[index]['function']['arguments'] += tool_call_data['function']['arguments']

            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.error(f"Error parsing stream response: {e}, rsp: {line}")
                continue

        if tool_calls:
            # 处理 tool call 调用的情况
            logger.info(f"PostAPIChatModelClient::parse_stream_response_async ---fff----tool_calls: {tool_calls}")
            yield [Message(role=FUNCTION, content='', tool_calls=tool_calls)]

        logger.info("PostAPIChatModelClient::parse_stream_response_async --- end!")

    # 根据用户输入的messages 和 Functions 进行处理了
    def generate_rsp(
            self,
            messages: List[Union[Message, Dict]],
            tools: Optional[List[Dict]] = None,
            stream: bool = True,
            delta_stream: bool = False,
            **kwargs: Any,
        ) -> Union[List[Message], List[Dict], Iterator[List[Message]], Iterator[List[Dict]]]:
        pass

    # 解析模型的响应，同步流模式，目前没用到
    def parse_stream_response(self, chunks: Any) -> Iterator[List[Message]]:
        logger.info("PostAPIChatModelClient::parse_stream_response --- begin!")
        pass
    
    # 解析模型的响应，同步非流模式，目前没用到
    def parse_non_stream_response(self, chunk: Any) -> List[Message]:
        pass

    # 将 NuwaBaseTool 转换为 OpenAI 支持的工具格式
    def convert_nuwa_tool_to_model_support(self, nuwa_tools: Union[Dict, List[NuwaBaseTool]]) -> List[Dict]:
        """将 NuwaBaseTool 格式转换为 OpenAI 支持的工具格式"""
        '''
            tools = [{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current temperature for a given location.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City and country e.g. Bogotá, Colombia"
                            }
                        },
                        "required": [
                            "location"
                        ],
                        "additionalProperties": False
                    },
                    "strict": True
                }
            },{.....}]
        '''
        openai_tools =[]
        # 没有tool 返回空
        if not nuwa_tools:
            return openai_tools
        
        # 如果dict说明是openAI格式，直接返回
        if isinstance(nuwa_tools, dict):
            nuwa_tools = [nuwa_tools]

        # 遍历传入的 nuwa_tools
        for tool in nuwa_tools:
            tool_json = tool.openAI_format()
            # 包装成 OpenAI 标准格式
            openai_tool = {
                "type": "function",
                "function": tool_json  # 直接使用 tool.openAI_format() 的返回值作为 function 内容
            }
            openai_tools.append(openai_tool)

        return openai_tools
