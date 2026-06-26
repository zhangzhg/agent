package com.agent.service.impl;

import com.agent.service.EmbeddingService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * Mock 嵌入服务实现，用于演示和测试
 * 生成随机向量，实际应用中应替换为真实的嵌入模型
 * 当 DJL Embedding Service 未启用时，此服务作为备用方案
 */
@Service
@ConditionalOnMissingBean(DjlEmbeddingServiceImpl.class)
public class MockEmbeddingServiceImpl implements EmbeddingService {
    
    private final Random random = new Random(42); // 使用固定种子以保证一致性
    private final int dimension = 384; // 使用常见的嵌入维度
    
    @Override
    public float[] embed(String text) {
        // 生成基于文本内容的伪向量（实际应用中应使用真实模型）
        float[] embedding = new float[dimension];
        
        // 使用文本的哈希值作为随机种子，使相同文本生成相同向量
        int hash = text.hashCode();
        Random textRandom = new Random(hash);
        
        for (int i = 0; i < dimension; i++) {
            embedding[i] = (textRandom.nextFloat() - 0.5f) * 2; // 生成 -1 到 1 之间的随机值
        }
        
        // 归一化向量
        normalize(embedding);
        
        return embedding;
    }
    
    @Override
    public List<float[]> embedBatch(List<String> texts) {
        List<float[]> embeddings = new ArrayList<>();
        for (String text : texts) {
            embeddings.add(embed(text));
        }
        return embeddings;
    }
    
    @Override
    public int getDimension() {
        return dimension;
    }
    
    /**
     * 归一化向量（L2归一化）
     */
    private void normalize(float[] vector) {
        float sum = 0;
        for (float v : vector) {
            sum += v * v;
        }
        float norm = (float) Math.sqrt(sum);
        if (norm > 0) {
            for (int i = 0; i < vector.length; i++) {
                vector[i] /= norm;
            }
        }
    }
}