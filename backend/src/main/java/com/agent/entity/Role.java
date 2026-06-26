package com.agent.entity;

import com.agent.config.LocalDateTimeTypeHandler;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import org.apache.ibatis.type.JdbcType;
import java.time.LocalDateTime;

@Data
@TableName("role")
public class Role {
    @TableId(type = IdType.AUTO)
    private Long id;
    
    private String roleName;
    
    private String roleCode;
    
    private String description;
    
    private Integer status;
    
    @TableField(fill = FieldFill.INSERT, typeHandler = LocalDateTimeTypeHandler.class, jdbcType = JdbcType.TIMESTAMP)
    private LocalDateTime createTime;
    
    @TableField(fill = FieldFill.INSERT_UPDATE, typeHandler = LocalDateTimeTypeHandler.class, jdbcType = JdbcType.TIMESTAMP)
    private LocalDateTime updateTime;
    
    @TableLogic
    private Integer deleted;
}