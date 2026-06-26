package com.agent.entity;

import com.agent.config.LocalDateTimeTypeHandler;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import org.apache.ibatis.type.JdbcType;
import java.time.LocalDateTime;

@Data
@TableName("user_role")
public class UserRole {
    @TableId(type = IdType.AUTO)
    private Long id;
    
    private Long userId;
    
    private Long roleId;
    
    @TableField(fill = FieldFill.INSERT, typeHandler = LocalDateTimeTypeHandler.class, jdbcType = JdbcType.TIMESTAMP)
    private LocalDateTime createTime;
}