# Embedding Service 条件注入修复

## 🐛 问题描述

**用户反馈：**
"已经配置为 false，但是这个变量还是 DjlEmbeddingServiceImpl"

**问题根源：**
`DjlEmbeddingServiceImpl` 缺少条件注解 `@ConditionalOnProperty`，导致它总是会被 Spring 创建，即使 `embedding.enabled=false`。

**影响范围：**
- ✅ `ChatServiceImpl` 注入的 `EmbeddingService` 总是 `DjlEmbeddingServiceImpl`
- ✅ `DjlEmbeddingServiceImpl` 尝试加载 DJL 模型，即使配置禁用
- ✅ 可能导致启动失败或资源浪费

## ✅ 解决方案

### 方案架构

**条件注入机制：**
1. **DjlEmbeddingServiceImpl**：只在 `embedding.enabled=true` 时创建
2. **MockEmbeddingServiceImpl**：只在 `embedding.enabled=false` 或未配置时创建
3. **@Primary 注解**：确保正确的服务被注入

### 实施步骤

#### 1. 修改 DjlEmbeddingServiceImpl

**修改文件：** [DjlEmbeddingServiceImpl.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\service\impl\DjlEmbeddingServiceImpl.java)

**修改内容：**
```java
/**
 * DJL Embedding 服务实现
 * 使用 DJL 加载 sentence-transformers 模型进行真实的文本嵌入
 * 只有在 embedding.enabled=true 时才会创建
 */
@Service
@Primary
@ConditionalOnProperty(name = "embedding.enabled", havingValue = "true")
public class DjlEmbeddingServiceImpl implements EmbeddingService {
    ...
}
```

**关键注解：**
- ✅ `@ConditionalOnProperty(name = "embedding.enabled", havingValue = "true")`
- ✅ 只有配置为 true 时才创建此服务
- ✅ 避免 DJL 模型加载失败

#### 2. 修改 MockEmbeddingServiceImpl

**修改文件：** [MockEmbeddingServiceImpl.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\service\impl\MockEmbeddingServiceImpl.java)

**修改内容：**
```java
/**
 * Mock 嵌入服务实现，用于演示和测试
 * 生成随机向量，实际应用中应替换为真实的嵌入模型
 * 当 embedding.enabled=false 或未配置时，此服务作为备用方案
 */
@Service
@Primary
@ConditionalOnProperty(name = "embedding.enabled", havingValue = "false", matchIfMissing = true)
public class MockEmbeddingServiceImpl implements EmbeddingService {
    ...
}
```

**关键注解：**
- ✅ `@ConditionalOnProperty(name = "embedding.enabled", havingValue = "false", matchIfMissing = true)`
- ✅ 配置为 false 或未配置时创建此服务
- ✅ `matchIfMissing = true` 确保默认情况下使用 Mock 服务
- ✅ `@Primary` 确保此服务被优先注入

### 配置说明

**配置文件：** [application.yml](d:\workspace_tmp\agent\backend\src\main\resources\application.yml)

```yaml
# Embedding 本地向量化配置（DJL sentence-transformers）
embedding:
  enabled: false  # ✅ false → 使用 MockEmbeddingServiceImpl
  model-path: models/sentence-transformers
  model-name: sentence-transformers/all-MiniLM-L6-v2
  dimension: 384
```

**配置效果：**

| 配置值 | 创建的服务 | 说明 |
|--------|-----------|------|
| `embedding.enabled=true` | `DjlEmbeddingServiceImpl` | ✅ 使用 DJL 真实嵌入 |
| `embedding.enabled=false` | `MockEmbeddingServiceImpl` | ✅ 使用 Mock 随机向量 |
| 未配置 | `MockEmbeddingServiceImpl` | ✅ 默认使用 Mock |

## 📊 工作流程

### 启动时的条件注入流程

```
Spring Boot 启动
    ↓
扫描 Service 类
    ↓
检查 @ConditionalOnProperty
    ↓
┌─────────────────────────────────┐
│  DjlEmbeddingServiceImpl         │
│  @ConditionalOnProperty(         │
│    name = "embedding.enabled",   │
│    havingValue = "true"          │
│  )                               │
└─────────────────────────────────┘
    ↓
检查 embedding.enabled 配置
    ↓
    ├─ true  → 创建 DjlEmbeddingServiceImpl ✅
    ├─ false → 不创建 DjlEmbeddingServiceImpl ❌
    └─ 未配置 → 不创建 DjlEmbeddingServiceImpl ❌
    ↓
┌─────────────────────────────────┐
│  MockEmbeddingServiceImpl        │
│  @ConditionalOnProperty(         │
│    name = "embedding.enabled",   │
│    havingValue = "false",        │
│    matchIfMissing = true         │
│  )                               │
└─────────────────────────────────┘
    ↓
检查 embedding.enabled 配置
    ↓
    ├─ true  → 不创建 MockEmbeddingServiceImpl ❌
    ├─ false → 创建 MockEmbeddingServiceImpl ✅
    └─ 未配置 → 创建 MockEmbeddingServiceImpl ✅
    ↓
ChatServiceImpl 注入 EmbeddingService
    ↓
根据 @Primary 注解注入正确的服务 ✅
```

