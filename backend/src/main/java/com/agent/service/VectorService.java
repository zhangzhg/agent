package com.agent.service;

import com.agent.entity.Message;
import java.util.List;

/**
 * 向量服务接口，用于向量存储和检索
 */
public interface VectorService {
    
    /**
     * 保存消息的向量嵌入
     * @param messageId 消息ID
     * @param embedding 向量嵌入
     */
    void saveEmbedding(Long messageId, float[] embedding);
    
    /**
     * 获取消息的向量嵌入
     * @param messageId 消息ID
     * @return 向量嵌入，如果不存在则返回null
     */
    float[] getEmbedding(Long messageId);
    
    /**
     * 查找相似消息
     * @param conversationId 对话ID
     * @param queryEmbedding 查询向量
     * @param threshold 相似度阈值（0-1之间）
     * @param topK 返回的最大数量
     * @return 相似消息列表，按相似度降序排列
     */
    List<Message> findSimilarMessages(Long conversationId, float[] queryEmbedding, float threshold, int topK);
    
    /**
     * 计算两个向量的余弦相似度
     * @param vec1 向量1
     * @param vec2 向量2
     * @return 余弦相似度（-1到1之间）
     */
    float cosineSimilarity(float[] vec1, float[] vec2);
}