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
        // 마크다운 렌더 (XSS 방지 위해 DOMPurify 사용)
        const md = typeof marked !== 'undefined' ? marked.parse(data.advice || '') : (data.advice || '').replace(/\n/g,'<br>');
        const safe = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(md) : md;
        document.getElementById('adviceContent').innerHTML = `<div class="alert alert-info">${safe}</div>`;
        
        // OTC 약품 표시
        const otcSection = document.getElementById('otcSection');
        const otcList = document.getElementById('otcList');
        if (data.otc && data.otc.length > 0) {
            otcList.innerHTML = data.otc.map(otc => `<li>${otc}</li>`).join('');
            otcSection.style.display = 'block';
        } else {
            otcSection.style.display = 'none';
        }
        
        // 참고 문헌 표시
        const refs = data.references || [];
        const refBox = document.getElementById('referencesBox');
        if (refBox) {
            if (refs.length) {
                refBox.style.display = 'block';
                document.getElementById('referencesList').innerHTML = refs.map(r => `<li>${r}</li>`).join('');
            } else {
                refBox.style.display = 'none';
            }
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

        // 주변 병원/약국 표시
        const hospBox = document.getElementById('nearbyHospitals');
        const pharmBox = document.getElementById('nearbyPharmacies');
        if (hospBox && pharmBox) {
            const hospitals = (data.nearby_hospitals || []).slice(0,5);
            const pharmacies = (data.nearby_pharmacies || []).slice(0,5);
            const toItem = (x) => {
                const hasCoord = x.lat != null && x.lon != null;
                const coord = hasCoord ? `${x.lat},${x.lon}` : '';
                // 좌표 기반 검색으로 전국 검색 확장 방지
                const mapUrl = hasCoord
                  ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(coord)}`
                  : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(x.name)}`;
                const dirUrl = hasCoord
                  ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(coord)}`
                  : null;
                return `<li class="mb-1 d-flex justify-content-between align-items-center">
                    <span>${x.name}${x.distance!=null?` <small class=\"text-muted\">(${x.distance.toFixed(1)}km)</small>`:''}</span>
                    <span class="btn-group">
                      <a class="btn btn-sm btn-outline-primary" href="${mapUrl}" target="_blank"><i class="fas fa-map"></i> 지도</a>
                      ${dirUrl ? `<a class=\"btn btn-sm btn-outline-secondary\" href=\"${dirUrl}\" target=\"_blank\"><i class=\"fas fa-route\"></i> 길찾기</a>` : ''}
                    </span>
                </li>`;
            };
            hospBox.innerHTML = hospitals.length ? hospitals.map(toItem).join('') : '<li>검색 결과 없음</li>';
            pharmBox.innerHTML = pharmacies.length ? pharmacies.map(toItem).join('') : '<li>검색 결과 없음</li>';
            document.getElementById('poiSection').style.display = (hospitals.length || pharmacies.length) ? 'block' : 'none';
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
        const help = document.getElementById('geoHelp');
        if (help) {
            help.style.display = 'block';
            help.innerHTML = '<strong>위치 서비스 미지원</strong><br>이 브라우저는 위치 서비스를 지원하지 않습니다. 랜덤 도쿄 또는 신주쿠 고정 위치 버튼을 사용해주세요.';
        }
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
                    message += '브라우저에서 위치 접근이 거부되었습니다. 주소창의 자물쇠 아이콘을 눌러 위치 권한을 "허용"으로 변경한 뒤 새로고침하세요.';
                    break;
                case error.POSITION_UNAVAILABLE:
                    message += '위치 정보를 사용할 수 없습니다. HTTPS에서 접속 중인지 확인해주세요.';
                    break;
                case error.TIMEOUT:
                    message += '위치 요청이 시간 초과되었습니다. 네트워크 상태를 확인하고 다시 시도하세요.';
                    break;
                default:
                    message += '알 수 없는 오류가 발생했습니다.';
                    break;
            }
            const help = document.getElementById('geoHelp');
            if (help) {
                help.style.display = 'block';
                help.innerHTML = `${message}<br><small>대안: 랜덤 도쿄 위치 또는 신주쿠 고정 위치 버튼을 사용해 주세요.</small>`;
            }
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
