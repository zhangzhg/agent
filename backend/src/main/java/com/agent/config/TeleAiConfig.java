package com.agent.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * 星辰智能体配置类
 * 用于配置星辰智能体 API 的连接参数
 */
@Data
@Configuration
@ConfigurationProperties(prefix = "teleai")
public class TeleAiConfig {
    
    /**
     * API 基础地址
     * 默认值：https://agent.teleai.com.cn/v1
     */
    private String baseUrl = "https://agent.teleai.com.cn/v1";
    
    /**
     * API Key
     * 格式：app-xxx
     */
    private String apiKey;
    
    /**
     * HTTP 请求超时时间（毫秒）
     * 默认值：30000 (30秒)
     */
    private int timeout = 30000;
    
    /**
     * 流式响应超时时间（毫秒）
     * 默认值：60000 (60秒)
     */
    private int streamTimeout = 60000;
    
    /**
     * 默认用户标识
     */
    private String defaultUser = "admin";
    
    /**
     * 默认模式
     * 可选值：streaming, blocking
     */
    private String defaultMode = "streaming";
    
    /**
     * 获取 Authorization 请求头
     * 格式：Bearer {api_key}
     *
     * @return Authorization 请求头
     */
    public String getAuthorizationHeader() {
        return "Bearer " + apiKey;
    }

}