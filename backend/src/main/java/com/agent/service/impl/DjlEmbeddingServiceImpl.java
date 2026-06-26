package com.agent.service.impl;

import ai.djl.inference.Predictor;
import ai.djl.translate.TranslateException;
import com.agent.config.EmbeddingProperties;
import com.agent.service.EmbeddingService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;
import java.util.ArrayList;
import java.util.List;

/**
 * DJL Embedding 服务实现
 * 使用 DJL 加载 sentence-transformers 模型进行真实的文本嵌入
 * 只有在 embedding.enabled=true 时才会创建
 */
@Service
@Primary
@ConditionalOnProperty(name = "embedding.enabled", havingValue = "true")
public class DjlEmbeddingServiceImpl implements EmbeddingService {
    
    private static final Logger logger = LoggerFactory.getLogger(DjlEmbeddingServiceImpl.class);
    
    @Autowired(required = false)
    private Predictor<String, float[]> predictor;
    
    @Autowired
    private EmbeddingProperties embeddingProperties;
    
    private boolean initialized = false;
    
    @PostConstruct
    public void init() {
        if (predictor != null) {
            initialized = true;
            logger.info("DJL Embedding Service initialized successfully with dimension: {}", 
                embeddingProperties.getDimension());
        } else {
            logger.warn("DJL predictor not available, service will not function properly");
            initialized = false;
        }
    }
    
    @Override
    public float[] embed(String text) {
        if (!initialized || predictor == null) {
            logger.warn("DJL embedding service not initialized, returning null embedding");
            return new float[embeddingProperties.getDimension()]; // 返回空向量
        }
        
        try {
            float[] embedding = predictor.predict(text);
            logger.debug("Generated embedding for text: {} (length: {})", 
                text.substring(0, Math.min(text.length(), 50)), embedding.length);
            return embedding;
        } catch (TranslateException e) {
            logger.error("Failed to generate embedding for text: {}", e.getMessage());
            return new float[embeddingProperties.getDimension()]; // 返回空向量
        }
    }
    
    @Override
    public List<float[]> embedBatch(List<String> texts) {
        List<float[]> embeddings = new ArrayList<>();
        
        if (!initialized || predictor == null) {
            logger.warn("DJL embedding service not initialized, returning empty embeddings");
            for (int i = 0; i < texts.size(); i++) {
                embeddings.add(new float[embeddingProperties.getDimension()]);
            }
            return embeddings;
        }
        
        try {
            for (String text : texts) {
                embeddings.add(embed(text));
            }
            logger.debug("Generated embeddings for {} texts", texts.size());
            return embeddings;
        } catch (Exception e) {
            logger.error("Failed to generate embeddings batch: {}", e.getMessage());
            // 返回空向量列表
            for (int i = 0; i < texts.size(); i++) {
                embeddings.add(new float[embeddingProperties.getDimension()]);
            }
            return embeddings;
        }
    }
    
    @Override
    public int getDimension() {
        return embeddingProperties.getDimension();
    }
    
    /**
     * 检查服务是否已初始化
     * @return true 如果已初始化，否则 false
     */
    public boolean isInitialized() {
        return initialized;
    }
}