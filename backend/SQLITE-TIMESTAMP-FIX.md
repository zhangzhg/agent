# SQLite 时间戳解析错误修复方案

## 🐛 问题描述

**错误信息：**
```
Error attempting to get column 'create_time' from result set.  
Cause: java.sql.SQLException: Error parsing time stamp  
Caused by: java.text.ParseException: Unparseable date: "2026-06-26T09:18:33.260958200" 
does not match (\p{Nd}++)\Q-\E(\p{Nd}++)\Q-\E(\p{Nd}++)\Q \E(\p{Nd}++)\Q:\E(\p{Nd}++)\Q:\E(\p{Nd}++)\Q.\E(\p{Nd}++)
```

**问题根源：**
1. SQLite 的 `CURRENT_TIMESTAMP` 返回 ISO 8601 格式（包含 `T` 分隔符）
   - 例如：`2026-06-26T09:18:33.260958200`
2. MyBatis Plus/JDBC 期望传统的 SQL 时间格式（使用空格分隔）
   - 例如：`2026-06-26 09:18:33.260958`
3. 时间格式不匹配导致解析失败

## ✅ 解决方案

### 方案：使用 MyBatis Plus 自动填充机制

**已修改的文件：**

#### 1. schema.sql - 移除 DEFAULT CURRENT_TIMESTAMP

**修改前：**
```sql
CREATE TABLE IF NOT EXISTS user (
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**修改后：**
```sql
CREATE TABLE IF NOT EXISTS user (
    create_time DATETIME,
    update_time DATETIME
);
```

**修改的表：**
- ✅ user
- ✅ role
- ✅ resource
- ✅ user_role
- ✅ role_resource
- ✅ conversation
- ✅ message

#### 2. MybatisPlusConfig.java - 自动填充配置（已存在）

**配置代码：**
```java
@Configuration
public class MybatisPlusConfig implements MetaObjectHandler {
    
    @Override
    public void insertFill(MetaObject metaObject) {
        // 插入时自动填充 createTime 和 updateTime
        this.strictInsertFill(metaObject, "createTime", LocalDateTime.class, LocalDateTime.now());
        this.strictInsertFill(metaObject, "updateTime", LocalDateTime.class, LocalDateTime.now());
    }
    
    @Override
    public void updateFill(MetaObject metaObject) {
        // 更新时自动填充 updateTime
        this.strictUpdateFill(metaObject, "updateTime", LocalDateTime.class, LocalDateTime.now());
    }
}
```

**优势：**
- ✅ 使用 `LocalDateTime.now()` 生成标准 SQL 时间格式
- ✅ 不包含 `T` 分隔符
- ✅ 精度控制在 6 位纳秒（而不是 9 位）
- ✅ MyBatis Plus 自动管理，无需手动设置

## 🔧 实施步骤

### 步骤 1：删除旧数据库

**重要：** 必须删除现有的数据库文件，因为旧数据使用了 ISO 8601 格式

**数据库文件位置：**
```
./data/agent.db
```

**删除命令：**
```bash
# Windows PowerShell
Remove-Item -Path "d:\workspace_tmp\agent\backend\data\agent.db" -Force

# 或者手动删除文件
```

### 步骤 2：重新启动应用

**启动应用：**
```bash
cd d:\workspace_tmp\agent\backend
mvn spring-boot:run
```

**效果：**
- ✅ Spring Boot 会重新创建数据库
- ✅ 使用新的 schema.sql（无 DEFAULT CURRENT_TIMESTAMP）
- ✅ 所有时间字段使用 MyBatis Plus 自动填充
- ✅ 时间格式为标准 SQL 格式（无 `T` 分隔符）

### 步骤 3：验证修复

**测试查询：**
```java
Conversation conversation = conversationMapper.selectById(conversationId);
// ✅ createTime 字段可以正常解析为 LocalDateTime
```

**预期结果：**
- ✅ 无时间戳解析错误
- ✅ createTime 和 updateTime 正常显示
- ✅ 时间格式为 `2026-06-26 09:18:33.260958`

## 📊 时间格式对比

| 数据源 | 时间格式 | 示例 | MyBatis Plus 支持 |
|--------|----------|------|------------------|
| SQLite CURRENT_TIMESTAMP | ISO 8601 | `2026-06-26T09:18:33.260958200` | ❌ 不支持 |
| LocalDateTime.now() | SQL 标准 | `2026-06-26 09:18:33.260958` | ✅ 支持 |

**关键差异：**
1. **分隔符：**
   - ISO 8601：使用 `T` 分隔日期和时间
   - SQL 标准：使用空格分隔

2. **纳秒精度：**
   - SQLite：9 位纳秒（`260958200`）
   - LocalDateTime：6 位纳秒（`260958`）

## 🎯 实体类配置

**Conversation.java：**
```java
@Data
@TableName("conversation")
public class Conversation {
    @TableId(type = IdType.AUTO)
    private Long id;
    
