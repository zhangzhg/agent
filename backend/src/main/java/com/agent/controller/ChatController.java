package com.agent.controller;

import cn.hutool.core.thread.ThreadFactoryBuilder;
import com.agent.client.TeleAiClient;
import com.agent.common.Result;
import com.agent.config.TeleAiConfig;
import com.agent.dto.ChatRequest;
import com.agent.dto.ConversationDTO;
import com.agent.entity.Message;
import com.agent.service.ChatService;
import com.agent.util.SessionUtil;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.concurrent.*;

@RestController
@RequestMapping("/chat")
public class ChatController {
    
    private static final Logger logger = LoggerFactory.getLogger(ChatController.class);
    
    @Autowired
    private ChatService chatService;
    
    @Autowired
    private TeleAiClient teleAiClient;
    
    private final ExecutorService executorService = new ThreadPoolExecutor(
        10,
        50,
        60L, TimeUnit.SECONDS,
        new LinkedBlockingQueue<>(100),
        new ThreadFactoryBuilder()
            .setNamePrefix("chat-stream-pool-")
            .build(),
        new ThreadPoolExecutor.CallerRunsPolicy()
    );
    
    @GetMapping("/conversations")
    public Result<List<ConversationDTO>> getConversations() {
        Long userId = SessionUtil.getUserId();
        List<ConversationDTO> conversations = chatService.getConversations(userId);
        return Result.success(conversations);
    }
    
    @GetMapping("/conversations/{id}")
    public Result<ConversationDTO> getConversation(@PathVariable Long id) {
        Long userId = SessionUtil.getUserId();
        ConversationDTO conversation = chatService.getConversationWithMessages(id, userId);
        return Result.success(conversation);
    }
    
    @PostMapping("/conversations")
    public Result<Long> createConversation(@RequestParam String title) {
        Long userId = SessionUtil.getUserId();
        Long conversationId = chatService.createConversation(userId, title);
        return Result.success(conversationId);
    }
    
    @DeleteMapping("/conversations/{id}")
    public Result<Void> deleteConversation(@PathVariable Long id) {
        Long userId = SessionUtil.getUserId();
        chatService.deleteConversation(id, userId);
        return Result.success();
    }
    
    @PostMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamChat(@RequestBody ChatRequest request) {
        
        SseEmitter emitter = new SseEmitter(60000L);
        
        executorService.execute(() -> {
            try {
                Long conversationId = request.getConversationId();
                String userMessage = request.getMessage();
                
                if (conversationId == null) {
                    conversationId = chatService.createConversation(
                        SessionUtil.getUserId(), 
                        userMessage.substring(0, Math.min(userMessage.length(), 20))
                    );
                    emitter.send(SseEmitter.event().name("conversationId").data(conversationId));
                }
                
                // 检索相关历史对话（相似度 > 0.7，最多2条）
                List<Message> relevantHistory = chatService.getRelevantHistory(conversationId, userMessage, 0.7f, 2);
                
                // 构建增强的提示词
                StringBuilder enhancedPrompt = new StringBuilder();
                if (!relevantHistory.isEmpty()) {
                    enhancedPrompt.append("以下是相关的历史对话：\n");
                    for (Message msg : relevantHistory) {
                        enhancedPrompt.append(msg.getRole()).append(": ").append(msg.getContent()).append("\n");
                    }
                    enhancedPrompt.append("\n");
                }
                enhancedPrompt.append("当前用户提示词：").append(userMessage);
                
                chatService.addMessage(conversationId, "user", userMessage);
                
                // 使用 TeleAi 生成 AI 回复（流式模式）
                StringBuilder responseBuilder = new StringBuilder();
                
                // 使用真实的 TeleAi API
                generateAIResponseWithTeleAi(enhancedPrompt.toString(), emitter, responseBuilder);

                chatService.addMessage(conversationId, "assistant", responseBuilder.toString());
        
                emitter.send(SseEmitter.event().name("done").data("完成"));
                emitter.complete();
                
            } catch (Exception e) {
                emitter.completeWithError(e);
            }
        });
        
        return emitter;
    }
    
