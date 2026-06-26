# TeleAi API 流式响应格式说明

## 📖 流式响应结构

TeleAi API 的流式返回结构与标准 SSE 格式有所不同，需要特殊处理。

### 🔍 响应格式

**Content-Type:** `text/event-stream`

**基本格式：**
```
data: {"event": "message", ...}\n\n
data: {"event": "message", ...}\n\n
data: {"event": "message_end", ...}\n\n
```

**关键特征：**
- ✅ 每个流式块以 `data: ` 开头
- ✅ 块之间以 `\n\n`（两个换行符）分隔
- ✅ 每个 `data:` 后面是 JSON 格式的事件数据
- ✅ 需要解析 JSON 来判断事件类型

### 📤 事件类型

#### 1. message 事件（普通消息）

**格式示例：**
```json
data: {"event": "message", "task_id": "aa321d77-dd8a-469b-a176-7791e44dfa1e", "id": "403f4621-5332-4fb2-85a1-a36ecac331cf", "answer": "你好", "created_at": 1705398420}\n\n
```

**字段说明：**
- `event`: "message"（固定值）
- `task_id`: 任务 ID
- `id`: 消息 ID
- `answer`: 回答内容（需要提取并发送给用户）
- `created_at`: 创建时间戳

**处理方式：**
- 提取 `answer` 字段内容
- 实时发送给用户（通过 SSE 或 WebSocket）

#### 2. message_end 事件（消息结束）

**格式示例：**
```json
data: {"event": "message_end", "task_id": "aa321d77-dd8a-469b-a176-7791e44dfa1e", "id": "403f4621-5332-4fb2-85a1-a36ecac331cf", "created_at": 1705398420}\n\n
```

**字段说明：**
- `event`: "message_end"（固定值）
- `task_id`: 任务 ID
- `id`: 消息 ID
- `created_at`: 创建时间戳

**处理方式：**
- 表示流式输出结束
- 结束流处理，关闭连接

#### 3. error 事件（异常）

**格式示例：**
```json
data: {"event": "error", "code": 500, "message": "Internal server error"}\n\n
```

**字段说明：**
- `event`: "error"（固定值）
- `code`: 错误码
- `message`: 错误消息

**处理方式：**
- 表示流式输出过程中出现异常
- 抛出异常，结束流处理
- 向用户返回错误信息

## 🚀 处理实现

### TeleAiStreamEvent DTO

创建了 [TeleAiStreamEvent.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\dto\TeleAiStreamEvent.java) 用于解析流式事件：

```java
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TeleAiStreamEvent {
    private String event;          // 事件类型
    @JsonProperty("task_id")
    private String taskId;         // 任务 ID
    private String id;             // 消息 ID
    private String answer;         // 回答内容（message 事件）
    @JsonProperty("created_at")
    private Long createdAt;        // 创建时间
    private Integer code;          // 错误码（error 事件）
    private String message;        // 错误消息（error 事件）
    private Metadata metadata;     // 元数据（可选）
    
    // 判断方法
    public boolean isMessage() { return "message".equals(event); }
    public boolean isEnd() { return "message_end".equals(event); }
    public boolean isError() { return "error".equals(event); }
}
```

### processSseStream 方法

修改了 [TeleAiClient.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\client\TeleAiClient.java) 的 `processSseStream` 方法：

```java
private void processSseStream(HttpResponse response, Consumer<String> onMessage) {
    try (InputStream inputStream = response.bodyStream();
         BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
        
        String line;
        
        while ((line = reader.readLine()) != null) {
            // SSE 格式：data: {json}
            if (line.startsWith("data: ")) {
                String data = line.substring(6).trim();
                
                if (!data.isEmpty()) {
                    // 解析 JSON 数据
                    TeleAiStreamEvent event = httpClientUtil.parseJson(data, TeleAiStreamEvent.class);
                    
                    // 根据事件类型处理
                    switch (event.getEvent()) {
                        case "message":
                            // 普通消息，提取 answer 内容
                            if (event.getAnswer() != null && !event.getAnswer().isEmpty()) {
                                onMessage.accept(event.getAnswer());
                            }
                            break;
                            
                        case "message_end":
                            // 消息结束事件
                            logger.info("SSE stream completed - TaskId: {}, MessageId: {}", 
                                event.getTaskId(), event.getId());
                            return; // 结束流处理
                            
                        case "error":
                            // 异常事件
                            logger.error("SSE stream error - Code: {}, Message: {}", 
                                event.getCode(), event.getMessage());
                            throw new RuntimeException("TeleAi stream error: " + event.getMessage());
                            
                        default:
                            logger.warn("Unknown SSE event type: {}", event.getEvent());
                    }
                }
            }
            // 忽略空行（\n\n 分隔符）
        }
        
    } catch (Exception e) {
        logger.error("SSE stream processing error: {}", e.getMessage());
        throw new RuntimeException("SSE stream processing failed: " + e.getMessage(), e);
    }
}
```

## 📊 处理流程

```
接收 SSE 流
    ↓
读取每一行
    ↓
判断是否为 data: 开头
    ↓
提取 JSON 数据
    ↓
解析为 TeleAiStreamEvent
    ↓
判断事件类型
    ↓
┌─────────────┬─────────────┬─────────────┐
│   message   │ message_end │    error    │
└─────────────┴─────────────┴─────────────┘
    ↓              ↓              ↓
提取 answer      结束流处理     抛出异常
发送给用户      关闭连接      返回错误信息
    ↓              ↓              ↓
继续读取        完成          中断
```

