# 星辰智能体客户端使用指南

## 📖 简介

星辰智能体客户端（TeleAiClient）用于调用星辰智能体发布平台的 API，支持阻塞模式和流式模式的聊天对话。

## 🔧 配置说明

### 1. application.yml 配置

```yaml
# 星辰智能体配置
teleai:
  enabled: true  # 启用星辰智能体
  base-url: https://agent.teleai.com.cn/v1  # API 基础地址
  api-key: app-xxx  # API Key（请替换为实际的 API Key）
  timeout: 30000  # HTTP 请求超时时间（毫秒）
  stream-timeout: 60000  # 流式响应超时时间（毫秒）
  default-user: admin  # 默认用户标识
  default-mode: streaming  # 默认模式
```

### 2. 获取 API Key

1. 登录星辰智能体发布平台：https://agent.teleai.com.cn
2. 创建或选择已发布的智能体
3. 在智能体详情页面获取 API Key（格式：app-xxx）
4. 将 API Key 配置到 `application.yml` 中

## 🚀 使用方式

### 1. 注入客户端

```java
@Autowired
private TeleAiClient teleAiClient;
```

### 2. 阻塞模式（同步调用）

#### 简单聊天

```java
// 发送简单聊天消息
TeleAiResponse response = teleAiClient.chatSimple("请介绍下华为手机");

System.out.println("Answer: " + response.getAnswer());
System.out.println("ConversationId: " + response.getConversationId());
```

#### 带对话上下文

```java
// 第一次对话
TeleAiResponse response1 = teleAiClient.chatSimple("你好，我是小明");
String conversationId = response1.getConversationId();

// 继续对话（保持上下文）
TeleAiResponse response2 = teleAiClient.chatWithConversation(
    "我刚才说我叫什么名字？", 
    conversationId
);

System.out.println("Answer: " + response2.getAnswer());
```

#### 带图片

```java
// 发送带图片的聊天消息
TeleAiResponse response = teleAiClient.chatWithImage(
    "这张图片里有什么？", 
    "http://cloud.itbg2.ffcs.cn:20361/logo/logo-site.png"
);

System.out.println("Answer: " + response.getAnswer());
```

### 3. 流式模式（异步调用）

#### 简单流式聊天

```java
// 发送流式聊天消息
teleAiClient.chatSimpleStream("请介绍下华为手机", message -> {
    System.out.println("Received: " + message);
    // 可以将消息发送到前端（通过 SSE 或 WebSocket）
});
```

#### 带对话上下文的流式聊天

```java
// 第一次对话（阻塞模式获取 conversationId）
TeleAiResponse response1 = teleAiClient.chatSimple("你好，我是小明");
String conversationId = response1.getConversationId();

// 继续对话（流式模式）
teleAiClient.chatWithConversationStream(
    "我刚才说我叫什么名字？", 
    conversationId, 
    message -> {
        System.out.println("Received: " + message);
    }
);
```

#### 带图片的流式聊天

```java
// 发送带图片的流式聊天消息
teleAiClient.chatWithImageStream(
    "这张图片里有什么？", 
    "http://cloud.itbg2.ffcs.cn:20361/logo/logo-site.png",
    message -> {
        System.out.println("Received: " + message);
    }
);
```

### 4. 自定义请求

#### 构建自定义请求

```java
// 创建自定义请求
TeleAiRequest request = TeleAiRequest.builder()
    .query("请帮我分析这个文档")
    .conversationId("")  // 新对话
    .mode("streaming")  // 流式模式
    .user("user123")  // 自定义用户标识
    .files(List.of(
        TeleAiFile.createDocument("http://example.com/document.pdf")
    ))
    .build();

// 发送请求（阻塞模式）
TeleAiResponse response = teleAiClient.chat(request);

// 或发送请求（流式模式）
teleAiClient.chatStream(request, message -> {
    System.out.println("Received: " + message);
});
```

## 📊 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat-messages` | POST | 发送聊天消息 |

## 🔍 请求参数说明

### TeleAiRequest

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | String | ✅ | 用户查询内容 |
| `conversation_id` | String | ❌ | 对话 ID（空字符串表示新对话） |
| `mode` | String | ❌ | 响应模式（streaming 或 blocking） |
| `user` | String | ❌ | 用户标识 |
| `input_data` | Map | ❌ | 输入数据（可选） |
| `files` | List | ❌ | 文件列表（可选） |

### TeleAiFile

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | String | ✅ | 文件类型（image, document） |
| `transfer_method` | String | ✅ | 传输方式（remote_url） |
| `url` | String | ✅ | 文件 URL |

## 📤 响应参数说明

### TeleAiResponse

| 参数 | 类型 | 说明 |
|------|------|------|
| `message_id` | String | 消息 ID |
| `conversation_id` | String | 对话 ID |
| `mode` | String | 响应模式 |
| `answer` | String | 响应内容 |
| `created_at` | Long | 创建时间 |
| `user` | String | 用户标识 |
| `metadata` | Metadata | 元数据 |

