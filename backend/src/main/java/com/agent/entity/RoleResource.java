package com.agent.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("role_resource")
public class RoleResource {
    @TableId(type = IdType.AUTO)
    private Long id;
    
    private Long roleId;
    
    private Long resourceId;
    
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;
}