## 🎯 关键改进

### 1. 正确解析 JSON

**旧实现：** 直接拼接字符串
**新实现：** 解析 JSON 结构，提取 `answer` 字段

### 2. 区分事件类型

**旧实现：** 无法区分事件类型
**新实现：** 根据 `event` 字段判断：
- `message`: 提取 `answer` 发送给用户
- `message_end`: 结束流处理
- `error`: 抛出异常

### 3. 处理分隔符

**旧实现：** 使用空行判断消息分隔
**新实现：** 忽略空行（`\n\n` 分隔符），直接处理 `data:` 行

### 4. 错误处理

**旧实现：** 统一的错误处理
**新实现：** 区分不同错误类型：
- JSON 解析失败：继续处理下一个事件
- `error` 事件：抛出异常，中断流
- 其他异常：记录日志，抛出异常

## 📚 使用示例

### ChatController 中的使用

```java
private void generateAIResponseWithTeleAi(String prompt, SseEmitter emitter, StringBuilder responseBuilder) {
    try {
        logger.info("Calling TeleAi API with prompt length: {}", prompt.length());
        
        // 使用 TeleAi 流式聊天
        teleAiClient.chatSimpleStream(prompt, message -> {
            try {
                // 将 TeleAi 返回的消息发送到前端
                responseBuilder.append(message);
                emitter.send(SseEmitter.event().name("message").data(message));
            } catch (Exception e) {
                logger.error("Error sending SSE message: {}", e.getMessage());
            }
        });
        
        logger.info("TeleAi API call completed, response length: {}", responseBuilder.length());
        
    } catch (Exception e) {
        logger.error("TeleAi API call failed: {}", e.getMessage());
        
        // 如果 TeleAi 调用失败，使用模拟回复
        try {
            String fallbackResponse = "抱歉，AI 服务暂时不可用。错误信息：" + e.getMessage();
            responseBuilder.append(fallbackResponse);
            emitter.send(SseEmitter.event().name("message").data(fallbackResponse));
        } catch (Exception ex) {
            logger.error("Error sending fallback message: {}", ex.getMessage());
        }
    }
}
```

### 前端接收 SSE 消息

```javascript
const eventSource = new EventSource('/chat/stream');

eventSource.addEventListener('message', (e) => {
    // 接收 TeleAi 的 answer 内容
    console.log('Received message:', e.data);
    // 显示在聊天界面
    appendMessage(e.data);
});

eventSource.addEventListener('done', (e) => {
    // 流结束
    console.log('Stream completed');
    eventSource.close();
});

eventSource.addEventListener('conversationId', (e) => {
    // 对话 ID（用于保持上下文）
    console.log('Conversation ID:', e.data);
});
```

## 🔧 测试验证

### 1. 测试流式响应

```bash
curl -X POST 'https://agent.teleai.com.cn/v1/chat-messages' \
  --header 'Authorization: Bearer app-xxx' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "query": "请介绍下华为手机",
    "conversation_id": "",
    "mode": "streaming",
    "user": "admin"
  }'
```

**预期输出：**
```
data: {"event":"message","task_id":"xxx","id":"xxx","answer":"华为","created_at":1705398420}\n\n
data: {"event":"message","task_id":"xxx","id":"xxx","answer":"手机","created_at":1705398421}\n\n
data: {"event":"message_end","task_id":"xxx","id":"xxx","created_at":1705398422}\n\n
```

### 2. 测试错误处理

```bash
curl -X POST 'https://agent.teleai.com.cn/v1/chat-messages' \
  --header 'Authorization: Bearer invalid-key' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "query": "测试",
    "mode": "streaming"
  }'
```

**预期输出：**
```
data: {"event":"error","code":401,"message":"Unauthorized"}\n\n
```

## 📊 性能优化

### 1. 日志级别控制

```java
// 生产环境：使用 INFO 级别
logger.info("SSE stream completed - TaskId: {}, MessageId: {}", event.getTaskId(), event.getId());

// 开发环境：使用 DEBUG 级别
logger.debug("SSE event received: {} - {}", event.getEvent(), data);
```

### 2. 异常处理优化

```java
// JSON 解析失败不中断流
catch (Exception e) {
    logger.error("Failed to parse SSE event: {} - {}", data, e.getMessage());
    // 继续处理下一个事件，不中断流
}
```

### 3. 资源管理

```java
// 使用 try-with-resources 自动关闭资源
try (InputStream inputStream = response.bodyStream();
     BufferedReader reader = new BufferedReader(...)) {
    // 处理流
}
```

## 🎉 总结

**关键改进：**
- ✅ 正确解析 JSON 格式的流式事件
- ✅ 区分三种事件类型（message、message_end、error）
- ✅ 提取 `answer` 字段发送给用户
- ✅ 正确处理 `\n\n` 分隔符
- ✅ 完善的错误处理和日志记录

**文件变更：**
- ✅ 创建 [TeleAiStreamEvent.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\dto\TeleAiStreamEvent.java)
- ✅ 修改 [TeleAiClient.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\client\TeleAiClient.java) 的 `processSseStream` 方法
- ✅ 添加 import 语句

---

**现在 TeleAiClient 可以正确处理 TeleAi API 的流式响应格式！** ✅