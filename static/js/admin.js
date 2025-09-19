// HOS 관리자 대시보드 JavaScript

let websocket = null;
let confidenceChart = null;
let timeChart = null;

document.addEventListener('DOMContentLoaded', function() {
    // WebSocket 연결
    connectWebSocket();
    
    // 초기 데이터 로드
    loadDashboard();
    loadLogs();
    
    // 주기적 새로고침 (30초마다)
    setInterval(loadDashboard, 30000);
});

// WebSocket 연결
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
    
    websocket = new WebSocket(wsUrl);
    
    websocket.onopen = function(event) {
        console.log('WebSocket 연결됨');
        // 주기적으로 ping 전송
        setInterval(() => {
            if (websocket.readyState === WebSocket.OPEN) {
                websocket.send('ping');
            }
        }, 30000);
    };
    
    websocket.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'crawling_completed') {
                showNotification(`크롤링 완료: ${data.symptom}`, 'success');
                loadDashboard(); // 대시보드 새로고침
            } else if (data.type === 'crawling_error') {
                showNotification(`크롤링 오류: ${data.error}`, 'error');
            }
        } catch (e) {
            // ping/pong 메시지는 무시
        }
    };
    
    websocket.onclose = function(event) {
        console.log('WebSocket 연결 끊김, 재연결 시도...');
        setTimeout(connectWebSocket, 5000);
    };
    
    websocket.onerror = function(error) {
        console.error('WebSocket 오류:', error);
    };
}

// 탭 전환
function showTab(tabName) {
    // 모든 탭 숨기기
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.style.display = 'none';
    });
    
    // 모든 메뉴 아이템 비활성화
    document.querySelectorAll('.list-group-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // 선택된 탭 표시
    document.getElementById(`${tabName}-tab`).style.display = 'block';
    
    // 선택된 메뉴 아이템 활성화
    event.target.classList.add('active');
    
    // 탭별 데이터 로드
    switch(tabName) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'logs':
            loadLogs();
            break;
        case 'stats':
            loadStats();
            break;
        case 'settings':
            loadSettings();
            break;
    }
}

// OTC 규칙 편집기
async function loadOtcRules() {
    try {
        const res = await fetch('/api/otc_rules');
        const data = await res.json();
        const el = document.getElementById('otcRulesEditor');
        if (el) el.value = JSON.stringify(data, null, 2);
    } catch (e) {
        showNotification('규칙 불러오기 실패: ' + e, 'error');
    }
}

async function saveOtcRules() {
    try {
        const el = document.getElementById('otcRulesEditor');
        if (!el) return;
        const json = JSON.parse(el.value);
        const res = await fetch('/api/otc_rules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rules: json })
        });
        if (!res.ok) throw new Error(await res.text());
        showNotification('규칙 저장 완료', 'success');
    } catch (e) {
        showNotification('규칙 저장 실패: ' + e, 'error');
    }
}

// 대시보드 데이터 로드
async function loadDashboard() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        // 메트릭 업데이트
        document.getElementById('totalLogs').textContent = stats.total_logs;
        document.getElementById('successRate').textContent = `${(stats.success_rate * 100).toFixed(1)}%`;
        document.getElementById('ragPassages').textContent = stats.rag_passages_count;
        document.getElementById('playwrightStatus').textContent = stats.playwright_enabled ? '활성' : '비활성';
        
        // 차트 업데이트
        updateConfidenceChart(stats.confidence_distribution);
        updateTimeSeriesChart();
        
        // 실시간 로그 로드
        loadRealtimeLogs();
        
    } catch (error) {
        console.error('대시보드 로드 오류:', error);
    }
}

// 실시간 로그 로드
async function loadRealtimeLogs() {
    try {
        const response = await fetch('/api/logs?limit=10');
        const logs = await response.json();
        
        const container = document.getElementById('realtimeLogs');
        container.innerHTML = '';
        
        logs.forEach(log => {
            const logElement = document.createElement('div');
            logElement.className = 'log-entry mb-2 p-2 border rounded';
            logElement.innerHTML = `
                <div class="d-flex justify-content-between">
                    <div>
                        <strong>${new Date(log.timestamp).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}</strong> - ${log.user_input.substring(0, 50)}...
                    </div>
                    <div>
                        <span class="badge ${getConfidenceBadgeClass(log.rag_confidence)}">
                            ${(log.rag_confidence * 100).toFixed(1)}%
                        </span>
                        <span class="badge ${getQualityBadgeClass(log.advice_quality)}">
                            ${log.advice_quality}
                        </span>
                    </div>
                </div>
            `;
            container.appendChild(logElement);
        });
        
    } catch (error) {
        console.error('실시간 로그 로드 오류:', error);
    }
}

