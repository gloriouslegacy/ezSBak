# ezSBAK - Windows Backup Scheduler Documentation

## 개요 

**ezSBAK**은 Windows 환경에서 사용자 프로필 및 사용자 지정 파일/폴더를 자동으로 백업하는 GUI 기반 스케줄링 도구입니다. </br>Windows 작업 스케줄러와 통합되어 정기적인 백업을 자동화하고, 이메일 알림 기능을 제공합니다.

---

## 주요 기능

### 1. 백업 유형
- **사용자 프로필 백업**: Windows 사용자 폴더 전체를 백업
- **사용자 지정 백업**: 선택한 파일 및 폴더를 백업

### 2. 스케줄링 옵션
- **일일 백업**: 매일 지정된 시간에 실행
- **주간 백업**: 선택한 요일에 실행
- **월간 백업**: 매월 지정된 날짜에 실행

### 3. 고급 기능
- **숨김/시스템 파일 필터링**: 숨김 및 시스템 파일 포함/제외 옵션
- **백업 보존 정책**: 지정된 개수만큼 백업 유지 (자동 정리)
- **로그 보존 정책**: 지정된 기간만큼 로그 파일 유지
- **임시 볼륨 마운트**: 백업 전용 볼륨을 임시로 마운트하여 사용
- **이메일 알림**: 백업 성공/실패 시 이메일 통지
- **Windows 토스트 알림**: 백업 완료 시 시스템 알림 표시

### 4. 관리 기능
- **작업 실행 제어**: 즉시 실행, 중지, 활성화/비활성화
- **로그 관리**: 최근 로그 파일 빠른 열기
- **다중 작업 관리**: 여러 백업 작업 동시 선택 및 제어
- **실시간 상태 표시**: 다음 실행 시간, 마지막 실행 결과 표시

---

## 설치 및 실행

### 요구 사항
- **운영체제**: Windows 10/11
- **권한**: 관리자 권한 필요
- **Python 버전**: Python 3.7 이상 (소스 실행 시)

### 실행 방법

#### PyInstaller로 빌드된 실행 파일 사용
```bash
ezSBAK.exe
```

#### Python 스크립트 직접 실행
```bash
python ezSBAK.py
```

프로그램은 자동으로 관리자 권한 상승을 요청합니다.

---

## 사용 방법

### 1. 새 백업 스케줄 생성

#### 단계별 설정

1. **작업 이름**
   - 백업 작업을 식별할 고유한 이름 지정
   - 예: `ezBAK_Backup_John`, `ezBAK_Custom_Backup`

2. **백업 유형 선택**
   - **User Profile**: 특정 Windows 사용자 폴더 백업
   - **Custom Selection**: 사용자가 선택한 파일/폴더 백업

3. **백업 소스 지정**
   - **User Profile 모드**: 드롭다운에서 사용자 선택
   - **Custom Selection 모드**: "Select..." 버튼으로 파일/폴더 선택

4. **대상 폴더 설정**
   - 백업을 저장할 폴더 지정
   - 또는 "Use Temporary Mount" 옵션으로 볼륨 마운트

5. **스케줄 설정**
   - **Schedule**: Daily, Weekly, 또는 1-31 (월간)
   - **Time**: 실행 시간 (HH:MM 형식, 예: `02:00`)
   - **Days**: Weekly 선택 시 실행 요일 지정

6. **고급 옵션**
   - ☑ **Include Hidden**: 숨김 파일 포함
   - ☑ **Include System**: 시스템 파일 포함
   - **Backups to Keep**: 보관할 백업 개수 (0 = 무제한)
   - **Logs to Keep**: 로그 보관 기간 (일 단위, 0 = 무제한)

7. **이메일 알림 설정** (선택사항)
   - ☑ **Enable Email Notification**: 이메일 알림 활성화
   - ☑ **Notify on Success**: 성공 시 알림
   - ☑ **Notify on Failure**: 실패 시 알림 (기본값)
   - SMTP 서버 정보 입력:
     - SMTP Server: 예: `smtp.gmail.com`
     - Port: `587` (STARTTLS) 또는 `465` (SSL)
     - Sender/Recipient Email
     - Username/Password

