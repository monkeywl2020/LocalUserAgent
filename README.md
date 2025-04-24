# LocalUserAgent

部署在本地的可以与服务端agent交互的。
localUserAgent 代码，这个是与 pcuse 工具交互的模块，含有 fastapi 接口，RabbitMQ 客户端接口， apscheduler 接口，后台 nuwa-agent 接口，与pcuse的 接口
这里面包含2个模块， pcuserAgent 模块和 apscheduler 服务模块。 接口类型：<br>
-- 1） pcuserAgent 和 apscheduler 直接是通过http接口对接，主动和被动接口，创建调度，获取调度的通知<br>
-- 2） pcuserAgent 和 RabbitMQ 是使用的RabbitMQ客户端连接的。被动接口，接收消息。<br>
-- 3） pcuserAgent 和 pcuse 是使用的http连接。有消息规范，主动和被动即可，发送创建添加微信好友信息。接收pcuse的添加成功信息和聊天信息。<br>
-- 4） pcuserAgent 和 nuaw-agent 是使用的http连接。有消息规范，主动接口，调用与大模型通讯接口，流式输出。<br>
-- 5） 接口比较多。被动接口：有http的fastapi接口（接收pcuse过来的消息，接收apscheduler的调度通知消息）。 有RabbitMQ接收消息通知的接口。<br>
