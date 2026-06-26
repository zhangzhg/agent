# DJL Sentence-Transformers 模型使用指南

## 📖 简介

本项目使用 DJL (Deep Java Library) 加载 sentence-transformers 模型，实现本地文本向量化。无需 Python 环境，直接在 Java 中运行嵌入模型。

## 🔧 环境准备

### 1. 安装 DJL 模型转换工具

DJL 需要先使用 Python 工具将 HuggingFace 模型转换为 TorchScript 格式。这个工具只在开发机使用一次，生产环境完全不需要 Python。

```bash
# 安装 DJL 转换工具
pip install djl-converter

# 或者从 GitHub 安装最新版本
pip install "git+https://github.com/deepjavalibrary/djl.git#subdirectory=extensions/tokenizers/src/main/python"
```

### 2. 转换模型

使用 `djl-convert` 命令将 HuggingFace 模型转换为 DJL 格式：

```bash
# 转换 sentence-transformers/all-MiniLM-L6-v2 模型
djl-convert -m sentence-transformers/all-MiniLM-L6-v2

# 转换其他模型
djl-convert -m sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
djl-convert -m BAAI/bge-small-zh-v1.5  # 中文模型
```

转换后的模型会保存在 `model/sentence-transformers/all-MiniLM-L6-v2/` 目录中。

### 3. 移动模型文件

将转换后的模型移动到项目的 `models/sentence-transformers` 目录：

```bash
# Windows
move model\sentence-transformers\all-MiniLM-L6-v2 models\sentence-transformers

# Linux/macOS
mv model/sentence-transformers/all-MiniLM-L6-v2 models/sentence-transformers
```

## ⚙️ 配置说明

### application.yml 配置

```yaml
# Embedding 配置（DJL sentence-transformers）
embedding:
  enabled: true  # 启用 DJL embedding
  model-path: models/sentence-transformers  # 本地模型路径
  model-name: sentence-transformers/all-MiniLM-L6-v2  # HuggingFace 模型名称
  dimension: 384  # 向量维度
```

### 配置参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `enabled` | 是否启用 DJL embedding | `false` |
| `model-path` | 本地模型路径 | `models/sentence-transformers` |
| `model-name` | HuggingFace 模型名称 | `sentence-transformers/all-MiniLM-L6-v2` |
| `dimension` | 向量维度 | `384` |

## 🚀 使用方式

### 1. 启动项目

```bash
cd backend
mvn clean install
mvn spring-boot:run
```

### 2. 测试向量检索功能

- 登录系统（用户名：admin，密码：123456）
- 创建新对话并发送消息
- 发送相似的问题，系统会自动检索历史对话并作为上下文
- AI 回复中会显示检索到的历史对话数量

### 3. 验证 DJL 是否启用

查看启动日志：

```
INFO: Loading embedding model from: models/sentence-transformers
INFO: Embedding model loaded successfully
INFO: DJL Embedding Service initialized successfully with dimension: 384
```

如果看到这些日志，说明 DJL embedding 已成功启用。

## 📊 推荐模型

### 英文模型

| 模型名称 | 维度 | 特点 | 适用场景 |
|---------|------|------|---------|
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | 轻量级，速度快 | 通用英文场景 |
| `sentence-transformers/all-mpnet-base-v2` | 768 | 高质量，较慢 | 高精度英文场景 |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 384 | 多语言支持 | 多语言场景 |

### 中文模型

| 模型名称 | 维度 | 特点 | 适用场景 |
|---------|------|------|---------|
| `BAAI/bge-small-zh-v1.5` | 512 | 中文优化，轻量级 | 中文场景 |
| `BAAI/bge-base-zh-v1.5` | 768 | 中文优化，高质量 | 高精度中文场景 |
| `moka-ai/m3e-base` | 768 | 中文优化，多语言 | 中文多语言场景 |

## 🔍 性能优化

### 1. 模型选择

- **轻量级模型**（384 维）：适合快速响应，内存占用小
- **高质量模型**（768 维）：适合高精度场景，内存占用较大

### 2. GPU 加速

如果需要 GPU 加速，修改 `pom.xml`：

```xml
<!-- 替换 CPU 版本为 GPU 版本 -->
<dependency>
    <groupId>ai.djl.pytorch</groupId>
    <artifactId>pytorch-native-cu121</artifactId>
    <version>2.2.2-0.28.0</version>
    <scope>runtime</scope>
</dependency>
```

### 3. 批量处理

对于大量文本，使用批量嵌入提高效率：

```java
List<String> texts = Arrays.asList("文本1", "文本2", "文本3");
List<float[]> embeddings = embeddingService.embedBatch(texts);
```

## 🛠️ 常见问题

### 1. 模型加载失败

**错误信息**：`Model path does not exist`

**解决方案**：
- 检查 `embedding.model-path` 配置是否正确
- 确保已使用 `djl-convert` 转换模型
- 检查模型文件是否存在于指定路径

### 2. 内存不足

**错误信息**：`OutOfMemoryError`

**解决方案**：
- 使用更小的模型（如 `all-MiniLM-L6-v2`）
- 减少 batch size
- 增加 JVM 内存：`-Xmx2g`

### 3. Python 环境问题

**错误信息**：`djl-convert: command not found`

**解决方案**：
- 确保已安装 Python 和 pip
- 使用 `pip install djl-converter` 安装工具
- 或从 GitHub 安装最新版本

## 📚 参考资源

- [DJL 官方文档](https://docs.djl.ai/)
- [DJL HuggingFace Tokenizers](https://docs.djl.ai/master/extensions/tokenizers/index.html)
- [Sentence-Transformers 模型列表](https://www.sbert.net/docs/pretrained_models.html)
- [DJL 模型转换教程](https://blog.csdn.net/this_xiaohuar/article/details/140488759)

## 🎯 下一步

1. **启用 DJL embedding**：修改 `application.yml` 中的 `embedding.enabled: true`
2. **转换模型**：运行 `djl-convert -m sentence-transformers/all-MiniLM-L6-v2`
3. **启动项目**：运行 `mvn spring-boot:run`
4. **测试功能**：登录系统并发送对话，验证向量检索功能

---

**注意**：如果未启用 DJL embedding 或模型未转换，系统会自动使用 Mock Embedding Service（生成伪向量）作为备用方案。