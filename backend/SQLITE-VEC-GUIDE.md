# SQLite Vec 扩展使用指南

## 📖 简介

SQLite Vec 是一个 SQLite 扩展，提供向量搜索功能。本文档介绍如何在 Java 项目中集成 sqlite-vec 扩展。

## ⚠️ 重要说明

**SQLite JDBC 支持加载扩展，但需要特殊配置：**

1. ✅ SQLite JDBC 支持加载扩展（通过 `load_extension` SQL 函数）
2. ✅ 需要在连接 URL 中添加 `?enable_load_extension=true` 参数
3. ⚠️ sqlite-vec 需要手动编译为共享库（.so/.dll/.dylib）
4. ⚠️ 扩展加载默认是禁用的（出于安全考虑）

## 🔧 编译 sqlite-vec 扩展

### 1. 克隆仓库

```bash
git clone https://github.com/asg017/sqlite-vec.git
cd sqlite-vec
```

### 2. 编译扩展

**Linux:**
```bash
./scripts/vendor.sh
make loadable
# 生成：dist/vec0.so
```

**Windows (MinGW):**
```bash
gcc -g -shared sqlite-vec.c -o vec0.dll
```

**Windows (MSVC):**
```bash
cl sqlite-vec.c -link -dll -out:sqlite-vec.dll
```

**macOS:**
```bash
gcc -g -fPIC -dynamiclib sqlite-vec.c -o vec0.dylib
```

### 3. 复制扩展文件

将编译好的扩展文件复制到项目目录：

```bash
# Windows
copy vec0.dll d:\workspace_tmp\agent\backend\extensions\

# Linux/macOS
cp vec0.so /path/to/project/extensions/
```

## ⚙️ 配置说明

### application.yml 配置

```yaml
# SQLite Vec 扩展配置
sqlite:
  vec:
    enabled: true  # 启用 sqlite-vec 扩展
    path: "extensions/vec0.dll"  # 扩展文件路径（Windows）
    # path: "extensions/vec0.so"  # Linux
    # path: "extensions/vec0.dylib"  # macOS
```

### 数据源配置

确保数据源 URL 包含 `enable_load_extension=true` 参数：

```yaml
spring:
  datasource:
    url: jdbc:sqlite:./data/agent.db?enable_load_extension=true
```

## 🚀 使用方式

### 1. 自动加载（推荐）

系统启动时会自动加载 sqlite-vec 扩展：

```java
@Configuration
public class SQLiteVecConfig {
    @PostConstruct
    public void init() {
        // 自动加载扩展
        loadVecExtension();
    }
}
```

### 2. 手动加载

如果需要手动加载扩展：

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;

public class ManualLoad {
    public static void main(String[] args) throws Exception {
        // 连接数据库（启用扩展加载）
        String url = "jdbc:sqlite:./data/agent.db?enable_load_extension=true";
        Connection conn = DriverManager.getConnection(url);
        
        try (Statement stmt = conn.createStatement()) {
            // 加载扩展
            stmt.execute("SELECT load_extension('extensions/vec0.dll')");
            
            // 验证加载成功
            var rs = stmt.executeQuery("SELECT vec_version()");
            if (rs.next()) {
                System.out.println("SQLite Vec version: " + rs.getString(1));
            }
        }
    }
}
```

## 📊 向量表创建

### 使用 sqlite-vec 创建向量表

```sql
-- 创建虚拟向量表
CREATE VIRTUAL TABLE vec_items USING vec0(
    embedding FLOAT[384]  -- 384 维向量
);

-- 插入向量数据
INSERT INTO vec_items(rowid, embedding)
VALUES (1, '[0.1, 0.2, 0.3, ...]');

-- 向量搜索（L2 距离）
SELECT rowid, distance
FROM vec_items
WHERE vec_search(embedding, '[0.1, 0.2, 0.3, ...]')
ORDER BY distance
LIMIT 10;
```

### 使用普通表（默认方案）

如果 sqlite-vec 不可用，系统使用普通表存储向量：

```sql
-- message 表中的 embedding 字段（BLOB 类型）
CREATE TABLE message (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER,
    role VARCHAR(20),
    content TEXT,
    embedding BLOB,  -- 存储向量数据
    create_time DATETIME
);
```

## 🔍 功能对比

| 功能 | sqlite-vec 扩展 | 默认实现 |
|------|----------------|---------|
| 向量存储 | 虚拟表（优化） | 普通 BLOB 字段 |
| 向量搜索 | SQL 函数（快速） | Java 计算（较慢） |
| 索引支持 | ✅ 自动索引 | ❌ 无索引 |
| 编译要求 | ✅ 需要编译 | ❌ 无需编译 |
| 配置复杂度 | ⚠️ 较复杂 | ✅ 简单 |
| 性能 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |

## 🛠️ 常见问题

### 1. 扩展加载失败

**错误信息**：`load_extension is disabled`

**解决方案**：
- 在连接 URL 中添加 `?enable_load_extension=true`
- 确保扩展文件路径正确
- 检查扩展文件权限（Linux/macOS）

### 2. 找不到扩展文件

**错误信息**：`extension file not found`

**解决方案**：
- 检查 `sqlite.vec.path` 配置是否正确
- 确保扩展文件存在
- Windows 路径使用双反斜杠：`C:\\path\\to\\vec0.dll`

### 3. 编译失败

**错误信息**：`undefined reference to sqlite3_extension_init`

**解决方案**：
- 运行 `./scripts/vendor.sh` 下载 SQLite amalgamation
- 确保 SQLite 开发依赖已安装
- 检查编译器版本和参数

## 📚 参考资源

- [SQLite Vec GitHub](https://github.com/asg017/sqlite-vec)
- [SQLite Vec 文档](https://alexgarcia.xyz/sqlite-vec/)
- [SQLite 扩展加载](https://www.sqlite.org/loadext.html)
- [SQLite JDBC 文档](https://github.com/xerial/sqlite-jdbc)

## 🎯 推荐方案

**对于生产环境：**
- ✅ 使用 sqlite-vec 扩展（性能更好）
- ✅ 编译扩展并配置路径
- ✅ 启用 `sqlite.vec.enabled: true`

**对于开发/测试：**
- ✅ 使用默认实现（无需编译）
- ✅ 保持 `sqlite.vec.enabled: false`
- ✅ 使用 message 表的 embedding 字段

---

**注意**：如果 sqlite-vec 扩展不可用或加载失败，系统会自动使用默认的向量检索实现（基于 message 表的 embedding 字段）。这保证了系统的可用性和稳定性。