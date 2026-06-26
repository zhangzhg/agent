package com.agent.service;

import com.agent.dto.ConversationDTO;
import com.agent.entity.Message;
import java.util.List;

public interface ChatService {
    List<ConversationDTO> getConversations(Long userId);
    
    ConversationDTO getConversationWithMessages(Long conversationId, Long userId);
    
    Long createConversation(Long userId, String title);
    
    void deleteConversation(Long conversationId, Long userId);
    
    void addMessage(Long conversationId, String role, String content);
    
    /**
     * 获取相关历史对话，用于增强上下文
     * @param conversationId 对话ID
     * @param currentMessage 当前消息内容
     * @param threshold 相似度阈值
     * @param topK 返回的最大数量
     * @return 相关历史消息列表
     */
    List<Message> getRelevantHistory(Long conversationId, String currentMessage, float threshold, int topK);
}