package com.agent.service;

import java.util.List;

/**
 * 嵌入服务接口，用于将文本转换为向量表示
 */
public interface EmbeddingService {
    
    /**
     * 将文本转换为向量嵌入
     * @param text 输入文本
     * @return 向量嵌入（float数组）
     */
    float[] embed(String text);
    
    /**
     * 批量将文本转换为向量嵌入
     * @param texts 输入文本列表
     * @return 向量嵌入列表
     */
    List<float[]> embedBatch(List<String> texts);
    
    /**
     * 获取嵌入向量的维度
     * @return 向量维度
     */
    int getDimension();
}