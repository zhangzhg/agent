-- 用户表
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(20),
    status INTEGER DEFAULT 1,
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    deleted INTEGER DEFAULT 0
);

-- 角色表
CREATE TABLE IF NOT EXISTS role (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name VARCHAR(50) NOT NULL UNIQUE,
    role_code VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255),
    status INTEGER DEFAULT 1,
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    deleted INTEGER DEFAULT 0
);

-- 资源表
CREATE TABLE IF NOT EXISTS resource (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_name VARCHAR(50) NOT NULL,
    resource_code VARCHAR(100) NOT NULL UNIQUE,
    resource_type VARCHAR(20) NOT NULL,
    url VARCHAR(255),
    parent_id INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    icon VARCHAR(100),
    status INTEGER DEFAULT 1,
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    deleted INTEGER DEFAULT 0
);

-- 用户角色关联表
CREATE TABLE IF NOT EXISTS user_role (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(id),
    FOREIGN KEY (role_id) REFERENCES role(id),
    UNIQUE(user_id, role_id)
);

-- 角色资源关联表
CREATE TABLE IF NOT EXISTS role_resource (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES role(id),
    FOREIGN KEY (resource_id) REFERENCES resource(id),
    UNIQUE(role_id, resource_id)
);

-- 对话表
CREATE TABLE IF NOT EXISTS conversation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    deleted INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES user(id)
);

-- 消息表
CREATE TABLE IF NOT EXISTS message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversation(id)
);

-- 初始化管理员用户 (密码: 123456，使用BCrypt加密)
INSERT INTO user (username, password, email, status) 
SELECT 'admin', '$2a$10$2/VcWSVkT1VhOOMpPdA8BOQcadTlgDAOeXUprQofARZlZV3IZlluG', 'admin@example.com', 1
WHERE NOT EXISTS (SELECT 1 FROM user WHERE username = 'admin');

-- 初始化角色
INSERT INTO role (role_name, role_code, description, status) 
SELECT '管理员', 'ADMIN', '系统管理员', 1
WHERE NOT EXISTS (SELECT 1 FROM role WHERE role_code = 'ADMIN');

INSERT INTO role (role_name, role_code, description, status) 
SELECT '普通用户', 'USER', '普通用户', 1
WHERE NOT EXISTS (SELECT 1 FROM role WHERE role_code = 'USER');

-- 初始化资源
INSERT INTO resource (resource_name, resource_code, resource_type, url, parent_id, sort_order, status) 
SELECT '系统管理', 'system', 'MENU', '/system', 0, 1, 1
WHERE NOT EXISTS (SELECT 1 FROM resource WHERE resource_code = 'system');

INSERT INTO resource (resource_name, resource_code, resource_type, url, parent_id, sort_order, status) 
SELECT '用户管理', 'user:manage', 'MENU', '/system/user', 1, 1, 1
WHERE NOT EXISTS (SELECT 1 FROM resource WHERE resource_code = 'user:manage');

INSERT INTO resource (resource_name, resource_code, resource_type, url, parent_id, sort_order, status) 
SELECT '角色管理', 'role:manage', 'MENU', '/system/role', 1, 2, 1
WHERE NOT EXISTS (SELECT 1 FROM resource WHERE resource_code = 'role:manage');

INSERT INTO resource (resource_name, resource_code, resource_type, url, parent_id, sort_order, status) 
SELECT '资源管理', 'resource:manage', 'MENU', '/system/resource', 1, 3, 1
WHERE NOT EXISTS (SELECT 1 FROM resource WHERE resource_code = 'resource:manage');