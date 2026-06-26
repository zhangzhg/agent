package com.agent.client;

import cn.hutool.http.HttpResponse;
import com.agent.config.TeleAiConfig;
import com.agent.dto.TeleAiRequest;
import com.agent.dto.TeleAiResponse;
import com.agent.dto.TeleAiStreamEvent;
import com.agent.util.HttpClientUtil;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.function.Consumer;

/**
 * 星辰智能体客户端
 * 用于调用星辰智能体发布平台的 API
 */
@Component
public class TeleAiClient {
    
    private static final Logger logger = LoggerFactory.getLogger(TeleAiClient.class);
    
    @Autowired
    private TeleAiConfig teleAiConfig;
    
    @Autowired
    private HttpClientUtil httpClientUtil;
    
    /**
     * API 端点：聊天消息
     */
    private static final String CHAT_MESSAGES_ENDPOINT = "/chat-messages";
    
    /**
     * 发送聊天消息（阻塞模式）
     *
     * @param request 请求对象
     * @return 响应对象
     */
    public TeleAiResponse chat(TeleAiRequest request) {
        if (!teleAiConfig.isValid()) {
            logger.warn("TeleAi is not configured properly");
            throw new RuntimeException("TeleAi configuration is invalid");
        }
        
        // 设置阻塞模式
        request.setMode("blocking");
        
        String url = teleAiConfig.getBaseUrl() + CHAT_MESSAGES_ENDPOINT;
        Map<String, String> headers = buildHeaders();
        
        try {
            String responseBody = httpClientUtil.post(url, headers, request, teleAiConfig.getTimeout());
            TeleAiResponse response = httpClientUtil.parseJson(responseBody, TeleAiResponse.class);
            
            logger.info("TeleAi chat success - MessageId: {}, ConversationId: {}", 
                response.getMessageId(), response.getConversationId());
            
            return response;
            
        } catch (Exception e) {
            logger.error("TeleAi chat failed: {}", e.getMessage());
            throw new RuntimeException("TeleAi chat request failed: " + e.getMessage(), e);
        }
    }
    
    /**
     * 发送聊天消息（流式模式，支持结束和错误回调）
     * 使用 SSE (Server-Sent Events) 接收流式响应
     *
     * @param request 请求对象
     * @param onMessage 消息处理回调函数
     * @param onEnd 结束回调函数
     * @param onError 错误回调函数
     */
    public void chatStream(TeleAiRequest request, Consumer<String> onMessage, Runnable onEnd, Consumer<String> onError) {
        if (!teleAiConfig.isValid()) {
            logger.warn("TeleAi is not configured properly");
            throw new RuntimeException("TeleAi configuration is invalid");
        }
        
        // 设置流式模式
        request.setMode("streaming");
        
        String url = teleAiConfig.getBaseUrl() + CHAT_MESSAGES_ENDPOINT;
        Map<String, String> headers = buildHeaders();
        
        try {
            HttpResponse response = httpClientUtil.postStream(url, headers, request, teleAiConfig.getStreamTimeout());
            
            // 处理 SSE 流式响应
            processSseStream(response, onMessage, onEnd, onError);
            
        } catch (Exception e) {
            logger.error("TeleAi chat stream failed: {}", e.getMessage());
            
            // 调用错误回调
            if (onError != null) {
                onError.accept(e.getMessage());
            }
            
            throw new RuntimeException("TeleAi chat stream request failed: " + e.getMessage(), e);
        }
    }
    
    /**
     * 发送简单聊天消息（阻塞模式）
     *
     * @param query 查询内容
     * @return 响应对象
     */
    public TeleAiResponse chatSimple(String query) {
        TeleAiRequest request = TeleAiRequest.createSimple(query, teleAiConfig.getDefaultUser());
        return chat(request);
    }
    
    /**
     * 发送简单聊天消息（流式模式，支持结束和错误回调）
     *
     * @param query 查询内容
     * @param onMessage 消息处理回调函数
     * @param onEnd 结束回调函数
     * @param onError 错误回调函数
     */
    public void chatSimpleStream(String query, Consumer<String> onMessage, Runnable onEnd, Consumer<String> onError) {
        TeleAiRequest request = TeleAiRequest.createSimple(query, teleAiConfig.getDefaultUser());
        chatStream(request, onMessage, onEnd, onError);
    }
    
    /**
     * 发送带对话上下文的聊天消息（阻塞模式）
     *
     * @param query 查询内容
     * @param conversationId 对话 ID
     * @return 响应对象
     */
    public TeleAiResponse chatWithConversation(String query, String conversationId) {
        TeleAiRequest request = TeleAiRequest.createWithConversation(query, conversationId, teleAiConfig.getDefaultUser());
        return chat(request);
    }
    