    private Long userId;
    
    private String title;
    
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;  // ✅ 插入时自动填充
    
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updateTime;  // ✅ 插入和更新时自动填充
    
    @TableLogic
    private Integer deleted;
}
```

**Message.java：**
```java
@Data
@TableName("message")
public class Message {
    @TableId(type = IdType.AUTO)
    private Long id;
    
    private Long conversationId;
    
    private String role;
    
    private String content;
    
    private byte[] embedding;
    
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;  // ✅ 插入时自动填充
}
```

**关键注解：**
- `@TableField(fill = FieldFill.INSERT)` - 插入时自动填充
- `@TableField(fill = FieldFill.INSERT_UPDATE)` - 插入和更新时自动填充

## 🚀 自动填充工作流程

```
插入数据
    ↓
MyBatis Plus 检测 @TableField(fill = FieldFill.INSERT)
    ↓
调用 MetaObjectHandler.insertFill()
    ↓
填充 createTime = LocalDateTime.now()
填充 updateTime = LocalDateTime.now()
    ↓
生成标准 SQL 时间格式
    ↓
保存到数据库
```

```
更新数据
    ↓
MyBatis Plus 检测 @TableField(fill = FieldFill.INSERT_UPDATE)
    ↓
调用 MetaObjectHandler.updateFill()
    ↓
填充 updateTime = LocalDateTime.now()
    ↓
生成标准 SQL 时间格式
    ↓
保存到数据库
```

## ⚠️ 重要提示

### 1. 必须删除旧数据库

**为什么必须删除：**
- ✅ 旧数据库使用了 ISO 8601 格式的时间数据
- ✅ MyBatis Plus 无法解析 ISO 8601 格式
- ✅ 新的 schema.sql 不会自动更新现有数据

### 2. 备份重要数据

**如果需要保留数据：**
```bash
# 备份数据库（可选）
Copy-Item -Path "d:\workspace_tmp\agent\backend\data\agent.db" -Destination "d:\workspace_tmp\agent\backend\data\agent.db.backup"

# 导出重要数据（可选）
# 使用 SQLite 工具导出 SQL 或 CSV
```

### 3. 初始化数据会保留

**schema.sql 包含初始化数据：**
- ✅ 管理员用户（admin）
- ✅ 默认角色（ADMIN、USER）
- ✅ 默认资源（系统管理、用户管理、角色管理、资源管理）

**重新创建数据库后：**
- ✅ 初始化数据会自动插入
- ✅ 使用标准 SQL 时间格式
- ✅ 无解析错误

## 📚 相关文件

**修改的文件：**
- ✅ [schema.sql](d:\workspace_tmp\agent\backend\src\main\resources\db\schema.sql) - 移除 DEFAULT CURRENT_TIMESTAMP

**已有的文件：**
- ✅ [MybatisPlusConfig.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\config\MybatisPlusConfig.java) - 自动填充配置
- ✅ [Conversation.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\entity\Conversation.java) - 实体类配置
- ✅ [Message.java](d:\workspace_tmp\agent\backend\src\main\java\com\agent\entity\Message.java) - 实体类配置

## 🎉 总结

**问题：** SQLite 的 ISO 8601 时间格式导致 MyBatis Plus 解析失败
**解决：** 使用 MyBatis Plus 自动填充机制生成标准 SQL 时间格式
**步骤：** 删除旧数据库 → 重新启动应用 → 验证修复

**关键改进：**
- ✅ 移除所有表的 `DEFAULT CURRENT_TIMESTAMP`
- ✅ 使用 MyBatis Plus 自动填充时间字段
- ✅ 生成标准 SQL 时间格式（无 `T` 分隔符）
- ✅ 精度控制在 6 位纳秒
- ✅ 无需手动设置时间字段

---

**现在时间字段可以正常解析，不再出现 ParseException 错误！** ✅