8. **작업 생성**
   - "Create" 또는 "Save" 버튼 클릭

### 2. 작업 관리

#### 작업 목록 보기
메인 창에서 모든 등록된 백업 작업을 확인할 수 있습니다:
- **Task Name**: 작업 이름
- **Next Run Time**: 다음 실행 예정 시간
- **Status**: 현재 상태 (Ready, Running, Disabled)
- **Last Run Time**: 마지막 실행 시간
- **Last Run Result**: 마지막 실행 결과 (0 = 성공, 그 외 = 오류 코드)

#### 작업 제어 (우클릭 메뉴)
작업을 선택하고 우클릭하여:
- **지금 실행 (Run Now)**: 즉시 백업 실행
- **정지 (Stop)**: 실행 중인 백업 중지
- **사용 안 함 (Disable)**: 작업 비활성화
- **사용 (Enable)**: 작업 활성화
- **최근 로그 파일 열기 (Open Latest Log)**: 최신 로그 확인
- **삭제 (Delete)**: 작업 삭제

#### 작업 편집
작업을 더블클릭하여 설정을 수정할 수 있습니다.

#### 버튼 기능
- **New Schedule**: 새 백업 작업 생성
- **Delete Selected**: 선택한 작업 삭제
- **Refresh**: 작업 목록 새로고침
- **Open Log Folder**: 선택한 작업의 로그 폴더 열기
- **Task Scheduler**: Windows 작업 스케줄러 열기
- **Disk Management**: Windows 디스크 관리 열기

### 3. 임시 볼륨 마운트 사용

백업 전용 외장 드라이브를 사용할 때 유용합니다.

1. 스케줄 생성 시 "Use Temporary Mount" 체크
2. "Create" 버튼 클릭 시 볼륨 선택 대화상자 표시
3. 백업할 볼륨 선택:
   - 마운트되지 않은 볼륨: 임시 드라이브 문자 지정
4. 백업 실행 시:
   - 자동으로 볼륨 마운트
   - 백업 수행
   - 백업 완료 후 자동으로 볼륨 언마운트

---

## 백업 파일 구조

### 백업 폴더 명명 규칙
```
<BaseName>_backup_<YYYY-MM-DD_HHMMSS>
```

예시:
- User Profile: `Public_backup_2025-10-08_020000`
- Custom Backup: `Custom_backup_2025-10-08_020000`
- Named Task: `MyBackup_backup_2025-10-08_020000`

### 로그 파일 명명 규칙
```
<BaseName>_backup_<YYYY-MM-DD_HHMMSS>.log
```

### 디렉토리 구조 예시
```
D:\Backups\
├── Public_backup_2025-10-08_020000/
│   ├── Desktop/
│   ├── Documents/
│   └── Downloads/
├── Public_backup_2025-10-07_020000/
├── Public_backup_2025-10-08_020000.log
└── Public_backup_2025-10-07_020000.log
```

---

## 이메일 알림 설정 예시

### Gmail 사용
```
SMTP Server: smtp.gmail.com
Port: 587
Sender Email: your-email@gmail.com
Recipient Email: recipient@example.com
Username: your-email@gmail.com
Password: [앱 비밀번호]
```

**참고**: Gmail은 2단계 인증을 활성화하고 앱 비밀번호를 생성해야 합니다.

### Outlook/Office 365
```
SMTP Server: smtp.office365.com
Port: 587
Sender Email: your-email@outlook.com
Recipient Email: recipient@example.com
Username: your-email@outlook.com
Password: [계정 비밀번호]
```

---

## 헤드리스 모드 (자동 실행)

Windows 작업 스케줄러를 통해 자동으로 실행될 때는 GUI 없이 백업을 수행합니다.

### 명령줄 형식
```bash
sc_ezBAK.exe --auto-backup --task-name "TaskName"
```

