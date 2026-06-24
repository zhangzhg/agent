package com.agent.service.impl;

import com.agent.mapper.UserMapper;
import com.agent.dto.LoginRequest;
import com.agent.dto.LoginResponse;
import com.agent.entity.User;
import com.agent.service.UserService;
import com.agent.util.EncryptionUtil;
import com.agent.util.JwtUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;


@Slf4j
@Service
public class UserServiceImpl implements UserService {
    
    @Resource
    private UserMapper userMapper;
    
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();
    
    @Override
    public LoginResponse login(LoginRequest request) {
        String username = request.getUsername();
        String encryptedPassword = request.getPassword();
        
        String password = EncryptionUtil.decrypt(encryptedPassword);
        
        LambdaQueryWrapper<User> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(User::getUsername, username);
        User user = userMapper.selectOne(queryWrapper);
        
        if (user == null) {
            throw new RuntimeException("用户不存在");
        }
        
        if (!passwordEncoder.matches(password, user.getPassword())) {
            throw new RuntimeException("密码错误");
        }
        
        if (user.getStatus() != 1) {
            throw new RuntimeException("用户已被禁用");
        }
        
        String token = JwtUtil.generateToken(username, user.getId());
        
        log.info("用户登录成功: {}", username);
        
        return new LoginResponse(token, username, user.getId());
    }
}