package com.agent.util;

import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import cn.hutool.http.Method;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * HTTP 客户端工具类
 * 基于 Hutool 的 HttpRequest 封装，提供统一的 HTTP 请求处理
 */
@Component
public class HttpClientUtil {
    
    private static final Logger logger = LoggerFactory.getLogger(HttpClientUtil.class);
    
    private final ObjectMapper objectMapper = new ObjectMapper();
    
    /**
     * 默认超时时间（毫秒）
     */
    private static final int DEFAULT_TIMEOUT = 30000;
    
    /**
     * 发送 GET 请求
     *
     * @param url 请求地址
     * @return 响应内容
     */
    public String get(String url) {
        return get(url, null, DEFAULT_TIMEOUT);
    }
    
    /**
     * 发送 GET 请求（带请求头）
     *
     * @param url 请求地址
     * @param headers 请求头
     * @return 响应内容
     */
    public String get(String url, Map<String, String> headers) {
        return get(url, headers, DEFAULT_TIMEOUT);
    }
    
    /**
     * 发送 GET 请求（带请求头和超时时间）
     *
     * @param url 请求地址
     * @param headers 请求头
     * @param timeout 超时时间（毫秒）
     * @return 响应内容
     */
    public String get(String url, Map<String, String> headers, int timeout) {
        try {
            HttpRequest request = HttpRequest.get(url)
                .timeout(timeout);
            
            if (headers != null && !headers.isEmpty()) {
                request.addHeaders(headers);
            }
            
            HttpResponse response = request.execute();
            
            if (!response.isOk()) {
                logger.error("GET request failed: {} - Status: {}", url, response.getStatus());
                throw new RuntimeException("HTTP request failed with status: " + response.getStatus());
            }
            
            String body = response.body();
            logger.debug("GET request success: {} - Response length: {}", url, body.length());
            return body;
            
        } catch (Exception e) {
            logger.error("GET request error: {} - {}", url, e.getMessage());
            throw new RuntimeException("HTTP GET request failed: " + e.getMessage(), e);
        }
    }
    
    /**
     * 发送 POST 请求（JSON 格式）
     *
     * @param url 请求地址
     * @param body 请求体（对象会被序列化为 JSON）
     * @return 响应内容
     */
    public String post(String url, Object body) {
        return post(url, null, body, DEFAULT_TIMEOUT);
    }
    
    /**
     * 发送 POST 请求（JSON 格式，带请求头）
     *
     * @param url 请求地址
     * @param headers 请求头
     * @param body 请求体（对象会被序列化为 JSON）
     * @return 响应内容
     */
    public String post(String url, Map<String, String> headers, Object body) {
        return post(url, headers, body, DEFAULT_TIMEOUT);
    }
    
    /**
     * 发送 POST 请求（JSON 格式，带请求头和超时时间）
     *
     * @param url 请求地址
     * @param headers 请求头
     * @param body 请求体（对象会被序列化为 JSON）
     * @param timeout 超时时间（毫秒）
     * @return 响应内容
     */
    public String post(String url, Map<String, String> headers, Object body, int timeout) {
        try {
            String jsonBody = objectMapper.writeValueAsString(body);
            
            HttpRequest request = HttpRequest.post(url)
                .timeout(timeout)
                .contentType("application/json")
                .body(jsonBody);
            
            if (headers != null && !headers.isEmpty()) {
                request.addHeaders(headers);
            }
            
            HttpResponse response = request.execute();
            
            if (!response.isOk()) {
                logger.error("POST request failed: {} - Status: {} - Body: {}", 
                    url, response.getStatus(), response.body());
                throw new RuntimeException("HTTP request failed with status: " + response.getStatus());
            }
            
            String responseBody = response.body();
            logger.debug("POST request success: {} - Response length: {}", url, responseBody.length());
            return responseBody;
            
        } catch (Exception e) {
            logger.error("POST request error: {} - {}", url, e.getMessage());
            throw new RuntimeException("HTTP POST request failed: " + e.getMessage(), e);
        }
    }
    
    /**
     * 发送流式 POST 请求（用于 SSE 流式响应）
     *
     * @param url 请求地址
     * @param headers 请求头
     * @param body 请求体（对象会被序列化为 JSON）
     * @param timeout 超时时间（毫秒）
     * @return HttpResponse 对象（可用于流式读取）
     */
    public HttpResponse postStream(String url, Map<String, String> headers, Object body, int timeout) {
        try {
            String jsonBody = objectMapper.writeValueAsString(body);
            
            HttpRequest request = HttpRequest.post(url)
                .timeout(timeout)
                .contentType("application/json")
                .body(jsonBody);
            
            if (headers != null && !headers.isEmpty()) {
                request.addHeaders(headers);
            }
            
            HttpResponse response = request.execute();
            
            if (!response.isOk()) {
                logger.error("POST stream request failed: {} - Status: {}", url, response.getStatus());
                throw new RuntimeException("HTTP request failed with status: " + response.getStatus());
            }
            
            logger.debug("POST stream request success: {}", url);
            return response;
            
        } catch (Exception e) {
            logger.error("POST stream request error: {} - {}", url, e.getMessage());
            throw new RuntimeException("HTTP POST stream request failed: " + e.getMessage(), e);
        }
    }
    
    /**
     * 发送自定义 HTTP 请求
     *
     * @param url 请求地址
     * @param method 请求方法
     * @param headers 请求头
     * @param body 请求体
     * @param timeout 超时时间（毫秒）
     * @return 响应内容
     */
    public String request(String url, Method method, Map<String, String> headers, Object body, int timeout) {
        try {
            HttpRequest request = HttpRequest.of(url)
                .method(method)
                .timeout(timeout);
            
            if (headers != null && !headers.isEmpty()) {
                request.addHeaders(headers);
            }
            
            if (body != null) {
                String jsonBody = objectMapper.writeValueAsString(body);
                request.contentType("application/json").body(jsonBody);
            }
            
            HttpResponse response = request.execute();
            
            if (!response.isOk()) {
                logger.error("HTTP request failed: {} {} - Status: {}", method, url, response.getStatus());
                throw new RuntimeException("HTTP request failed with status: " + response.getStatus());
            }
            
            String responseBody = response.body();
            logger.debug("HTTP request success: {} {} - Response length: {}", method, url, responseBody.length());
            return responseBody;
            
        } catch (Exception e) {
            logger.error("HTTP request error: {} {} - {}", method, url, e.getMessage());
            throw new RuntimeException("HTTP request failed: " + e.getMessage(), e);
        }
    }
    
    /**
     * 将 JSON 字符串转换为对象
     *
     * @param json JSON 字符串
     * @param clazz 目标类型
     * @return 对象
     */
    public <T> T parseJson(String json, Class<T> clazz) {
        try {
            return objectMapper.readValue(json, clazz);
        } catch (Exception e) {
            logger.error("JSON parse error: {}", e.getMessage());
            throw new RuntimeException("JSON parse failed: " + e.getMessage(), e);
        }
    }
    
    /**
     * 将对象转换为 JSON 字符串
     *
     * @param obj 对象
     * @return JSON 字符串
     */
    public String toJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            logger.error("JSON serialize error: {}", e.getMessage());
            throw new RuntimeException("JSON serialize failed: " + e.getMessage(), e);
        }
    }
}