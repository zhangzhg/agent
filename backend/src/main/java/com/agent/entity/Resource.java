package com.agent.entity;

import com.agent.config.LocalDateTimeTypeHandler;
import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import org.apache.ibatis.type.JdbcType;
import java.time.LocalDateTime;

@Data
@TableName("resource")
public class Resource {
    @TableId(type = IdType.AUTO)
    private Long id;
    
    private String resourceName;
    
    private String resourceCode;
    
    private String resourceType;
    
    private String url;
    
    private Long parentId;
    
    private Integer sortOrder;
    
    private String icon;
    
    private Integer status;
    
    @TableField(fill = FieldFill.INSERT, typeHandler = LocalDateTimeTypeHandler.class, jdbcType = JdbcType.TIMESTAMP)
    private LocalDateTime createTime;
    
    @TableField(fill = FieldFill.INSERT_UPDATE, typeHandler = LocalDateTimeTypeHandler.class, jdbcType = JdbcType.TIMESTAMP)
    private LocalDateTime updateTime;
    
    @TableLogic
    private Integer deleted;
}