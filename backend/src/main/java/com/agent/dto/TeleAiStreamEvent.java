package com.agent.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 星辰智能体流式事件 DTO
 * 用于接收流式响应的事件数据
 * 
 * TeleAi API 流式事件类型：
 * - message：普通消息
 * - message_end：结束事件
 * - error：异常事件
 * - node_started：工作流节点开始
 * - node_finished：工作流节点完成
 * - agent_thought：智能体思考过程
 * 
 * 使用 @JsonIgnoreProperties(ignoreUnknown = true) 忽略未知字段，避免解析错误
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)  // ✅ 忽略未知字段，避免 JSON 解析错误
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
    
    // ========== agent_thought 事件字段（智能体思考过程）==========
    
    /**
     * 思考位置（agent_thought 事件）
     */
    private Integer position;
    
    /**
     * 思考内容（agent_thought 事件）
     */
    private String thought;
    
    /**
     * 观察结果（agent_thought 事件）
     */
    private String observation;
    
    /**
     * 工具名称（agent_thought 事件）
     */
    private String tool;
    
    /**
     * 工具输入（agent_thought 事件）
     */
    @JsonProperty("tool_input")
    private String toolInput;
    
    
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
    
    /**
     * 判断是否为思考事件
     *
     * @return 是否为思考事件
     */
    public boolean isThought() {
        return "agent_thought".equals(event);
    }
}