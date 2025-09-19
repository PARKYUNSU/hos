import http from 'k6/http';
import { check, sleep } from 'k6';

// 환경변수
const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const ADMIN_USER = __ENV.ADMIN_USER || '';
const ADMIN_PASS = __ENV.ADMIN_PASS || '';

export const options = {
  stages: [
    { duration: '10s', target: 5 },
    { duration: '20s', target: 10 },
    { duration: '10s', target: 0 },
  ],
};

function authHeaders() {
  if (!ADMIN_USER || !ADMIN_PASS) return {};
  const token = `${ADMIN_USER}:${ADMIN_PASS}`;
  const b64 = typeof btoa !== 'undefined' ? btoa(token) : Buffer.from(token).toString('base64');
  return { Authorization: `Basic ${b64}` };
}

export default function () {
  // 1) 헬스 체크
  const res1 = http.get(`${BASE_URL}/api/health`);
  check(res1, {
    'health 200': (r) => r.status === 200,
  });

  // 2) 관리자 API(옵션)
  const headers = authHeaders();
  if (headers.Authorization) {
    const res2 = http.get(`${BASE_URL}/api/logs?limit=1`, { headers });
    check(res2, {
      'logs 200/204': (r) => r.status === 200 || r.status === 204,
    });
    const res3 = http.get(`${BASE_URL}/api/stats`, { headers });
    check(res3, {
      'stats 200': (r) => r.status === 200,
    });
  }

  sleep(1);
}