### ChatServiceImpl 注入流程

```
ChatServiceImpl 启动
    ↓
@Autowired EmbeddingService
    ↓
Spring 查找 EmbeddingService 实现
    ↓
检查哪个服务有 @Primary 注解
    ↓
┌─────────────────────────────────┐
│  embedding.enabled=true          │
│  DjlEmbeddingServiceImpl @Primary│
│  MockEmbeddingServiceImpl 不创建 │
└─────────────────────────────────┘
    ↓
注入 DjlEmbeddingServiceImpl ✅
    ↓
┌─────────────────────────────────┐
│  embedding.enabled=false         │
│  MockEmbeddingServiceImpl @Primary│
│  DjlEmbeddingServiceImpl 不创建  │
└─────────────────────────────────┘
    ↓
注入 MockEmbeddingServiceImpl ✅
```

## 🎯 解决的问题

### 问题 1：条件注入不生效

**旧方案：**
```java
// DjlEmbeddingServiceImpl
@Service
@Primary
public class DjlEmbeddingServiceImpl ...  // ❌ 总是创建

// MockEmbeddingServiceImpl
@Service
@ConditionalOnMissingBean(DjlEmbeddingServiceImpl.class)  // ❌ 永远不会创建
public class MockEmbeddingServiceImpl ...
```

**问题：**
- ❌ DjlEmbeddingServiceImpl 总是创建
- ❌ MockEmbeddingServiceImpl 永远不会创建（因为 DjlEmbeddingServiceImpl 总是存在）
- ❌ 配置不生效

**新方案：**
```java
// DjlEmbeddingServiceImpl
@Service
@Primary
@ConditionalOnProperty(name = "embedding.enabled", havingValue = "true")
public class DjlEmbeddingServiceImpl ...  // ✅ 条件创建

// MockEmbeddingServiceImpl
@Service
@Primary
@ConditionalOnProperty(name = "embedding.enabled", havingValue = "false", matchIfMissing = true)
public class MockEmbeddingServiceImpl ...  // ✅ 条件创建
```

**效果：**
- ✅ 根据配置选择正确的服务
- ✅ 避免 DJL 模型加载失败
- ✅ 配置生效

### 问题 2：默认行为不明确

**旧方案：** 未配置时行为不确定
**新方案：** 默认使用 Mock 服务（`matchIfMissing = true`）

**效果：**
- ✅ 默认行为明确
- ✅ 避免启动失败（DJL 模型未下载）
- ✅ 开发和测试更方便

## 🔍 两种服务的区别

| 特性 | DjlEmbeddingServiceImpl | MockEmbeddingServiceImpl |
|------|------------------------|--------------------------|
| **创建条件** | `embedding.enabled=true` | `embedding.enabled=false` 或未配置 |
| **向量生成** | 真实模型（sentence-transformers） | 随机向量（基于文本哈希） |
| **向量质量** | 高质量语义向量 | 低质量随机向量 |
| **资源占用** | 需要 DJL 模型（~100MB） | 无额外资源 |
| **适用场景** | 生产环境 | 开发、测试、演示 |
| **是否归一化** | ✅ 是 | ✅ 是 |
| **向量维度** | 384（all-MiniLM-L6-v2） | 384 |

## 📚 相关文件

**修改的文件：**
- ✅ [DjlEmbeddingServiceImpl.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\service\impl\DjlEmbeddingServiceImpl.java) - 添加条件注解
- ✅ [MockEmbeddingServiceImpl.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\service\impl\MockEmbeddingServiceImpl.java) - 添加条件和 @Primary 注解

**涉及的文件：**
- ✅ [application.yml](d:\workspace_tmp\agent\backend\src\main\resources\application.yml) - 配置文件
- ✅ [ChatServiceImpl.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\service\impl\ChatServiceImpl.java) - 服务注入
- ✅ [EmbeddingService.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\service\EmbeddingService.java) - 服务接口

## 🚀 启动应用

**重新编译和启动：**
```bash
cd d:\workspace_tmp\agent\backend
mvn clean compile
mvn exec:java
```

**预期效果：**
- ✅ 当 `embedding.enabled=false` 时，注入 `MockEmbeddingServiceImpl`
- ✅ 当 `embedding.enabled=true` 时，注入 `DjlEmbeddingServiceImpl`
- ✅ 未配置时，默认注入 `MockEmbeddingServiceImpl`
- ✅ 避免启动失败或资源浪费
- ✅ 配置生效

## 🎉 总结

**核心改进：**
1. ✅ 添加 `@ConditionalOnProperty` 注解，实现条件注入
2. ✅ 两个服务都添加 `@Primary` 注解，确保正确的服务被注入
3. ✅ `MockEmbeddingServiceImpl` 使用 `matchIfMissing = true`，确保默认行为
4. ✅ 配置生效，避免 DJL 模型加载失败

**技术要点：**
- Spring Boot 条件注解 `@ConditionalOnProperty`
- `@Primary` 注解的作用和优先级
- `matchIfMissing = true` 的默认行为
- 依赖注入的条件选择机制

---

**现在配置生效了！当 embedding.enabled=false 时，注入 MockEmbeddingServiceImpl，而不是 DjlEmbeddingServiceImpl！** ✅