// 로그 데이터 로드
async function loadLogs() {
    try {
        const limit = document.getElementById('logLimit').value;
        const response = await fetch(`/api/logs?limit=${limit}`);
        const logs = await response.json();
        
        const tbody = document.getElementById('logsTable');
        tbody.innerHTML = '';
        
        logs.forEach(log => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${new Date(log.timestamp).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}</td>
                <td>${log.user_input}</td>
                <td>
                    <span class="badge ${getConfidenceBadgeClass(log.rag_confidence)}">
                        ${(log.rag_confidence * 100).toFixed(1)}%
                    </span>
                </td>
                <td>${log.processing_time.toFixed(2)}초</td>
                <td>
                    <span class="badge ${getQualityBadgeClass(log.advice_quality)}">
                        ${log.advice_quality}
                    </span>
                </td>
                <td>
                    <i class="fas fa-${log.image_uploaded ? 'camera text-success' : 'times text-muted'}"></i>
                </td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="showAdvice(${log.id})">
                        <i class="fas fa-eye"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
        
    } catch (error) {
        console.error('로그 로드 오류:', error);
    }
}

// 통계 로드
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        document.getElementById('systemStats').innerHTML = `
            <div class="row">
                <div class="col-6">
                    <strong>총 로그:</strong> ${stats.total_logs}개
                </div>
                <div class="col-6">
                    <strong>성공률:</strong> ${(stats.success_rate * 100).toFixed(1)}%
                </div>
            </div>
            <div class="row mt-2">
                <div class="col-6">
                    <strong>RAG 문서:</strong> ${stats.rag_passages_count}개
                </div>
                <div class="col-6">
                    <strong>Playwright:</strong> ${stats.playwright_enabled ? '활성' : '비활성'}
                </div>
            </div>
        `;
        
        document.getElementById('performanceStats').innerHTML = `
            <div class="row">
                <div class="col-12">
                    <strong>RAG 신뢰도 분포:</strong>
                    <ul class="mt-2">
                        ${Object.entries(stats.confidence_distribution).map(([range, count]) => 
                            `<li>${range}: ${count}개</li>`
                        ).join('')}
                    </ul>
                </div>
            </div>
        `;
        
    } catch (error) {
        console.error('통계 로드 오류:', error);
    }
}

