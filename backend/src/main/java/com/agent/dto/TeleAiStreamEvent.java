package com.agent.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 星辰智能体流式事件 DTO
 * 用于接收流式响应的事件数据
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TeleAiStreamEvent {
    
    /**
     * 事件类型
     * 可选值：message（普通消息）、message_end（结束）、error（异常）
     */
    private String event;
    
    /**
     * 任务 ID
     */
    @JsonProperty("task_id")
    private String taskId;

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
     * 回答内容（message 事件）
     */
    private String answer;
    
    /**
     * 创建时间
     */
    @JsonProperty("created_at")
    private Long createdAt;

    /**
     * 消息 ID
     */
    private String id;
    
    /**
     * 错误码（error 事件）
     */
    private Integer code;
    
    /**
     * 错误消息（error 事件）
     */
    private String message;
    
    
    /**
     * 判断是否为消息事件
     *
     * @return 是否为消息事件
     */
    public boolean isMessage() {
        return "message".equals(event);
    }
    
    /**
     * 判断是否为结束事件
     *
     * @return 是否为结束事件
     */
    public boolean isEnd() {
        return "message_end".equals(event);
    }
    
    /**
     * 判断是否为错误事件
     *
     * @return 是否为错误事件
     */
    public boolean isError() {
        return "error".equals(event);
    }
}