package com.agent.entity;

import com.agent.config.LocalDateTimeTypeHandler;
import com.agent.handler.SqliteBlobTypeHandler;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import org.apache.ibatis.type.ByteArrayTypeHandler;
import org.apache.ibatis.type.JdbcType;
import java.time.LocalDateTime;

@Data
@TableName("message")
public class Message {
    @TableId(type = IdType.AUTO)
    private Long id;
    
    private Long conversationId;
    
    private String role;
    
    private String content;

    @TableField(value = "embedding", typeHandler = SqliteBlobTypeHandler.class)
    private byte[] embedding;
    
    @TableField(fill = FieldFill.INSERT, typeHandler = LocalDateTimeTypeHandler.class, jdbcType = JdbcType.TIMESTAMP)
    private LocalDateTime createTime;
}