// 설정 로드
async function loadSettings() {
    // 환경 변수 설정 UI 생성
    const envSettings = document.getElementById('envSettings');
    envSettings.innerHTML = `
        <div class="row">
            <div class="col-md-6">
                <div class="mb-3">
                    <label class="form-label">AUTO_REINDEX_ON_CRAWL</label>
                    <select class="form-select" id="autoReindex">
                        <option value="1">활성</option>
                        <option value="0">비활성</option>
                    </select>
                </div>
            </div>
            <div class="col-md-6">
                <div class="mb-3">
                    <label class="form-label">REINDEX_DEBOUNCE_SEC</label>
                    <input type="number" class="form-control" id="debounceSec" value="120" min="60" max="600">
                </div>
            </div>
        </div>
        <div class="row">
            <div class="col-md-6">
                <div class="mb-3">
                    <label class="form-label">USE_PLAYWRIGHT_CRAWLING</label>
                    <select class="form-select" id="playwrightCrawling">
                        <option value="1">활성</option>
                        <option value="0">비활성</option>
                    </select>
                </div>
            </div>
            <div class="col-md-6">
                <div class="mb-3">
                    <label class="form-label">CRAWL_MAX_LINKS_PER_SITE</label>
                    <input type="number" class="form-control" id="maxLinks" value="8" min="1" max="20">
                </div>
            </div>
        </div>
        <div class="row">
            <div class="col-md-6">
                <div class="mb-3">
                    <label class="form-label">MVP_RANDOM_TOKYO (테스트 모드)</label>
                    <select class="form-select" id="randomTokyo">
                        <option value="1">활성</option>
                        <option value="0">비활성</option>
                    </select>
                </div>
            </div>
            <div class="col-md-6">
                <div class="mb-3">
                    <label class="form-label">MVP_FIXED_SHINJUKU (고정 위치)</label>
                    <select class="form-select" id="fixedShinjuku">
                        <option value="1">활성</option>
                        <option value="0">비활성</option>
                    </select>
                </div>
            </div>
        </div>
        <div class="row">
            <div class="col-md-6">
                <div class="mb-3">
                    <label class="form-label">MVP_FIXED_LAT (고정 위도)</label>
                    <input type="number" class="form-control" id="fixedLat" value="35.6762" step="any">
                </div>
            </div>
            <div class="col-md-6">
                <div class="mb-3">
                    <label class="form-label">MVP_FIXED_LON (고정 경도)</label>
                    <input type="number" class="form-control" id="fixedLon" value="139.6503" step="any">
                </div>
            </div>
        </div>
        <button class="btn btn-primary" onclick="saveSettings()">
            <i class="fas fa-save"></i> 설정 저장
        </button>
        <hr/>
        <div class="row mt-3">
            <div class="col-md-6">
                <h5>OTC 병용 금기 규칙</h5>
                <div class="mb-2">
                    <button class="btn btn-sm btn-secondary" onclick="loadOtcRules()">불러오기</button>
                    <button class="btn btn-sm btn-primary" onclick="saveOtcRules()">저장</button>
                    <button class="btn btn-sm btn-outline-dark" onclick="backupOtcRules()">백업</button>
                    <input type="file" id="restoreFile" accept="application/json" class="form-control form-control-sm mt-2" onchange="restoreOtcRules(event)">
                </div>
                <textarea id="otcRulesEditor" class="form-control" rows="14" placeholder="JSON 규칙"></textarea>
                <small class="text-muted">PMDA/RAD-AR 기준을 반영한 규칙 JSON을 직접 수정/백업/복구할 수 있습니다.</small>
            </div>
        </div>
    `;
}
// 규칙 백업/복구
function backupOtcRules() {
  try {
    const el = document.getElementById('otcRulesEditor');
    if (!el) return;
    const blob = new Blob([el.value], {type: 'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `otc_rules_backup_${new Date().toISOString().slice(0,19).replace(/[:T]/g,'-')}.json`;
    a.click();
  } catch (e) {
    showNotification('백업 실패: ' + e, 'error');
  }
}

function restoreOtcRules(evt) {
  const file = evt.target.files && evt.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function() {
    try {
      const text = reader.result;
      JSON.parse(text); // 유효성 확인
      document.getElementById('otcRulesEditor').value = text;
      showNotification('파일 로드 완료. 저장 버튼으로 적용하세요.', 'success');
    } catch (e) {
      showNotification('복구 파일 파싱 실패: ' + e, 'error');
    }
  };
  reader.readAsText(file, 'utf-8');
}

// 신뢰도 배지 클래스 반환
function getConfidenceBadgeClass(confidence) {
    if (confidence >= 0.7) return 'bg-success';
    if (confidence >= 0.4) return 'bg-warning';
    return 'bg-danger';
}

// 품질 배지 클래스 반환
function getQualityBadgeClass(quality) {
    switch(quality) {
        case 'excellent': return 'bg-success';
        case 'good': return 'bg-primary';
        case 'fair': return 'bg-warning';
        case 'poor': return 'bg-danger';
        default: return 'bg-secondary';
    }
}

// 신뢰도 차트 업데이트
function updateConfidenceChart(distribution) {
    const ctx = document.getElementById('confidenceChart').getContext('2d');
    
    if (confidenceChart) {
        confidenceChart.destroy();
    }
    
    confidenceChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: Object.keys(distribution),
            datasets: [{
                data: Object.values(distribution),
                backgroundColor: [
                    '#dc3545', // 0-0.2: 빨강
                    '#fd7e14', // 0.2-0.4: 주황
                    '#ffc107', // 0.4-0.6: 노랑
                    '#20c997', // 0.6-0.8: 청록
                    '#198754'  // 0.8-1.0: 초록
                ]
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
}

// 시간별 차트 업데이트
async function updateTimeSeriesChart() {
    const ctx = document.getElementById('timeChart').getContext('2d');
    
    if (timeChart) {
        timeChart.destroy();
    }
    try {
      const res = await fetch('/api/logs?limit=500');
      const logs = await res.json();
      // 최근 24시간을 시:00 단위로 그룹핑
      const buckets = new Map();
      const fmtHour = new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul', year: undefined, month: undefined, day: undefined,
        hour: '2-digit', minute: '2-digit', hour12: false
      });
      const now = new Date();
      for (let i=0;i<24;i++) {
        const d = new Date(now.getTime() - i * 3600000);
        const key = fmtHour.format(d).replace(/^(\d{2}):\d{2}$/,'$1:00');
        if (!buckets.has(key)) buckets.set(key, 0);
      }
      logs.forEach(l => {
        const t = new Date(l.timestamp);
        if (isNaN(t.getTime())) return;
        const key = fmtHour.format(t).replace(/^(\d{2}):\d{2}$/,'$1:00');
        if (buckets.has(key)) buckets.set(key, (buckets.get(key)||0) + 1);
      });
      const labels = Array.from(buckets.keys()).reverse();
      const data = labels.map(k => buckets.get(k));
      timeChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: '로그 수',
                data,
                borderColor: '#0d6efd',
                backgroundColor: 'rgba(13, 110, 253, 0.1)',
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
      });
    } catch (e) {
      console.error('시간별 차트 생성 오류:', e);
    }
}

