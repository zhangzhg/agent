package com.agent.service;

import com.agent.dto.LoginRequest;
import com.agent.dto.LoginResponse;

public interface UserService {
    LoginResponse login(LoginRequest request);
}