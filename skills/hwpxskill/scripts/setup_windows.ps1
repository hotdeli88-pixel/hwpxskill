# hwpxskill Windows 설정 — 한글(2022 이상) 자동화로 PDF 렌더·HWP 변환을 쓰기 위한 준비.
#
#   powershell -ExecutionPolicy Bypass -File setup_windows.ps1
#   powershell -ExecutionPolicy Bypass -File setup_windows.ps1 -DllPath "C:\HwpAutomation\FilePathCheckerModuleExample.dll"
#
# 하는 일
#   1) pywin32 설치 (python -m pip install --user pywin32)
#   2) -DllPath 를 주면 한글 자동화 보안 모듈을 현재 사용자 레지스트리에 등록
#      HKCU\Software\HNC\HwpAutomation\Modules  (값 이름: FilePathCheckerModule)
#      → 파일을 열고 저장할 때마다 뜨는 "접근 허용" 창이 뜨지 않게 된다.
#      보안 모듈 DLL은 한컴 개발자 사이트(developer.hancom.com)의 '한글 자동화' 자료에서 받는다.
param(
    [string]$DllPath = "",
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"

Write-Host "[1/3] pywin32 설치"
& $Python -m pip install --user --upgrade pywin32
if ($LASTEXITCODE -ne 0) { throw "pywin32 설치 실패 — python 경로를 -Python 으로 지정해 보세요 (예: -Python py)" }

Write-Host "[2/3] 한글 자동화 보안 모듈"
if ($DllPath -ne "") {
    if (-not (Test-Path $DllPath)) { throw "DLL을 찾을 수 없습니다: $DllPath" }
    $full = (Resolve-Path $DllPath).Path
    $key = "HKCU:\Software\HNC\HwpAutomation\Modules"
    New-Item -Path $key -Force | Out-Null
    New-ItemProperty -Path $key -Name "FilePathCheckerModule" -Value $full -PropertyType String -Force | Out-Null
    Write-Host "  등록함: FilePathCheckerModule = $full"
} else {
    Write-Host "  건너뜀 (-DllPath 없음). 등록하지 않아도 동작하지만 파일마다 허용 창이 뜰 수 있습니다."
}

Write-Host "[3/3] 점검"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& $Python (Join-Path $here "hwpx.py") doctor
