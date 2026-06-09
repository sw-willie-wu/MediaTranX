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

; 解除安裝時清除使用者資料（%APPDATA%\MediaTranX：.venv、AI 模型、bin、DB、加密金鑰…常達數 GB）。
; electron-builder 預設只刪安裝目錄（%LOCALAPPDATA%），Roaming 資料會殘留。
; 互動式跳框詢問，預設按鈕為「是」（移除）。
!macro customUnInstall
  ; 靜默解除安裝（/S，例如 app 內建自動更新的 uninstall→reinstall）一律「保留」，
  ; 不可無聲清掉模型與 API key 加密金鑰——只有使用者在對話框按「是」才移除。
  IfSilent skip_user_data
  MessageBox MB_YESNO|MB_ICONQUESTION "是否一併移除已下載的 AI 模型、設定與資料？$\n$\n位置：%APPDATA%\MediaTranX（可能數 GB）$\n移除後重新安裝需重新下載；保留則可加速重裝。" IDNO skip_user_data
    DetailPrint "正在移除使用者資料 $APPDATA\MediaTranX ..."
    ; 先殺可能仍鎖住 .venv/模型檔的孤兒子行程（見 llama-server 孤兒洩漏歷史），
    ; 否則 RMDir /r 會跳過被鎖檔案、留下數 GB 殘骸。best-effort、忽略結果。
    nsExec::Exec 'taskkill /F /IM llama-server.exe'
    Pop $0
    nsExec::Exec 'taskkill /F /IM core.exe'
    Pop $0
    Sleep 500  ; 讓 OS 釋放被殺行程的檔案 handle，再刪才不留殘骸
    RMDir /r "$APPDATA\MediaTranX"
  skip_user_data:
!macroend
