"""
ChatGPT API 代理 - Vercel Serverless Function
用于绕过 Cloudflare Workers 被拦截的问题
"""

from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.error
import os

# 从环境变量读取 API Key
API_KEY = os.environ.get('API_KEY', '')

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 验证 API Key
        auth = self.headers.get('Authorization', '')
        if auth != f'Bearer {API_KEY}':
            self._send_json(401, {'error': 'Unauthorized'})
            return

        # 读取请求体
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}

        path = self.path

        try:
            if path == '/api/chatgpt/token':
                # 用 session-token 换 accessToken
                result = self._get_access_token(body.get('session_token', ''))
            elif path == '/api/chatgpt/subscription':
                # 获取订阅信息
                result = self._get_subscription(body.get('access_token', ''), body.get('account_id', ''))
            elif path == '/api/chatgpt/members':
                # 获取成员列表
                result = self._get_members(body.get('access_token', ''), body.get('account_id', ''))
            elif path == '/api/chatgpt/invite':
                # 发送邀请
                result = self._send_invite(body.get('access_token', ''), body.get('account_id', ''), body.get('email', ''))
            elif path == '/api/chatgpt/kick':
                # 踢出成员
                result = self._kick_member(body.get('access_token', ''), body.get('account_id', ''), body.get('user_id', ''))
            elif path == '/api/chatgpt/cancel-invite':
                # 取消邀请
                result = self._cancel_invite(body.get('access_token', ''), body.get('account_id', ''), body.get('email', ''))
            elif path == '/api/chatgpt/sync':
                # 一次性获取所有信息（token + subscription + members）
                result = self._sync_all(body.get('session_token', ''), body.get('account_id', ''))
            else:
                result = {'error': 'Not found'}
                self._send_json(404, result)
                return

            self._send_json(200, result)
        except Exception as e:
            self._send_json(500, {'error': str(e)})

    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def _parse_openai_error(self, error_str):
        """解析 OpenAI 错误并映射成友好消息"""
        # 错误码映射表
        error_map = {
            'token_invalidated': ('token_expired', 'Token已过期，请更新Session Token'),
            'invalid_api_key': ('token_expired', 'Token无效，请更新Session Token'),
            'account_deactivated': ('banned', '账号已被封禁'),
            'account_suspended': ('banned', '账号已被暂停'),
            'subscription_expired': ('expired', '订阅已过期'),
            'rate_limit_exceeded': ('rate_limit', '请求过于频繁，请稍后重试'),
            'server_error': ('server_error', 'OpenAI服务器错误，请稍后重试'),
        }
        
        try:
            # 尝试解析 JSON 错误
            if isinstance(error_str, str) and error_str.strip().startswith('{'):
                error_data = json.loads(error_str)
                if 'error' in error_data:
                    code = error_data['error'].get('code', '')
                    message = error_data['error'].get('message', '')
                    
                    # 查找映射
                    if code in error_map:
                        return error_map[code]
                    
                    # 根据消息内容判断
                    msg_lower = message.lower()
                    if 'token' in msg_lower and ('invalid' in msg_lower or 'expired' in msg_lower):
                        return ('token_expired', 'Token已过期，请更新Session Token')
                    if 'banned' in msg_lower or 'suspended' in msg_lower or 'deactivated' in msg_lower:
                        return ('banned', '账号已被封禁')
                    
                    # 返回原始消息
                    return ('error', message)
        except:
            pass
        
        # 无法解析，返回原始错误
        return ('error', str(error_str)[:200] if error_str else '未知错误')

    def _fetch(self, url, headers, method='GET', data=None):
        """发起 HTTP 请求"""
        req = urllib.request.Request(url, headers=headers, method=method)
        if data:
            req.data = json.dumps(data).encode()
        
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return {'status': res.status, 'data': json.loads(res.read())}
        except urllib.error.HTTPError as e:
            return {'status': e.code, 'error': e.read().decode()[:500]}
        except Exception as e:
            return {'status': 0, 'error': str(e)}

    def _get_access_token(self, session_token):
        """用 session-token 换取 accessToken（带重试）"""
        if not session_token:
            return {'success': False, 'error': 'Missing session_token'}

        headers = {
            'Accept': '*/*',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Cookie': f'__Secure-next-auth.session-token={session_token}'
        }

        # 重试3次
        last_error = None
        for attempt in range(3):
            result = self._fetch('https://chatgpt.com/api/auth/session', headers)
            
            if result.get('status') == 200 and result.get('data', {}).get('accessToken'):
                return {'success': True, 'accessToken': result['data']['accessToken']}
            
            last_error = result.get('error', 'Failed')
            # 等待后重试
            if attempt < 2:
                import time
                time.sleep(0.5)
        
        return {'success': False, 'error': last_error, 'status': result.get('status')}

    def _build_headers(self, access_token, account_id):
        return {
            'Accept': '*/*',
            'Authorization': f'Bearer {access_token}',
            'Chatgpt-Account-Id': account_id,
            'Content-Type': 'application/json',
            'Origin': 'https://chatgpt.com',
            'Referer': 'https://chatgpt.com/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }

    def _get_subscription(self, access_token, account_id):
        """获取订阅信息"""
        if not access_token or not account_id:
            return {'success': False, 'error': 'Missing params'}

        url = f'https://chatgpt.com/backend-api/subscriptions?account_id={account_id}'
        result = self._fetch(url, self._build_headers(access_token, account_id))

        if result.get('status') == 200:
            data = result['data']
            return {
                'success': True,
                'seats_in_use': data.get('seats_in_use'),
                'seats_entitled': data.get('seats_entitled'),
                'plan_type': data.get('plan_type'),
                'active_until': data.get('active_until'),
            }
        elif result.get('status') in [401, 403]:
            return {'success': False, 'banned': True, 'status': result.get('status')}
        
        return {'success': False, 'error': result.get('error'), 'status': result.get('status')}

    def _get_members(self, access_token, account_id):
        """获取成员列表"""
        if not access_token or not account_id:
            return {'success': False, 'error': 'Missing params'}

        url = f'https://chatgpt.com/backend-api/accounts/{account_id}/users?offset=0&limit=100&query='
        result = self._fetch(url, self._build_headers(access_token, account_id))

        if result.get('status') == 200:
            return {'success': True, 'items': result['data'].get('items', []), 'total': result['data'].get('total', 0)}
        
        return {'success': False, 'error': result.get('error'), 'status': result.get('status')}

    def _send_invite(self, access_token, account_id, email):
        """发送邀请"""
        if not access_token or not account_id or not email:
            return {'success': False, 'error': 'Missing params'}

        url = f'https://chatgpt.com/backend-api/accounts/{account_id}/invites'
        data = {'email_addresses': [email], 'role': 'standard-user', 'resend_emails': True}
        result = self._fetch(url, self._build_headers(access_token, account_id), 'POST', data)

        return {'success': result.get('status') == 200, 'status': result.get('status'), 'error': result.get('error')}

    def _kick_member(self, access_token, account_id, user_id):
        """踢出成员"""
        if not access_token or not account_id or not user_id:
            return {'success': False, 'error': 'Missing params'}

        url = f'https://chatgpt.com/backend-api/accounts/{account_id}/users/{user_id}'
        result = self._fetch(url, self._build_headers(access_token, account_id), 'DELETE')

        return {'success': result.get('status') == 200, 'status': result.get('status')}

    def _get_invites(self, access_token, account_id):
        """获取待处理邀请列表"""
        if not access_token or not account_id:
            return {'success': False, 'error': 'Missing params'}

        url = f'https://chatgpt.com/backend-api/accounts/{account_id}/invites?offset=0&limit=100'
        result = self._fetch(url, self._build_headers(access_token, account_id))

        if result.get('status') == 200:
            return {'success': True, 'items': result['data'].get('items', []), 'total': result['data'].get('total', 0)}
        
        return {'success': False, 'error': result.get('error'), 'status': result.get('status')}

    def _cancel_invite(self, access_token, account_id, email):
        """取消待处理邀请"""
        if not access_token or not account_id or not email:
            return {'success': False, 'error': 'Missing params'}

        url = f'https://chatgpt.com/backend-api/accounts/{account_id}/invites'
        data = {'email_address': email}
        result = self._fetch(url, self._build_headers(access_token, account_id), 'DELETE', data)

        return {'success': result.get('status') == 200, 'status': result.get('status'), 'error': result.get('error')}

    def _sync_all(self, session_token, account_id):
        """一次性获取所有信息：token + subscription + members"""
        if not session_token or not account_id:
            return {'success': False, 'error': 'Missing params'}

        # 1. 获取 accessToken
        token_result = self._get_access_token(session_token)
        if not token_result.get('success'):
            return {'success': False, 'error': token_result.get('error', 'Failed to get accessToken'), 'banned': True}

        access_token = token_result['accessToken']
        headers = self._build_headers(access_token, account_id)

        # 2. 并行获取 subscription、members 和 invites
        import concurrent.futures
        
        def fetch_subscription():
            url = f'https://chatgpt.com/backend-api/subscriptions?account_id={account_id}'
            return self._fetch(url, headers)
        
        def fetch_members():
            url = f'https://chatgpt.com/backend-api/accounts/{account_id}/users?offset=0&limit=100&query='
            return self._fetch(url, headers)

        def fetch_invites():
            url = f'https://chatgpt.com/backend-api/accounts/{account_id}/invites?offset=0&limit=100'
            return self._fetch(url, headers)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            sub_future = executor.submit(fetch_subscription)
            mem_future = executor.submit(fetch_members)
            inv_future = executor.submit(fetch_invites)
            
            sub_result = sub_future.result()
            mem_result = mem_future.result()
            inv_result = inv_future.result()

        # 3. 处理结果
        response = {'success': True}

        # 订阅信息
        if sub_result.get('status') == 200:
            data = sub_result['data']
            response['subscription'] = {
                'seats_in_use': data.get('seats_in_use'),
                'seats_entitled': data.get('seats_entitled'),
                'plan_type': data.get('plan_type'),
                'active_until': data.get('active_until'),
            }
        elif sub_result.get('status') in [401, 403]:
            # 解析错误并映射
            error_type, error_msg = self._parse_openai_error(sub_result.get('error'))
            is_banned = error_type == 'banned'
            return {'success': False, 'banned': is_banned, 'error': error_msg, 'error_type': error_type}
        else:
            # 解析错误并映射
            error_type, error_msg = self._parse_openai_error(sub_result.get('error'))
            return {'success': False, 'error': error_msg, 'error_type': error_type}

        # 成员列表
        if mem_result.get('status') == 200:
            response['members'] = mem_result['data'].get('items', [])
        else:
            response['members'] = []
            response['members_error'] = mem_result.get('error')

        # 待处理邀请
        if inv_result.get('status') == 200:
            response['invites'] = inv_result['data'].get('items', [])
        else:
            response['invites'] = []
            response['invites_error'] = inv_result.get('error')

        return response
