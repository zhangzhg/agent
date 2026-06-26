package com.agent.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 星辰智能体响应 DTO
 * 用于接收聊天消息响应
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TeleAiResponse {
    
    /**
     * 消息 ID
     */
    @JsonProperty("message_id")
    private String messageId;
    
    /**
     * 对话 ID
     */
    @JsonProperty("conversation_id")
    private String conversationId;
    
    /**
     * 模式
     */
    private String mode;
    
    /**
     * 响应内容
     */
    private String answer;
    
    /**
     * 创建时间
     */
    @JsonProperty("created_at")
    private Long createdAt;
    
    /**
     * 用户标识
     */
    private String user;
    
    /**
     * 元数据
     */
    private Metadata metadata;
    
    /**
     * 元数据类
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Metadata {
        
        /**
         * 使用情况
         */
        @JsonProperty("usage")
        private Usage usage;
        
        /**
         * 使用情况类
         */
        @Data
        @Builder
        @NoArgsConstructor
        @AllArgsConstructor
        public static class Usage {
            
            /**
             * 提示词 token 数
             */
            @JsonProperty("prompt_tokens")
            private Integer promptTokens;
            
            /**
             * 完成 token 数
             */
            @JsonProperty("completion_tokens")
            private Integer completionTokens;
            
            /**
             * 总 token 数
             */
            @JsonProperty("total_tokens")
            private Integer totalTokens;
        }
    }
    
    /**
     * 判断响应是否成功
     *
     * @return 是否成功
     */
    public boolean isSuccess() {
        return messageId != null && !messageId.isEmpty();
    }
}