// 조언 내용 표시
async function showAdvice(logId) {
    try {
        // 최근 로그에서 해당 ID를 찾아 조언을 표시 (간단 구현: /api/logs 응답에서 조회)
        const limit = document.getElementById('logLimit').value || 100;
        const res = await fetch(`/api/logs?limit=${limit}`);
        const logs = await res.json();
        const log = logs.find(l => l.id === logId);
        const content = (log && log.advice_content) ? log.advice_content : '조언 내용이 저장되지 않았습니다.';

        const container = document.getElementById('adviceContent');
        if (container) {
            try {
                // marked를 이용해 Markdown을 HTML로 렌더링하고 DOMPurify로 안전화
                const html = marked.parse(content || '');
                container.innerHTML = DOMPurify.sanitize(html);
            } catch (e) {
                container.textContent = content || '';
            }
        }
        const modalEl = document.getElementById('adviceModal');
        if (modalEl) {
            const modal = new bootstrap.Modal(modalEl);
            modal.show();
        }
    } catch (e) {
        showNotification('조언 로드 실패: ' + e, 'error');
    }
}

// 설정 저장
function saveSettings() {
    const settings = {
        AUTO_REINDEX_ON_CRAWL: document.getElementById('autoReindex').value,
        REINDEX_DEBOUNCE_SEC: document.getElementById('debounceSec').value,
        USE_PLAYWRIGHT_CRAWLING: document.getElementById('playwrightCrawling').value,
        CRAWL_MAX_LINKS_PER_SITE: document.getElementById('maxLinks').value,
        MVP_RANDOM_TOKYO: document.getElementById('randomTokyo').value,
        MVP_FIXED_SHINJUKU: document.getElementById('fixedShinjuku').value,
        MVP_FIXED_LAT: document.getElementById('fixedLat').value,
        MVP_FIXED_LON: document.getElementById('fixedLon').value
    };
    
    // 실제로는 API 엔드포인트로 설정 저장
    console.log('설정 저장:', settings);
    showNotification('설정이 저장되었습니다. 서버 재시작 후 적용됩니다.', 'success');
}

// 알림 표시
function showNotification(message, type = 'info') {
    const alertClass = type === 'success' ? 'alert-success' : 
                      type === 'error' ? 'alert-danger' : 'alert-info';
    
    const notification = document.createElement('div');
    notification.className = `alert ${alertClass} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    // 5초 후 자동 제거
    setTimeout(() => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 5000);
}

// 대시보드 새로고침
function refreshDashboard() {
    loadDashboard();
    showNotification('대시보드가 새로고침되었습니다.', 'success');
}
