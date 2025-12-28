# ChatGPT API 代理

用于绕过 Cloudflare Workers 被 ChatGPT 拦截的问题。

## 部署到 Vercel

1. 在 Vercel 创建新项目，导入这个文件夹
2. 设置环境变量：
   - `API_KEY`: 自定义一个密钥（防止滥用）

3. 部署完成后得到 URL，如 `https://your-project.vercel.app`

## API 接口

所有接口都是 POST 请求，需要 Header: `Authorization: Bearer <API_KEY>`

### 1. 获取 AccessToken
```
POST /api/chatgpt/token
Body: { "session_token": "eyJ..." }
Response: { "success": true, "accessToken": "eyJ..." }
```

### 2. 获取订阅信息
```
POST /api/chatgpt/subscription
Body: { "access_token": "eyJ...", "account_id": "xxx" }
Response: { "success": true, "seats_in_use": 5, "seats_entitled": 5, ... }
```

### 3. 获取成员列表
```
POST /api/chatgpt/members
Body: { "access_token": "eyJ...", "account_id": "xxx" }
Response: { "success": true, "items": [...], "total": 5 }
```

### 4. 发送邀请
```
POST /api/chatgpt/invite
Body: { "access_token": "eyJ...", "account_id": "xxx", "email": "user@example.com" }
Response: { "success": true }
```

### 5. 踢出成员
```
POST /api/chatgpt/kick
Body: { "access_token": "eyJ...", "account_id": "xxx", "user_id": "xxx" }
Response: { "success": true }
```

## 在 team-invite 中使用

部署后，修改 `team-invite/src/lib/chatgpt.ts`，把直接调用 ChatGPT 改成调用这个代理。
