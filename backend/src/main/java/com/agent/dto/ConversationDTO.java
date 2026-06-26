package com.agent.dto;

import lombok.Data;
import java.time.LocalDateTime;
import java.util.List;

@Data
public class ConversationDTO {
    private Long id;
    private String title;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
    private List<MessageDTO> messages;
}