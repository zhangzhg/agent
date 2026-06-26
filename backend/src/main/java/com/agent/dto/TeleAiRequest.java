package com.agent.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * 星辰智能体请求 DTO
 * 用于发送聊天消息请求
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TeleAiRequest {
    
    /**
     * 输入数据（可选）
     * 用于传递额外的输入参数
     */
    private Map<String, Object> inputData;
    
    /**
     * 用户查询内容
     * 必填字段
     */
    private String query;
    
    /**
     * 对话 ID
     * 用于保持对话上下文
     * 首次对话时为空字符串
     */
    private String conversationId;
    
    /**
     * 响应模式
     * 可选值：streaming（流式）, blocking（阻塞）
     */
    private String mode;
    
    /**
     * 用户标识
     * 用于区分不同用户
     */
    private String user;
    
    /**
     * 文件列表（可选）
     * 支持图片等文件类型
     */
    private List<TeleAiFile> files;
    
    /**
     * 创建简单的聊天请求（无文件）
     *
     * @param query 查询内容
     * @param user 用户标识
     * @return 请求对象
     */
    public static TeleAiRequest createSimple(String query, String user) {
        return TeleAiRequest.builder()
            .query(query)
            .conversationId("")
            .mode("streaming")
            .user(user)
            .build();
    }
    
    /**
     * 创建带对话 ID 的聊天请求
     *
     * @param query 查询内容
     * @param conversationId 对话 ID
     * @param user 用户标识
     * @return 请求对象
     */
    public static TeleAiRequest createWithConversation(String query, String conversationId, String user) {
        return TeleAiRequest.builder()
            .query(query)
            .conversationId(conversationId)
            .mode("streaming")
            .user(user)
            .build();
    }
    
    /**
     * 创建带图片的聊天请求
     *
     * @param query 查询内容
     * @param imageUrl 图片 URL
     * @param user 用户标识
     * @return 请求对象
     */
    public static TeleAiRequest createWithImage(String query, String imageUrl, String user) {
        return TeleAiRequest.builder()
            .query(query)
            .conversationId("")
            .mode("streaming")
            .user(user)
            .files(List.of(TeleAiFile.createImage(imageUrl)))
            .build();
    }
}