package com.agent.dto;

import lombok.Data;
import java.time.LocalDateTime;

@Data
public class MessageDTO {
    private Long id;
    private String role;
    private String content;
    private LocalDateTime createTime;
}