package com.agent.util;

import org.springframework.security.core.context.SecurityContextHolder;

/**
 * Session工具类，用于获取当前登录用户信息
 */
public class SessionUtil {
    
    /**
     * 获取当前登录用户的ID
     * @return 用户ID，如果未登录则返回null
     */
    public static Long getUserId() {
        try {
            Object details = SecurityContextHolder.getContext().getAuthentication().getDetails();
            if (details instanceof Long) {
                return (Long) details;
            }
            return null;
        } catch (Exception e) {
            return null;
        }
    }
    
    /**
     * 获取当前登录用户的用户名
     * @return 用户名，如果未登录则返回null
     */
    public static String getUsername() {
        try {
            return SecurityContextHolder.getContext().getAuthentication().getName();
        } catch (Exception e) {
            return null;
        }
    }
    
    /**
     * 检查用户是否已登录
     * @return true表示已登录，false表示未登录
     */
    public static boolean isAuthenticated() {
        try {
            return SecurityContextHolder.getContext().getAuthentication() != null 
                && SecurityContextHolder.getContext().getAuthentication().isAuthenticated();
        } catch (Exception e) {
            return false;
        }
    }
}