### 동작 과정
1. 설정 파일 로드 (`%APPDATA%\ezbak_schedules\<TaskName>.json`)
2. 필요 시 볼륨 마운트
3. 백업 수행 (진행 상황 로그 파일에 기록)
4. 이전 백업 정리 (보존 정책에 따라)
5. 이전 로그 정리 (보존 정책에 따라)
6. 필요 시 볼륨 언마운트
7. Windows 토스트 알림 표시
8. 성공/실패 시 이메일 알림 (설정된 경우)

---

## 파일 필터링 규칙

### 자동 제외 항목
- **Reparse Points**: 심볼릭 링크 및 정션 포인트
- **특수 폴더** (Include Hidden & System 모두 체크되지 않은 경우):
  - `AppData`
  - `Application Data`
  - `Local Settings`

### 숨김/시스템 속성
- **Include Hidden 미체크**: `FILE_ATTRIBUTE_HIDDEN` 파일/폴더 제외
- **Include System 미체크**: `FILE_ATTRIBUTE_SYSTEM` 파일/폴더 제외

---

## 보존 정책

### 백업 보존
- 설정된 개수만큼 최신 백업 유지
- 오래된 백업은 자동 삭제
- `0` 설정 시 모든 백업 유지

### 로그 보존
- 설정된 기간(일) 동안 로그 파일 유지
- 파일명의 날짜 기준으로 판단
- `0` 설정 시 모든 로그 유지

---

## 문제 해결

### 백업이 실행되지 않음
1. Windows 작업 스케줄러에서 작업 상태 확인
2. 작업을 우클릭하여 "지금 실행" 테스트
3. 로그 파일 확인 (대상 폴더에 생성됨)
4. 대상 폴더의 디스크 공간 확인

### 권한 오류
- 프로그램을 관리자 권한으로 실행 중인지 확인
- 백업 대상 및 소스 폴더에 대한 접근 권한 확인

### 이메일 알림이 작동하지 않음
- SMTP 서버 정보가 정확한지 확인
- 방화벽에서 SMTP 포트(587/465) 허용 확인
- Gmail의 경우 앱 비밀번호 사용 확인
- 로그 파일에서 이메일 관련 오류 메시지 확인

### 볼륨 마운트 실패
- 선택한 드라이브 문자가 이미 사용 중인지 확인
- 볼륨이 물리적으로 연결되어 있는지 확인
- Disk Management에서 볼륨 상태 확인

---

## 설정 파일 위치

### Windows
```
%APPDATA%\ezbak_schedules\
```
실제 경로 예시:
```
C:\Users\YourName\AppData\Roaming\ezbak_schedules\
```

### 설정 파일 형식
각 작업은 JSON 형식으로 저장됩니다:
```json
{
    "task_name": "ezBAK_Backup_Public",
    "type": "user_profile",
    "user": "Public",
    "dest": "D:\\Backups",
    "schedule": "Daily",
    "time_str": "02:00",
    "include_hidden": false,
    "include_system": false,
    "retention_count": 2,
    "log_retention_days": 30,
    "email_notification": {
        "enabled": true,
        "notify_on_success": false,
        "notify_on_failure": true,
        "server": "smtp.gmail.com",
        "port": "587",
        "sender": "sender@example.com",
        "recipient": "recipient@example.com",
        "user": "sender@example.com",
        "password": "app-password"
    }
}
```

---

## 라이선스 및 크레딧

**개발자**: gloriouslegacy  
**GitHub**: https://github.com/gloriouslegacy

---

## 추가 정보

### 성능 최적화
- 대용량 파일 백업 시 64KB 버퍼 사용
- 증분 백업은 지원하지 않음 (전체 백업만 수행)
- 네트워크 드라이브로의 백업 시 속도 저하 가능

### 보안 고려사항
- 설정 파일 권한 관리
- 중요 데이터 백업 시 추가 암호화 고려

### 알려진 제한사항
- Windows 전용 (Linux/Mac 미지원)
- 파일 잠금 시 백업 실패 가능 (VSS 미사용)
- 2TB 이상 파일 시스템에서 일부 제한 가능

