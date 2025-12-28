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
        """用 session-token 换取 accessToken"""
        if not session_token:
            return {'success': False, 'error': 'Missing session_token'}

        headers = {
            'Accept': '*/*',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Cookie': f'__Secure-next-auth.session-token={session_token}'
        }

        result = self._fetch('https://chatgpt.com/api/auth/session', headers)
        
        if result.get('status') == 200 and result.get('data', {}).get('accessToken'):
            return {'success': True, 'accessToken': result['data']['accessToken']}
        
        return {'success': False, 'error': result.get('error', 'Failed'), 'status': result.get('status')}

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
