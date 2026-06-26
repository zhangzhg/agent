package com.agent.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import jakarta.annotation.PostConstruct;

import java.io.File;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;

/**
 * SQLite Vec 扩展配置类（可选）
 * 用于加载 sqlite-vec 扩展，提供向量搜索功能
 * 
 * 注意：sqlite-vec 需要手动编译为共享库（.so/.dll/.dylib）
 * 如果扩展不可用，系统会使用默认的向量检索实现
 */
@Configuration
public class SQLiteVecConfig {
    
    private static final Logger logger = LoggerFactory.getLogger(SQLiteVecConfig.class);
    
    @Value("${sqlite.vec.enabled:false}")
    private boolean vecEnabled;
    
    @Value("${sqlite.vec.path:}")
    private String vecExtensionPath;
    
    @Value("${spring.datasource.url}")
    private String datasourceUrl;
    
    @PostConstruct
    public void init() {
        if (!vecEnabled) {
            logger.info("SQLite Vec extension is disabled, using default vector implementation");
            return;
        }
        
        if (vecExtensionPath == null || vecExtensionPath.isEmpty()) {
            logger.warn("SQLite Vec extension path is not configured");
            logger.info("To enable sqlite-vec, compile the extension and set sqlite.vec.path in application.yml");
            return;
        }
        
        try {
            loadVecExtension();
            logger.info("SQLite Vec extension loaded successfully from: {}", vecExtensionPath);
        } catch (Exception e) {
            logger.error("Failed to load SQLite Vec extension: {}", e.getMessage());
            logger.info("Falling back to default vector implementation");
        }
    }
    
    /**
     * 加载 sqlite-vec 扩展
     * 需要在连接 URL 中添加 enable_load_extension=true 参数
     */
    private void loadVecExtension() throws Exception {
        // 检查扩展文件是否存在
        File extensionFile = new File(vecExtensionPath);
        if (!extensionFile.exists()) {
            throw new RuntimeException("SQLite Vec extension file not found: " + vecExtensionPath);
        }
        
        // 构建支持扩展加载的连接 URL
        String connectionUrl = datasourceUrl;
        if (!connectionUrl.contains("enable_load_extension")) {
            connectionUrl += "?enable_load_extension=true";
        }
        
        // 加载扩展
        try (Connection conn = DriverManager.getConnection(connectionUrl);
             Statement stmt = conn.createStatement()) {
            
            // 加载 sqlite-vec 扩展
            stmt.execute("SELECT load_extension('" + vecExtensionPath + "')");
            
            // 验证扩展加载成功
            var rs = stmt.executeQuery("SELECT vec_version()");
            if (rs.next()) {
                String version = rs.getString(1);
                logger.info("SQLite Vec extension version: {}", version);
            }
        }
    }
}