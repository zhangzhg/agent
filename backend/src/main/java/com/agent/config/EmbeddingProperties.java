package com.agent.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * Embedding 配置属性类
 */
@Configuration
@ConfigurationProperties(prefix = "embedding")
public class EmbeddingProperties {
    
    /**
     * 是否启用 DJL embedding
     */
    private boolean enabled = false;
    
    /**
     * 模型路径（本地路径）
     */
    private String modelPath = "models/sentence-transformers";
    
    /**
     * 模型名称（HuggingFace 模型名称）
     */
    private String modelName = "sentence-transformers/all-MiniLM-L6-v2";
    
    /**
     * 向量维度
     */
    private int dimension = 384;
    
    public boolean isEnabled() {
        return enabled;
    }
    
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
    
    public String getModelPath() {
        return modelPath;
    }
    
    public void setModelPath(String modelPath) {
        this.modelPath = modelPath;
    }
    
    public String getModelName() {
        return modelName;
    }
    
    public void setModelName(String modelName) {
        this.modelName = modelName;
    }
    
    public int getDimension() {
        return dimension;
    }
    
    public void setDimension(int dimension) {
        this.dimension = dimension;
    }
}