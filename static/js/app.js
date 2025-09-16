// HOS 응급 의료 챗봇 - 메인 애플리케이션 JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('symptomForm');
    const loading = document.getElementById('loading');
    const result = document.getElementById('result');
    const error = document.getElementById('error');
    const submitBtn = document.getElementById('submitBtn');

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        // UI 상태 초기화
        hideAll();
        showLoading();
        
        try {
            const formData = new FormData();
            formData.append('symptom', document.getElementById('symptom').value);
            
            // 이미지 파일 추가
            const imageFile = document.getElementById('image').files[0];
            if (imageFile) {
                formData.append('image', imageFile);
            }
            
            // 위치 정보 추가
            const lat = document.getElementById('latitude').value;
            const lon = document.getElementById('longitude').value;
            if (lat && lon) {
                formData.append('location', JSON.stringify({
                    lat: parseFloat(lat),
                    lon: parseFloat(lon)
                }));
            }
            
            const response = await fetch('/api/advice', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            showResult(data);
            
        } catch (err) {
            showError(err.message);
        }
    });
    
    function hideAll() {
        loading.style.display = 'none';
        result.style.display = 'none';
        error.style.display = 'none';
    }
    
    function showLoading() {
        loading.style.display = 'block';
        submitBtn.disabled = true;
    }
    
    function showResult(data) {
        hideAll();
        result.style.display = 'block';
        submitBtn.disabled = false;
        
        // 조언 내용 표시
        document.getElementById('adviceContent').innerHTML = 
            `<div class="alert alert-info">${data.advice.replace(/\n/g, '<br>')}</div>`;
        
        // OTC 약품 표시
        const otcSection = document.getElementById('otcSection');
        const otcList = document.getElementById('otcList');
        if (data.otc && data.otc.length > 0) {
            otcList.innerHTML = data.otc.map(otc => `<li>${otc}</li>`).join('');
            otcSection.style.display = 'block';
        } else {
            otcSection.style.display = 'none';
        }
        
        // 통계 정보 표시
        document.getElementById('ragConfidence').textContent = 
            `${(data.rag_confidence * 100).toFixed(1)}%`;
        document.getElementById('processingTime').textContent = 
            data.processing_time.toFixed(2);
        
        // 크롤링 알림 표시
        const crawlingNotice = document.getElementById('crawlingNotice');
        if (data.needs_crawling) {
            crawlingNotice.style.display = 'block';
        } else {
            crawlingNotice.style.display = 'none';
        }
        
        // 신뢰도에 따른 색상 표시
        const confidenceElement = document.getElementById('ragConfidence');
        if (data.rag_confidence >= 0.7) {
            confidenceElement.className = 'text-success fw-bold';
        } else if (data.rag_confidence >= 0.4) {
            confidenceElement.className = 'text-warning fw-bold';
        } else {
            confidenceElement.className = 'text-danger fw-bold';
        }
    }
    
    function showError(message) {
        hideAll();
        error.style.display = 'block';
        submitBtn.disabled = false;
        document.getElementById('errorMessage').textContent = message;
    }
});

// 현재 위치 가져오기
function getCurrentLocation() {
    if (!navigator.geolocation) {
        alert('이 브라우저는 위치 서비스를 지원하지 않습니다.');
        return;
    }
    
    const latInput = document.getElementById('latitude');
    const lonInput = document.getElementById('longitude');
    
    latInput.value = '';
    lonInput.value = '';
    
    navigator.geolocation.getCurrentPosition(
        function(position) {
            latInput.value = position.coords.latitude.toFixed(6);
            lonInput.value = position.coords.longitude.toFixed(6);
        },
        function(error) {
            let message = '위치를 가져올 수 없습니다. ';
            switch(error.code) {
                case error.PERMISSION_DENIED:
                    message += '위치 접근이 거부되었습니다.';
                    break;
                case error.POSITION_UNAVAILABLE:
                    message += '위치 정보를 사용할 수 없습니다.';
                    break;
                case error.TIMEOUT:
                    message += '위치 요청이 시간 초과되었습니다.';
                    break;
                default:
                    message += '알 수 없는 오류가 발생했습니다.';
                    break;
            }
            alert(message);
        }
    );
}

// 랜덤 도쿄 위치 설정 (테스트 모드)
function setRandomTokyoLocation() {
    const latInput = document.getElementById('latitude');
    const lonInput = document.getElementById('longitude');
    
    // 도쿄 지역의 랜덤 좌표 생성
    // 도쿄 중심: 35.6762, 139.6503
    // ±0.1도 범위 내에서 랜덤 생성 (약 ±11km)
    const centerLat = 35.6762;
    const centerLon = 139.6503;
    const range = 0.1;
    
    const randomLat = centerLat + (Math.random() - 0.5) * range;
    const randomLon = centerLon + (Math.random() - 0.5) * range;
    
    latInput.value = randomLat.toFixed(6);
    lonInput.value = randomLon.toFixed(6);
    
    // 시각적 피드백
    latInput.style.backgroundColor = '#e3f2fd';
    lonInput.style.backgroundColor = '#e3f2fd';
    setTimeout(() => {
        latInput.style.backgroundColor = '';
        lonInput.style.backgroundColor = '';
    }, 1000);
}

// 고정 신주쿠 위치 설정 (테스트 모드)
function setFixedShinjukuLocation() {
    const latInput = document.getElementById('latitude');
    const lonInput = document.getElementById('longitude');
    
    // 신주쿠역 근처 고정 좌표
    latInput.value = '35.6909';
    lonInput.value = '139.7006';
    
    // 시각적 피드백
    latInput.style.backgroundColor = '#fff3e0';
    lonInput.style.backgroundColor = '#fff3e0';
    setTimeout(() => {
        latInput.style.backgroundColor = '';
        lonInput.style.backgroundColor = '';
    }, 1000);
}
