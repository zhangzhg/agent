# DJL PyTorch 正确配置说明

## ⚠️ 重要变更

**`pytorch-native-auto` 已被废弃！**

自 DJL 0.14.0 开始，`pytorch-native-auto` 不再发布新版本。正确的配置方式是使用 **DJL BOM**。

## 📦 正确的 Maven 配置

### 1. 使用 DJL BOM 管理版本

```xml
<properties>
    <djl.version>0.28.0</djl.version>
</properties>

<dependencyManagement>
    <dependencies>
        <!-- DJL BOM - 自动管理所有 DJL 包版本 -->
        <dependency>
            <groupId>ai.djl</groupId>
            <artifactId>bom</artifactId>
            <version>${djl.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

### 2. 添加依赖（无需指定版本）

```xml
<!-- DJL PyTorch Engine -->
<dependency>
    <groupId>ai.djl.pytorch</groupId>
    <artifactId>pytorch-engine</artifactId>
    <scope>runtime</scope>
</dependency>

<!-- DJL HuggingFace Tokenizers -->
<dependency>
    <groupId>ai.djl.huggingface</groupId>
    <artifactId>tokenizers</artifactId>
</dependency>
```

## 🔍 DJL 版本对应关系

根据 DJL 官方文档，版本对应关系如下：

| DJL 版本 | 支持的 PyTorch 版本 |
|---------|-------------------|
| 0.28.0 | 1.13.1, 2.1.2, **2.2.2** |
| 0.29.0 | 1.13.1, 2.1.2, 2.2.2, **2.3.1** |
| 0.30.0 | 1.13.1, 2.1.2, 2.3.1, **2.4.0** |
| 0.31.0 | 1.13.1, 2.1.2, 2.3.1, 2.4.0, **2.5.1** |
| 0.36.0 | 1.13.1, 2.5.1, **2.7.1** |

**注意：** DJL 0.28.0 默认使用 PyTorch 2.2.2（加粗版本）

## 🚀 PyTorch Native 库自动下载

**DJL 会自动下载 PyTorch native 库！**

### 自动下载机制

1. **首次运行时自动下载**
   - DJL 会检测你的操作系统和架构
   - 自动下载对应的 PyTorch native 库
   - 缓存到 `~/.djl.ai/cache` 目录

2. **支持的平台**
   - Windows: `win-x86_64`
   - Linux: `linux-x86_64`
   - macOS: `osx-x86_64`, `osx-aarch64` (M1)
   - GPU 支持: `linux-x86_64` with CUDA

3. **缓存位置**
   ```
   ~/.djl.ai/cache/
   ├── pytorch/
   │   ├── 2.2.2/
   │   │   ├── cpu/
   │   │   │   └── linux-x86_64/
   │   │   │       └── libtorch.so
   ```

## ⚙️ 手动指定 PyTorch 版本（可选）

如果需要使用特定版本的 PyTorch：

### 方法1: 设置环境变量

```bash
export PYTORCH_VERSION=2.1.2
```

### 方法2: 设置系统属性

```java
System.setProperty("PYTORCH_VERSION", "2.1.2");
```

### 方法3: 添加特定平台的 native 库（离线环境）

```xml
<!-- Windows CPU -->
<dependency>
    <groupId>ai.djl.pytorch</groupId>
    <artifactId>pytorch-native-cpu</artifactId>
    <classifier>win-x86_64</classifier>
    <scope>runtime</scope>
</dependency>

<!-- Linux CPU -->
<dependency>
    <groupId>ai.djl.pytorch</groupId>
    <artifactId>pytorch-native-cpu</artifactId>
    <classifier>linux-x86_64</classifier>
    <scope>runtime</scope>
</dependency>

<!-- Linux GPU (CUDA 11.8) -->
<dependency>
    <groupId>ai.djl.pytorch</groupId>
    <artifactId>pytorch-native-cu118</artifactId>
    <classifier>linux-x86_64</classifier>
    <scope>runtime</scope>
</dependency>
```

## 📊 为什么废弃 pytorch-native-auto？

### 废弃原因

1. **版本管理混乱**
   - `pytorch-native-auto` 的版本号与 PyTorch 版本不一致
   - 例如: `pytorch-native-auto:1.9.1` 对应 PyTorch 1.9.1
   - 但 `pytorch-native-auto:2.2.2` 从未发布

2. **维护成本高**
   - 每个新 PyTorch 版本都需要发布新的 `pytorch-native-auto`
   - 容易出现版本不匹配问题

3. **更好的替代方案**
   - DJL BOM 自动管理版本
   - 自动下载机制更灵活
   - 支持多版本 PyTorch

### 新方案优势

| 特性 | pytorch-native-auto (旧) | DJL BOM + 自动下载 (新) |
|------|-------------------------|----------------------|
| 版本管理 | ❌ 手动指定 | ✅ 自动管理 |
| 平台检测 | ✅ 自动 | ✅ 自动 |
| 多版本支持 | ❌ 单一版本 | ✅ 多版本可选 |
| 离线支持 | ✅ 需手动配置 | ✅ 可添加特定包 |
| 维护性 | ❌ 已废弃 | ✅ 持续更新 |

## 🛠️ 常见问题

### 1. 依赖下载失败

**错误信息**: `Missing artifact ai.djl.pytorch:pytorch-native-auto:jar:2.2.2`

**解决方案**: 
- ✅ 使用 DJL BOM（已修复）
- ✅ 移除 `pytorch-native-auto` 依赖
- ✅ 让 DJL 自动下载 native 库

### 2. 首次运行慢

**原因**: DJL 正在下载 PyTorch native 库（约 200MB）

**解决方案**:
- ✅ 等待下载完成（首次运行）
- ✅ 后续运行会使用缓存
- ✅ 或提前手动下载到缓存目录

### 3. 离线环境部署

**解决方案**:
```xml
<!-- 添加特定平台的 native 库 -->
<dependency>
    <groupId>ai.djl.pytorch</groupId>
    <artifactId>pytorch-native-cpu</artifactId>
    <classifier>win-x86_64</classifier>
    <version>2.2.2-0.28.0</version>
    <scope>runtime</scope>
</dependency>

<!-- 添加 PyTorch JNI -->
<dependency>
    <groupId>ai.djl.pytorch</groupId>
    <artifactId>pytorch-jni</artifactId>
    <version>2.2.2-0.28.0</version>
    <scope>runtime</scope>
</dependency>
```

## 📚 参考文档

- [DJL PyTorch Engine 官方文档](http://djl.ai/engines/pytorch/pytorch-engine/)
- [DJL BOM 使用说明](http://djl.ai/bom/)
- [DJL 依赖管理](https://djl.ai/docs/development/dependency_management.html)
- [DJL 缓存管理](http://djl.ai/docs/development/cache_management.html)

## ✅ 推荐配置

**开发环境（推荐）**:
```xml
<!-- 使用 BOM + 自动下载 -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>ai.djl</groupId>
            <artifactId>bom</artifactId>
            <version>0.28.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>ai.djl.pytorch</groupId>
        <artifactId>pytorch-engine</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

**生产环境（离线）**:
```xml
<!-- 使用特定平台的 native 库 -->
<dependency>
    <groupId>ai.djl.pytorch</groupId>
    <artifactId>pytorch-native-cpu</artifactId>
    <classifier>win-x86_64</classifier>
    <version>2.2.2-0.28.0</version>
    <scope>runtime</scope>
</dependency>
```

---

**总结**: 使用 DJL BOM 是最简单、最可靠的配置方式。DJL 会自动处理 PyTorch native 库的下载和平台适配，无需手动配置。