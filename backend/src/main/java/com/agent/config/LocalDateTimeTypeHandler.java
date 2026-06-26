package com.agent.config;

import org.apache.ibatis.type.BaseTypeHandler;
import org.apache.ibatis.type.JdbcType;
import org.apache.ibatis.type.MappedTypes;
import org.apache.ibatis.type.MappedJdbcTypes;

import java.sql.*;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/**
 * SQLite LocalDateTime TypeHandler
 * 处理 SQLite 的 ISO 8601 时间格式（包含 T 分隔符）转换为 LocalDateTime
 * 
 * SQLite 时间格式：
 * - ISO 8601: 2026-06-26T09:18:33.260958200 (包含 T 分隔符，9位纳秒)
 * - SQL 标准: 2026-06-26 09:18:33.260958 (空格分隔，6位纳秒)
 * 
 * 此 TypeHandler 支持两种格式的解析
 */
@MappedTypes(LocalDateTime.class)
@MappedJdbcTypes(JdbcType.TIMESTAMP)
public class LocalDateTimeTypeHandler extends BaseTypeHandler<LocalDateTime> {
    
    // ISO 8601 格式（包含 T 分隔符）
    private static final DateTimeFormatter ISO_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss[.SSSSSSSSS][.SSSSSS][.SSS]");
    
    // SQL 标准格式（空格分隔）
    private static final DateTimeFormatter SQL_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss[.SSSSSS][.SSS]");
    
    @Override
    public void setNonNullParameter(PreparedStatement ps, int i, LocalDateTime parameter, JdbcType jdbcType) throws SQLException {
        // 写入时使用 SQL 标准格式（无 T 分隔符）
        ps.setString(i, parameter.format(SQL_FORMATTER));
    }
    
    @Override
    public LocalDateTime getNullableResult(ResultSet rs, String columnName) throws SQLException {
        String timestamp = rs.getString(columnName);
        return parseTimestamp(timestamp);
    }
    
    @Override
    public LocalDateTime getNullableResult(ResultSet rs, int columnIndex) throws SQLException {
        String timestamp = rs.getString(columnIndex);
        return parseTimestamp(timestamp);
    }
    
    @Override
    public LocalDateTime getNullableResult(CallableStatement cs, int columnIndex) throws SQLException {
        String timestamp = cs.getString(columnIndex);
        return parseTimestamp(timestamp);
    }
    
    /**
     * 解析时间字符串
     * 支持多种格式：
     * 1. ISO 8601: 2026-06-26T09:18:33.260958200
     * 2. SQL 标准: 2026-06-26 09:18:33.260958
     * 3. 异常格式: 2026-06-26 09:48:04.829565.829（纳秒重复）
     * 
     * @param timestamp 时间字符串
     * @return LocalDateTime 对象
     */
    private LocalDateTime parseTimestamp(String timestamp) {
        if (timestamp == null || timestamp.trim().isEmpty()) {
            return null;
        }
        
        timestamp = timestamp.trim();
        
        try {
            // 先处理异常格式：纳秒部分重复（如 .829565.829）
            // 这种格式可能是 SQLite JDBC 驱动的 bug 导致的
            if (timestamp.contains(".")) {
                // 检查是否有多个点（纳秒重复）
                int firstDotIndex = timestamp.indexOf('.');
                int lastDotIndex = timestamp.lastIndexOf('.');
                
                if (firstDotIndex != lastDotIndex) {
                    // 有多个点，纳秒重复，需要截取第一个纳秒部分
                    // 例如：2026-06-26 09:48:04.829565.829 -> 2026-06-26 09:48:04.829565
                    timestamp = timestamp.substring(0, lastDotIndex);
                }
                
                // 检查纳秒位数，截取最多9位
                int nanoIndex = timestamp.indexOf('.') + 1;
                if (nanoIndex > 0 && nanoIndex < timestamp.length()) {
                    String nanoStr = timestamp.substring(nanoIndex);
                    if (nanoStr.length() > 9) {
                        timestamp = timestamp.substring(0, nanoIndex + 9);
                    }
                }
            }
            
            // 判断是 ISO 8601 格式（包含 T）还是 SQL 标准格式（包含空格）
            if (timestamp.contains("T")) {
                // ISO 8601 格式
                return LocalDateTime.parse(timestamp, ISO_FORMATTER);
            } else {
                // SQL 标准格式（空格分隔）
                return LocalDateTime.parse(timestamp, SQL_FORMATTER);
            }
        } catch (Exception e) {
            // 如果格式都不匹配，尝试使用默认的 LocalDateTime.parse()
            try {
                return LocalDateTime.parse(timestamp);
            } catch (Exception ex) {
                throw new RuntimeException("无法解析时间字符串: " + timestamp, ex);
            }
        }
    }
}