package com.agent.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 星辰智能体文件 DTO
 * 用于传递文件信息（如图片）
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TeleAiFile {
    
    /**
     * 文件类型
     * 可选值：image, document 等
     */
    private String type;
    
    /**
     * 传输方式
     * 可选值：remote_url（远程 URL）, local_file（本地文件）
     */
    @JsonProperty("transfer_method")
    private String transferMethod;
    
    /**
     * 文件 URL（远程方式）
     */
    private String url;
    
    /**
     * 创建图片文件（远程 URL）
     *
     * @param imageUrl 图片 URL
     * @return 文件对象
     */
    public static TeleAiFile createImage(String imageUrl) {
        return TeleAiFile.builder()
            .type("image")
            .transferMethod("remote_url")
            .url(imageUrl)
            .build();
    }
    
    /**
     * 创建文档文件（远程 URL）
     *
     * @param documentUrl 文档 URL
     * @return 文件对象
     */
    public static TeleAiFile createDocument(String documentUrl) {
        return TeleAiFile.builder()
            .type("document")
            .transferMethod("remote_url")
            .url(documentUrl)
            .build();
    }
}