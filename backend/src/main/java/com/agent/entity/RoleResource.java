package com.agent.entity;

import com.agent.config.LocalDateTimeTypeHandler;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import org.apache.ibatis.type.JdbcType;
import java.time.LocalDateTime;

@Data
@TableName("role_resource")
public class RoleResource {
    @TableId(type = IdType.AUTO)
    private Long id;
    
    private Long roleId;
    
    private Long resourceId;
    
    @TableField(fill = FieldFill.INSERT, typeHandler = LocalDateTimeTypeHandler.class, jdbcType = JdbcType.TIMESTAMP)
    private LocalDateTime createTime;
}