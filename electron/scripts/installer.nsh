; 覆蓋預設安裝路徑為 %LOCALAPPDATA%\MediaTranX（移除多餘的 Programs 層）
!macro customInstallDir
  StrCpy $INSTDIR "$LOCALAPPDATA\MediaTranX"
!macroend

; 安裝前自動安裝 Visual C++ Redistributable 2015-2022 x64
; 靜默安裝，已安裝則跳過

!macro customInstall
  DetailPrint "正在確認 Visual C++ 執行套件..."

  ; 檢查是否已安裝（查機碼，Version >= 14.40 即為 2015-2022）
  ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Installed"
  ${If} $0 == 1
    DetailPrint "Visual C++ Redistributable 已安裝，略過。"
  ${Else}
    DetailPrint "正在下載並安裝 Visual C++ Redistributable..."
    nsExec::ExecToStack 'powershell.exe -NonInteractive -Command "Invoke-WebRequest -Uri ''https://aka.ms/vs/17/release/vc_redist.x64.exe'' -OutFile ''$TEMP\vc_redist.x64.exe'' -UseBasicParsing"'
    Pop $0
    Pop $1
    ${If} $0 == 0
      ExecWait '"$TEMP\vc_redist.x64.exe" /install /quiet /norestart' $1
      DetailPrint "VC++ Redistributable 安裝完成 (exit code: $1)"
      Delete "$TEMP\vc_redist.x64.exe"
    ${Else}
      MessageBox MB_OK|MB_ICONEXCLAMATION "無法自動安裝 Visual C++ Runtime（可能無網路連線）。$\n$\n請稍後手動下載安裝：$\nhttps://aka.ms/vs/17/release/vc_redist.x64.exe$\n$\n否則 MediaTranX 將無法啟動。"
    ${EndIf}
  ${EndIf}
!macroend