### Metadata

| 参数 | 类型 | 说明 |
|------|------|------|
| `usage` | Usage | Token 使用情况 |

### Usage

| 参数 | 类型 | 说明 |
|------|------|------|
| `prompt_tokens` | Integer | 提示词 token 数 |
| `completion_tokens` | Integer | 完成 token 数 |
| `total_tokens` | Integer | 总 token 数 |

## 🛠️ HttpClientUtil 工具类

HttpClientUtil 提供了统一的 HTTP 请求处理功能：

### 主要方法

```java
// GET 请求
String response = httpClientUtil.get(url);
String response = httpClientUtil.get(url, headers);

// POST 请求（JSON 格式）
String response = httpClientUtil.post(url, body);
String response = httpClientUtil.post(url, headers, body);

// 流式 POST 请求（用于 SSE）
HttpResponse response = httpClientUtil.postStream(url, headers, body, timeout);

// JSON 解析
TeleAiResponse response = httpClientUtil.parseJson(json, TeleAiResponse.class);

// JSON 序列化
String json = httpClientUtil.toJson(request);
```

### 自定义超时时间

```java
// 设置超时时间（毫秒）
String response = httpClientUtil.get(url, headers, 60000);
String response = httpClientUtil.post(url, headers, body, 60000);
```

## 🎯 最佳实践

### 1. 对话上下文管理

```java
// 保存 conversationId 到数据库
String conversationId = response.getConversationId();

// 后续对话使用相同的 conversationId
TeleAiResponse nextResponse = teleAiClient.chatWithConversation(
    "继续刚才的话题", 
    conversationId
);
```

### 2. 流式响应处理

```java
// 使用 StringBuilder 收集完整响应
StringBuilder fullAnswer = new StringBuilder();

teleAiClient.chatSimpleStream("请介绍下华为手机", message -> {
    fullAnswer.append(message);
    
    // 实时发送到前端（通过 SSE）
    // sseEmitter.send(message);
});

// 完整响应
String completeAnswer = fullAnswer.toString();
```

### 3. 错误处理

```java
try {
    TeleAiResponse response = teleAiClient.chatSimple(query);
    
    if (response.isSuccess()) {
        System.out.println("Success: " + response.getAnswer());
    } else {
        System.out.println("Failed: " + response.getMessageId());
    }
    
} catch (Exception e) {
    System.err.println("Error: " + e.getMessage());
}
```

### 4. 配置验证

```java
// 检查配置是否有效
if (!teleAiConfig.isValid()) {
    logger.warn("TeleAi configuration is invalid");
    return;
}

// 检查是否启用
if (!teleAiConfig.isEnabled()) {
    logger.warn("TeleAi is disabled");
    return;
}
```

## 📚 目录结构

```
src/main/java/com/agent/
├── config/
│   ├── TeleAiConfig.java          # 星辰智能体配置类
│   └── HttpClientConfig.java      # HTTP 客户端配置（可选）
├── client/
│   └── TeleAiClient.java          # 星辰智能体客户端
├── dto/
│   ├── TeleAiRequest.java         # 请求 DTO
│   ├── TeleAiResponse.java        # 响应 DTO
│   └── TeleAiFile.java            # 文件 DTO
└── util/
    └── HttpClientUtil.java        # HTTP 客户端工具类
```

## 🔗 相关文档

- [星辰智能体平台](https://agent.teleai.com.cn)
- [API 文档](https://agent.teleai.com.cn/docs)
- [HttpClientUtil 使用说明](./HttpClientUtil.md)

## 🎉 快速开始

### 1. 配置 API Key

```yaml
teleai:
  enabled: true
  api-key: app-your-actual-api-key
```

### 2. 创建测试接口

```java
@RestController
@RequestMapping("/test")
public class TestController {
    
    @Autowired
    private TeleAiClient teleAiClient;
    
    @GetMapping("/chat")
    public String chat(@RequestParam String query) {
        TeleAiResponse response = teleAiClient.chatSimple(query);
        return response.getAnswer();
    }
    
    @GetMapping("/chat-stream")
    public SseEmitter chatStream(@RequestParam String query) {
        SseEmitter emitter = new SseEmitter();
        
        teleAiClient.chatSimpleStream(query, message -> {
            try {
                emitter.send(message);
            } catch (IOException e) {
                emitter.completeWithError(e);
            }
        });
        
        emitter.complete();
        return emitter;
    }
}
```

### 3. 测试接口

```bash
# 阻塞模式
curl http://localhost:8080/api/test/chat?query=你好

# 流式模式
curl http://localhost:8080/api/test/chat-stream?query=你好
```

---

**总结**: 星辰智能体客户端提供了简单易用的 API 调用方式，支持阻塞模式和流式模式，可以轻松集成到现有的聊天系统中。✅