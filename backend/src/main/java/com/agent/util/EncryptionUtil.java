package com.agent.util;

import cn.hutool.crypto.Mode;
import cn.hutool.crypto.Padding;
import cn.hutool.crypto.symmetric.AES;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;

@Component
public class EncryptionUtil {
    
    @Value("${encryption.aes-key}")
    private String aesKeyConfig;
    
    private static AES aes;
    
    @PostConstruct
    public void init() {
        byte[] key = aesKeyConfig.getBytes(StandardCharsets.UTF_8);
        aes = new AES(Mode.ECB, Padding.PKCS5Padding, key);
    }
    
    public static String encrypt(String content) {
        if (content == null || content.isEmpty()) {
            return content;
        }
        return aes.encryptBase64(content);
    }
    
    public static String decrypt(String encryptedContent) {
        if (encryptedContent == null || encryptedContent.isEmpty()) {
            return encryptedContent;
        }
        return aes.decryptStr(encryptedContent);
    }
}