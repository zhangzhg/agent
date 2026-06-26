package com.agent.config;

import ai.djl.ModelException;
import ai.djl.inference.Predictor;
import ai.djl.repository.zoo.Criteria;
import ai.djl.repository.zoo.ZooModel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * DJL 模型配置类
 * 用于加载 sentence-transformers 模型进行文本嵌入
 */
@Configuration
public class DjlModelConfig {
    
    private static final Logger logger = LoggerFactory.getLogger(DjlModelConfig.class);
    
    @Autowired
    private EmbeddingProperties embeddingProperties;
    
    /**
     * 创建 ZooModel Bean
     * 只有在 embedding.enabled=true 时才创建
     * 支持自动下载模型
     */
    @Bean
    @ConditionalOnProperty(name = "embedding.enabled", havingValue = "true")
    public ZooModel<String, float[]> embeddingModel() {
        try {
            Path localModelPath = Paths.get(embeddingProperties.getModelPath());
            
            // 检查模型路径是否存在
            if (!Files.exists(localModelPath)) {
                logger.info("Local model not found at {}, attempting to download from HuggingFace...", 
                    embeddingProperties.getModelPath());
                
                // 使用 HuggingFace 模型 ID 自动下载
                return loadModelFromHuggingFace();
            }
            
            logger.info("Loading embedding model from local path: {}", localModelPath);
            
            Criteria<String, float[]> criteria = Criteria.builder()
                .setTypes(String.class, float[].class)
                .optModelPath(localModelPath)
                .optEngine("PyTorch")
                .optOption("mapLocation", "true") // 允许 CPU 加载 GPU 训练的模型
                .build();
            
            ZooModel<String, float[]> model = criteria.loadModel();
            logger.info("Embedding model loaded successfully from local path");
            
            return model;
            
        } catch (ModelException | IOException e) {
            logger.error("Failed to load embedding model: {}", e.getMessage());
            logger.info("Falling back to mock embedding service");
            throw new RuntimeException("Failed to load embedding model", e);
        }
    }
    
    /**
     * 从 HuggingFace 自动下载模型
     * DJL 会自动下载模型到 ~/.djl.ai/cache 目录
     */
    private ZooModel<String, float[]> loadModelFromHuggingFace() throws ModelException, IOException {
        logger.info("Downloading model from HuggingFace: {}", embeddingProperties.getModelName());
        
        // 使用 optModelUrls 指定 HuggingFace 模型 URL
        // DJL 会自动下载并缓存模型
        Criteria<String, float[]> criteria = Criteria.builder()
            .setTypes(String.class, float[].class)
            .optModelUrls("djl://ai.djl.huggingface.pytorch/" + embeddingProperties.getModelName())
            .optEngine("PyTorch")
            .optOption("mapLocation", "true")
            .build();
        
        ZooModel<String, float[]> model = criteria.loadModel();
        logger.info("Embedding model downloaded and loaded successfully from HuggingFace");
        
        return model;
    }
    
    /**
     * 创建 Predictor Bean
     * 只有在 embeddingModel bean 存在时才创建
     */
    @Bean
    @ConditionalOnBean(name = "embeddingModel")
    public Predictor<String, float[]> embeddingPredictor(ZooModel<String, float[]> model) {
        try {
            Predictor<String, float[]> predictor = model.newPredictor();
            logger.info("Embedding predictor created successfully");
            return predictor;
        } catch (Exception e) {
            logger.error("Failed to create embedding predictor: {}", e.getMessage());
            throw new RuntimeException("Failed to create embedding predictor", e);
        }
    }
}