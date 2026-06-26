package com.agent.service.impl;

import com.agent.config.SQLiteVecConfig;
import com.agent.dto.ConversationDTO;
import com.agent.dto.MessageDTO;
import com.agent.entity.Conversation;
import com.agent.entity.Message;
import com.agent.mapper.ConversationMapper;
import com.agent.mapper.MessageMapper;
import com.agent.service.ChatService;
import com.agent.service.EmbeddingService;
import com.agent.service.VectorService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
public class ChatServiceImpl implements ChatService {
    
    @Autowired
    private ConversationMapper conversationMapper;
    
    @Autowired
    private MessageMapper messageMapper;
    
    @Autowired
    private EmbeddingService embeddingService;
    
    @Autowired
    private VectorService vectorService;

    @Autowired
    private SQLiteVecConfig sqLiteVecConfig;
    
    @Override
    public List<ConversationDTO> getConversations(Long userId) {
        LambdaQueryWrapper<Conversation> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Conversation::getUserId, userId)
               .orderByDesc(Conversation::getUpdateTime);
        
        List<Conversation> conversations = conversationMapper.selectList(wrapper);
        
        return conversations.stream().map(conv -> {
            ConversationDTO dto = new ConversationDTO();
            BeanUtils.copyProperties(conv, dto);
            return dto;
        }).collect(Collectors.toList());
    }
    
    @Override
    public ConversationDTO getConversationWithMessages(Long conversationId, Long userId) {
        Conversation conversation = conversationMapper.selectById(conversationId);
        
        if (conversation == null || !conversation.getUserId().equals(userId)) {
            return null;
        }
        
        ConversationDTO dto = new ConversationDTO();
        BeanUtils.copyProperties(conversation, dto);
        
        LambdaQueryWrapper<Message> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Message::getConversationId, conversationId)
               .orderByAsc(Message::getCreateTime);
        
        List<Message> messages = messageMapper.selectList(wrapper);
        
        List<MessageDTO> messageDTOs = messages.stream().map(msg -> {
            MessageDTO msgDTO = new MessageDTO();
            BeanUtils.copyProperties(msg, msgDTO);
            return msgDTO;
        }).collect(Collectors.toList());
        
        dto.setMessages(messageDTOs);
        return dto;
    }
    
    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createConversation(Long userId, String title) {
        // 查找用户最新的会话
        LambdaQueryWrapper<Conversation> convWrapper = new LambdaQueryWrapper<>();
        convWrapper.eq(Conversation::getUserId, userId)
                   .orderByDesc(Conversation::getCreateTime)
                   .last("LIMIT 1");
        
        Conversation latestConversation = conversationMapper.selectOne(convWrapper);
        
        // 如果存在最新会话，检查是否有消息记录
        if (latestConversation != null) {
            LambdaQueryWrapper<Message> msgWrapper = new LambdaQueryWrapper<>();
            msgWrapper.eq(Message::getConversationId, latestConversation.getId());
            long messageCount = messageMapper.selectCount(msgWrapper);
            
            // 如果最新会话没有消息记录，返回现有会话ID（不创建新会话）
            if (messageCount == 0) {
                return latestConversation.getId();
            }
        }
        
        // 如果没有会话，或者最新会话有消息记录，创建新会话
        Conversation conversation = new Conversation();
        conversation.setUserId(userId);
        conversation.setTitle(title);
        conversationMapper.insert(conversation);
        return conversation.getId();
    }
    
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteConversation(Long conversationId, Long userId) {
        Conversation conversation = conversationMapper.selectById(conversationId);
        
        if (conversation != null && conversation.getUserId().equals(userId)) {
            conversationMapper.deleteById(conversationId);
            
            LambdaQueryWrapper<Message> wrapper = new LambdaQueryWrapper<>();
            wrapper.eq(Message::getConversationId, conversationId);
            messageMapper.delete(wrapper);
        }
    }
    
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void addMessage(Long conversationId, String role, String content) {
        Message message = new Message();
        message.setConversationId(conversationId);
        message.setRole(role);
        message.setContent(content);
        messageMapper.insert(message);
        
        // 如果是用户消息，生成并保存向量嵌入
        if ("user".equals(role) && sqLiteVecConfig.isVecEnabled()) {
            float[] embedding = embeddingService.embed(content);
            vectorService.saveEmbedding(message.getId(), embedding);
        }
    }
    
    /**
     * 获取相关历史对话，用于增强上下文
     * @param conversationId 对话ID
     * @param currentMessage 当前消息内容
     * @param threshold 相似度阈值
     * @param topK 返回的最大数量
     * @return 相关历史消息列表
     */
    @Override
    public List<Message> getRelevantHistory(Long conversationId, String currentMessage, float threshold, int topK) {
        // 生成当前消息的向量嵌入
        float[] queryEmbedding = embeddingService.embed(currentMessage);
        
        // 查找相似的历史消息
        return vectorService.findSimilarMessages(conversationId, queryEmbedding, threshold, topK);
    }
}