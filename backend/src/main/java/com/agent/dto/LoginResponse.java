package com.agent.dto;

import lombok.Data;

@Data
public class LoginResponse {
    private String token;
    private String username;
    private Long userId;
    
    public LoginResponse(String token, String username, Long userId) {
        this.token = token;
        this.username = username;
        this.userId = userId;
    }
}