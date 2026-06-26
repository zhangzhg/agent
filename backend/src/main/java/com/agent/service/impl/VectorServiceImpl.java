package com.agent.service.impl;

import com.agent.entity.Message;
import com.agent.mapper.MessageMapper;
import com.agent.service.VectorService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * 向量服务实现，使用简单的余弦相似度计算
 */
@Service
public class VectorServiceImpl implements VectorService {
    
    @Autowired
    private MessageMapper messageMapper;
    
    @Override
    public void saveEmbedding(Long messageId, float[] embedding) {
        Message message = messageMapper.selectById(messageId);
        if (message != null) {
            message.setEmbedding(floatArrayToBytes(embedding));
            messageMapper.updateById(message);
        }
    }
    
    @Override
    public float[] getEmbedding(Long messageId) {
        Message message = messageMapper.selectById(messageId);
        if (message != null && message.getEmbedding() != null) {
            return bytesToFloatArray(message.getEmbedding());
        }
        return null;
    }
    
    @Override
    public List<Message> findSimilarMessages(Long conversationId, float[] queryEmbedding, float threshold, int topK) {
        // 查询同一对话中的所有用户消息
        LambdaQueryWrapper<Message> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Message::getConversationId, conversationId)
               .eq(Message::getRole, "user") // 只检索用户消息
               .isNotNull(Message::getEmbedding) // 只检索有嵌入的消息
               .orderByDesc(Message::getCreateTime);
        
        List<Message> messages = messageMapper.selectList(wrapper);
        
        // 计算相似度并排序
        List<MessageSimilarity> similarities = new ArrayList<>();
        for (Message message : messages) {
            float[] messageEmbedding = bytesToFloatArray(message.getEmbedding());
            float similarity = cosineSimilarity(queryEmbedding, messageEmbedding);
            
            if (similarity >= threshold) {
                similarities.add(new MessageSimilarity(message, similarity));
            }
        }
        
        // 按相似度降序排序，取前topK个
        similarities.sort(Comparator.comparingDouble(MessageSimilarity::getSimilarity).reversed());
        
        List<Message> result = new ArrayList<>();
        for (int i = 0; i < Math.min(topK, similarities.size()); i++) {
            result.add(similarities.get(i).getMessage());
        }
        
        return result;
    }
    
    @Override
    public float cosineSimilarity(float[] vec1, float[] vec2) {
        if (vec1 == null || vec2 == null || vec1.length != vec2.length) {
            return 0;
        }
        
        float dotProduct = 0;
        float norm1 = 0;
        float norm2 = 0;
        
        for (int i = 0; i < vec1.length; i++) {
            dotProduct += vec1[i] * vec2[i];
            norm1 += vec1[i] * vec1[i];
            norm2 += vec2[i] * vec2[i];
        }
        
        if (norm1 == 0 || norm2 == 0) {
            return 0;
        }
        
        return dotProduct / (float) (Math.sqrt(norm1) * Math.sqrt(norm2));
    }
    
    /**
     * 将float数组转换为byte数组
     */
    private byte[] floatArrayToBytes(float[] floats) {
        ByteBuffer buffer = ByteBuffer.allocate(floats.length * 4);
        for (float f : floats) {
            buffer.putFloat(f);
        }
        return buffer.array();
    }
    
    /**
     * 将byte数组转换为float数组
     */
    private float[] bytesToFloatArray(byte[] bytes) {
        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        float[] floats = new float[bytes.length / 4];
        for (int i = 0; i < floats.length; i++) {
            floats[i] = buffer.getFloat();
        }
        return floats;
    }
    
    /**
     * 内部类，用于存储消息和相似度
     */
    private static class MessageSimilarity {
        private final Message message;
        private final float similarity;
        
        public MessageSimilarity(Message message, float similarity) {
            this.message = message;
            this.similarity = similarity;
        }
        
        public Message getMessage() {
            return message;
        }
        
        public float getSimilarity() {
            return similarity;
        }
    }
}