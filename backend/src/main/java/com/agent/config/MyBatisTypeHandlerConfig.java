package com.agent.config;

import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.type.JdbcType;
import org.apache.ibatis.type.TypeHandlerRegistry;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Configuration;

import jakarta.annotation.PostConstruct;
import java.time.LocalDateTime;

/**
 * MyBatis TypeHandler 配置类
 * 手动注册 LocalDateTime TypeHandler，确保它优先于 JDBC 驱动的默认处理
 */
@Configuration
@ConditionalOnClass(SqlSessionFactory.class)
public class MyBatisTypeHandlerConfig {
    
    @Autowired
    private SqlSessionFactory sqlSessionFactory;
    
    @PostConstruct
    public void registerTypeHandlers() {
        TypeHandlerRegistry typeHandlerRegistry = sqlSessionFactory.getConfiguration().getTypeHandlerRegistry();
        
        // 注册 LocalDateTime TypeHandler，覆盖默认的处理器
        LocalDateTimeTypeHandler typeHandler = new LocalDateTimeTypeHandler();
        
        // 注册多种 JdbcType，确保覆盖所有情况
        typeHandlerRegistry.register(LocalDateTime.class, JdbcType.TIMESTAMP, typeHandler);
        typeHandlerRegistry.register(LocalDateTime.class, JdbcType.DATE, typeHandler);
        typeHandlerRegistry.register(LocalDateTime.class, JdbcType.TIME, typeHandler);
        typeHandlerRegistry.register(LocalDateTime.class, null, typeHandler);
        
        // 也注册为未指定类型的默认处理器
        typeHandlerRegistry.register(LocalDateTime.class, typeHandler);
    }
}