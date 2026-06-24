package com.agent.util;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

public class PasswordGenerator {
    
    private static final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();
    
    public static String encode(String rawPassword) {
        return passwordEncoder.encode(rawPassword);
    }
    
    public static boolean matches(String rawPassword, String encodedPassword) {
        return passwordEncoder.matches(rawPassword, encodedPassword);
    }
    
    public static void main(String[] args) {
        if (args.length == 0) {
            System.out.println("使用方法:");
            System.out.println("1. 生成密码: java PasswordGenerator <原始密码>");
            System.out.println("2. 验证密码: java PasswordGenerator <原始密码> <加密密码>");
            System.out.println("\n示例:");
            System.out.println("java PasswordGenerator admin123");
            System.out.println("java PasswordGenerator admin123 $2a$10$...");
            
            // 默认生成几个常用密码
            System.out.println("\n=== 常用密码生成 ===");
            generateCommonPasswords();
            return;
        }
        
        if (args.length == 1) {
            String rawPassword = args[0];
            String encodedPassword = encode(rawPassword);
            System.out.println("原始密码: " + rawPassword);
            System.out.println("加密密码: " + encodedPassword);
            System.out.println("\nSQL插入语句:");
            System.out.println("INSERT INTO user (username, password, email, status) VALUES ('用户名', '" + encodedPassword + "', '邮箱', 1);");
        } else if (args.length == 2) {
            String rawPassword = args[0];
            String encodedPassword = args[1];
            boolean matches = matches(rawPassword, encodedPassword);
            System.out.println("原始密码: " + rawPassword);
            System.out.println("加密密码: " + encodedPassword);
            System.out.println("验证结果: " + (matches ? "匹配成功 ✓" : "匹配失败 ✗"));
        }
    }
    
    private static void generateCommonPasswords() {
        String[] passwords = {"admin123", "123456", "password", "test123"};
        for (String password : passwords) {
            String encoded = encode(password);
            System.out.println("密码: " + password + " => " + encoded);
        }
    }
}