    /**
     * 使用 TeleAi 生成 AI 回复（流式模式）
     * @param prompt 提示词
     * @param emitter SSE emitter
     * @param responseBuilder 响应构建器
     */
    private void generateAIResponseWithTeleAi(String prompt, SseEmitter emitter, StringBuilder responseBuilder) {
        try {
            logger.info("Calling TeleAi API with prompt length: {}", prompt.length());
            
            // 使用 TeleAi 流式聊天（支持结束和错误回调）
            teleAiClient.chatSimpleStream(prompt, 
                // 消息回调
                message -> {
                    try {
                        // 将 TeleAi 返回的消息发送到前端
                        responseBuilder.append(message);
                        emitter.send(SseEmitter.event().name("message").data(message));
                    } catch (Exception e) {
                        logger.error("Error sending SSE message: {}", e.getMessage());
                    }
                },
                // 思考过程回调
                thoughtEvent -> {
                    try {
                        // 将思考过程发送到前端（使用不同的事件类型）
                        logger.debug("Sending thought event: position={}, thought={}", 
                            thoughtEvent.getPosition(), thoughtEvent.getThought());
                        
                        // 构建思考内容 JSON
                        String thoughtJson = String.format(
                            "{\"position\":%d,\"thought\":\"%s\",\"observation\":\"%s\",\"tool\":\"%s\",\"toolInput\":\"%s\"}",
                            thoughtEvent.getPosition(),
                            thoughtEvent.getThought() != null ? thoughtEvent.getThought() : "",
                            thoughtEvent.getObservation() != null ? thoughtEvent.getObservation() : "",
                            thoughtEvent.getTool() != null ? thoughtEvent.getTool() : "",
                            thoughtEvent.getToolInput() != null ? thoughtEvent.getToolInput() : ""
                        );
                        
                        emitter.send(SseEmitter.event().name("thought").data(thoughtJson));
                    } catch (Exception e) {
                        logger.error("Error sending SSE thought: {}", e.getMessage());
                    }
                },
                // 结束回调
                () -> {
                    try {
                        logger.info("TeleAi stream ended, completing SSE emitter");
                        // 发送完成事件
                        emitter.send(SseEmitter.event().name("done").data("完成"));
                        // 完成 SSE 连接
                        emitter.complete();
                    } catch (Exception e) {
                        logger.error("Error completing SSE emitter: {}", e.getMessage());
                        emitter.completeWithError(e);
                    }
                },
                // 错误回调
                errorMessage -> {
                    try {
                        logger.error("TeleAi stream error: {}", errorMessage);
                        // 发送错误消息
                        String errorResponse = "抱歉，AI 服务出现错误：" + errorMessage;
                        responseBuilder.append(errorResponse);
                        emitter.send(SseEmitter.event().name("message").data(errorResponse));
                        // 发送完成事件
                        emitter.send(SseEmitter.event().name("done").data("完成"));
                        // 完成 SSE 连接
                        emitter.complete();
                    } catch (Exception e) {
                        logger.error("Error sending error message: {}", e.getMessage());
                        emitter.completeWithError(e);
                    }
                }
            );
            
            logger.info("TeleAi API call completed, response length: {}", responseBuilder.length());
            
        } catch (Exception e) {
            logger.error("TeleAi API call failed: {}", e.getMessage());
            
            // 如果 TeleAi 调用失败，使用模拟回复
            try {
                String fallbackResponse = "抱歉，AI 服务暂时不可用。错误信息：" + e.getMessage();
                responseBuilder.append(fallbackResponse);
                emitter.send(SseEmitter.event().name("message").data(fallbackResponse));
                emitter.send(SseEmitter.event().name("done").data("完成"));
                emitter.complete();
            } catch (Exception ex) {
                logger.error("Error sending fallback message: {}", ex.getMessage());
                emitter.completeWithError(ex);
            }
        }
    }
}