    /**
     * 发送带对话上下文的聊天消息（流式模式，支持结束和错误回调）
     *
     * @param query 查询内容
     * @param conversationId 对话 ID
     * @param onMessage 消息处理回调函数
     * @param onEnd 结束回调函数
     * @param onError 错误回调函数
     */
    public void chatWithConversationStream(String query, String conversationId, Consumer<String> onMessage, Runnable onEnd, Consumer<String> onError) {
        TeleAiRequest request = TeleAiRequest.createWithConversation(query, conversationId, teleAiConfig.getDefaultUser());
        chatStream(request, onMessage, onEnd, onError);
    }
    
    /**
     * 发送带图片的聊天消息（阻塞模式）
     *
     * @param query 查询内容
     * @param imageUrl 图片 URL
     * @return 响应对象
     */
    public TeleAiResponse chatWithImage(String query, String imageUrl) {
        TeleAiRequest request = TeleAiRequest.createWithImage(query, imageUrl, teleAiConfig.getDefaultUser());
        return chat(request);
    }
    
    /**
     * 发送带图片的聊天消息（流式模式，支持结束和错误回调）
     *
     * @param query 查询内容
     * @param imageUrl 图片 URL
     * @param onMessage 消息处理回调函数
     * @param onEnd 结束回调函数
     * @param onError 错误回调函数
     */
    public void chatWithImageStream(String query, String imageUrl, Consumer<String> onMessage, Runnable onEnd, Consumer<String> onError) {
        TeleAiRequest request = TeleAiRequest.createWithImage(query, imageUrl, teleAiConfig.getDefaultUser());
        chatStream(request, onMessage, onEnd, onError);
    }
    
    /**
     * 构建请求头
     *
     * @return 请求头 Map
     */
    private Map<String, String> buildHeaders() {
        Map<String, String> headers = new HashMap<>();
        headers.put("Authorization", teleAiConfig.getAuthorizationHeader());
        headers.put("Content-Type", "application/json");
        return headers;
    }
    
    /**
     * 处理 SSE 流式响应
     * TeleAi API 流式返回格式：
     * - 每个流式块格式：data: {"event": "message", ...}\n\n
     * - 块之间以 \n\n 分隔
     * - 事件类型：message（普通消息）、message_end（结束）、error（异常）
     *
     * @param response HTTP 响应对象
     * @param onMessage 消息处理回调函数
     * @param onEnd 结束回调函数
     * @param onError 错误回调函数
     */
    private void processSseStream(HttpResponse response, Consumer<String> onMessage, Runnable onEnd, Consumer<String> onError) {
        try (InputStream inputStream = response.bodyStream();
             BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
            
            String line;
            
            while ((line = reader.readLine()) != null) {
                // SSE 格式：data: {json}
                if (line.startsWith("data: ")) {
                    String data = line.substring(6).trim();
                    
                    if (!data.isEmpty()) {
                        // 解析 JSON 数据
                        try {
                            TeleAiStreamEvent event = httpClientUtil.parseJson(data, TeleAiStreamEvent.class);
                            
                            logger.debug("SSE event received: {} - {}", event.getEvent(), data);
                            
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
                                    
                                    // 调用结束回调
                                    onEnd.run();
                                    
                                    return; // 结束流处理
                                    
                                case "error":
                                    // 异常事件
                                    logger.error("SSE stream error - Code: {}, Message: {}", 
                                        event.getCode(), event.getMessage());
                                    
                                    // 调用错误回调
                                    onError.accept(event.getMessage());
                                    
                                    throw new RuntimeException("TeleAi stream error: " + event.getMessage());
                                    
                                default:
                                    logger.warn("Unknown SSE event type: {}", event.getEvent());
                            }
                            
                        } catch (RuntimeException e) {
                            // 如果是 TeleAi stream error，直接抛出（已经调用了错误回调）
                            if (e.getMessage().startsWith("TeleAi stream error")) {
                                throw e;
                            }
                            
                            logger.error("Failed to parse SSE event: {} - {}", data, e.getMessage());
                            // 继续处理下一个事件，不中断流
                        }
                    }
                }
                // 忽略空行（\n\n 分隔符）
            }
            
            logger.info("SSE stream ended normally");
            
            // 如果流正常结束（没有收到 message_end），也调用结束回调
            onEnd.run();
            
        } catch (Exception e) {
            logger.error("SSE stream processing error: {}", e.getMessage());
            
            // 调用错误回调（如果还没有调用）
            if (!e.getMessage().contains("TeleAi stream error")) {
                onError.accept(e.getMessage());
            }
            
            throw new RuntimeException("SSE stream processing failed: " + e.getMessage(), e);
        }
    }
}