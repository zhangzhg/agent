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
     * 发送聊天消息（流式模式，支持思考过程、结束和错误回调）
     * 使用 SSE (Server-Sent Events) 接收流式响应
     *
     * @param request 请求对象
     * @param onMessage 消息处理回调函数
     * @param onThought 思考过程处理回调函数（agent_thought 事件）
     * @param onEnd 结束回调函数
     * @param onError 错误回调函数
     */
    public void chatStream(TeleAiRequest request, Consumer<String> onMessage, Consumer<TeleAiStreamEvent> onThought, Runnable onEnd, Consumer<String> onError) {
        // 设置流式模式
        request.setMode("streaming");
        
        String url = teleAiConfig.getBaseUrl() + CHAT_MESSAGES_ENDPOINT;
        Map<String, String> headers = buildHeaders();
        
        try {
            HttpResponse response = httpClientUtil.postStream(url, headers, request, teleAiConfig.getStreamTimeout());
            
            // 处理 SSE 流式响应
            processSseStream(response, onMessage, onThought, onEnd, onError);
            
        } catch (Exception e) {
            logger.error("TeleAi chat stream failed: {}", e.getMessage());

            // 调用错误回调
            if (onError != null) {
                onError.accept(e.getMessage());
            }
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
     * 发送简单聊天消息（流式模式，支持思考过程、结束和错误回调）
     *
     * @param query 查询内容
     * @param onMessage 消息处理回调函数
     * @param onThought 思考过程处理回调函数（agent_thought 事件）
     * @param onEnd 结束回调函数
     * @param onError 错误回调函数
     */
    public void chatSimpleStream(String query, Consumer<String> onMessage, Consumer<TeleAiStreamEvent> onThought, Runnable onEnd, Consumer<String> onError) {
        TeleAiRequest request = TeleAiRequest.createSimple(query, teleAiConfig.getDefaultUser());
        chatStream(request, onMessage, onThought, onEnd, onError);
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
     * 发送带对话上下文的聊天消息（流式模式，支持思考过程、结束和错误回调）
     *
     * @param query 查询内容
     * @param conversationId 对话 ID
     * @param onMessage 消息处理回调函数
     * @param onThought 思考过程处理回调函数（agent_thought 事件）
     * @param onEnd 结束回调函数
     * @param onError 错误回调函数
     */
    public void chatWithConversationStream(String query, String conversationId, Consumer<String> onMessage, Consumer<TeleAiStreamEvent> onThought, Runnable onEnd, Consumer<String> onError) {
        TeleAiRequest request = TeleAiRequest.createWithConversation(query, conversationId, teleAiConfig.getDefaultUser());
        chatStream(request, onMessage, onThought, onEnd, onError);
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
     * 发送带图片的聊天消息（流式模式，支持思考过程、结束和错误回调）
     *
     * @param query 查询内容
     * @param imageUrl 图片 URL
     * @param onMessage 消息处理回调函数
     * @param onThought 思考过程处理回调函数（agent_thought 事件）
     * @param onEnd 结束回调函数
     * @param onError 错误回调函数
     */
    public void chatWithImageStream(String query, String imageUrl, Consumer<String> onMessage, Consumer<TeleAiStreamEvent> onThought, Runnable onEnd, Consumer<String> onError) {
        TeleAiRequest request = TeleAiRequest.createWithImage(query, imageUrl, teleAiConfig.getDefaultUser());
        chatStream(request, onMessage, onThought, onEnd, onError);
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
     * - 事件类型：message（普通消息）、message_end（结束）、error（异常）、agent_thought（思考过程）
     *
     * @param response HTTP 响应对象
     * @param onMessage 消息处理回调函数
     * @param onThought 思考过程处理回调函数（agent_thought 事件）
     * @param onEnd 结束回调函数
     * @param onError 错误回调函数
     */
    private void processSseStream(HttpResponse response, Consumer<String> onMessage, Consumer<TeleAiStreamEvent> onThought, Runnable onEnd, Consumer<String> onError) {
        try (InputStream inputStream = response.bodyStream();
             BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
            
            String line;
            StringBuilder dataBuilder = new StringBuilder();
            String sseEventName = null;
            
            while ((line = reader.readLine()) != null) {
                if (line.startsWith("event:")) {
                    sseEventName = line.substring(6).trim();
                    continue;
                }
                
                if (line.startsWith("data:")) {
                    String dataLine = line.substring(5);
                    if (dataLine.startsWith(" ")) {
                        dataLine = dataLine.substring(1);
                    }
                    dataBuilder.append(dataLine).append('\n');
                    continue;
                }
                
                if (line.isEmpty()) {
                    boolean stop = flushSseEvent(sseEventName, dataBuilder.toString().trim(), onMessage, onThought, onEnd, onError);
                    dataBuilder.setLength(0);
                    sseEventName = null;
                    if (stop) {
                        return;
                    }
                }
            }
            
            if (dataBuilder.length() > 0) {
                boolean stop = flushSseEvent(sseEventName, dataBuilder.toString().trim(), onMessage, onThought, onEnd, onError);
                if (stop) {
                    return;
                }
            }
            
            logger.info("SSE stream ended normally");
            
            // 如果流正常结束（没有收到 message_end），也调用结束回调
            onEnd.run();
            
        } catch (Exception e) {
            logger.error("SSE stream processing error: {}", e.getMessage());
            
            if (!e.getMessage().contains("TeleAi stream error") && onError != null) {
                onError.accept(e.getMessage());
            }
            
            throw new RuntimeException("SSE stream processing failed: " + e.getMessage(), e);
        }
    }
    
    private boolean flushSseEvent(String sseEventName, String rawData, Consumer<String> onMessage, Consumer<TeleAiStreamEvent> onThought, Runnable onEnd, Consumer<String> onError) {
        if (rawData == null || rawData.isEmpty()) {
            return false;
        }
        
        try {
            TeleAiStreamEvent event = httpClientUtil.parseJson(rawData, TeleAiStreamEvent.class);
            if ((event.getEvent() == null || event.getEvent().isEmpty()) && sseEventName != null) {
                event.setEvent(sseEventName);
            }
            
            logger.debug("SSE event received: {} - {}", event.getEvent(), rawData);
            
            switch (event.getEvent()) {
                case "message":
                case "message_replace":
                    String answerText = event.getAnswerText();
                    if (answerText != null && !answerText.isEmpty()) {
                        onMessage.accept(answerText);
                    }
                    return false;
                case "message_file":
                    logger.debug("SSE message_file event received: {}", rawData);
                    return false;
                case "agent_thought":
                    logger.debug("Agent thought - Position: {}, Thought: {}, Tool: {}", 
                        event.getPosition(), event.getThought(), event.getTool());
                    if (onThought != null) {
                        onThought.accept(event);
                    }
                    return false;
                case "message_end":
                    logger.info("SSE stream completed - TaskId: {}, MessageId: {}", 
                        event.getTaskId(), event.getId());
                    onEnd.run();
                    return true;
                case "workflow_started":
                case "node_started":
                case "node_finished":
                case "workflow_finished":
                    logger.debug("Workflow event received: {} - {}", event.getEvent(), rawData);
                    return false;
                case "check_failed":
                    String failedMsg = event.getCheckFailedMsg() != null ? event.getCheckFailedMsg() : event.getMessage();
                    logger.error("SSE check failed event: {}", failedMsg);
                    if (onError != null) {
                        onError.accept(failedMsg);
                    }
                    return true;
                case "error":
                    logger.error("SSE stream error - Code: {}, Message: {}", event.getCode(), event.getMessage());
                    if (onError != null) {
                        onError.accept(event.getMessage());
                    }
                    throw new RuntimeException("TeleAi stream error: " + event.getMessage());
                case "ping":
                    logger.debug("SSE ping received");
                    return false;
                default:
                    logger.debug("Other SSE event type: {} - {}", event.getEvent(), rawData);
                    return false;
            }
        } catch (RuntimeException e) {
            if (e.getMessage().startsWith("TeleAi stream error")) {
                throw e;
            }
            logger.error("Failed to parse SSE event: {} - {}", rawData, e.getMessage());
            return false;
        }
    }
}