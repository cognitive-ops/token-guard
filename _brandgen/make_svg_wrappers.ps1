$iconBytes = [System.IO.File]::ReadAllBytes("D:\Work\scopic\token-guard\_brandgen\icon-512.png")
$iconB64 = [System.Convert]::ToBase64String($iconBytes)
$iconSvg = @"
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
<image href="data:image/png;base64,$iconB64" width="512" height="512"/>
</svg>
"@
[System.IO.File]::WriteAllText("D:\Work\scopic\token-guard\_brandgen\token_guard_icon.svg", $iconSvg)

$wmBytes = [System.IO.File]::ReadAllBytes("D:\Work\scopic\token-guard\_brandgen\wordmark.png")
$wmB64 = [System.Convert]::ToBase64String($wmBytes)
$wmSvg = @"
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 876 240" width="876" height="240">
<image href="data:image/png;base64,$wmB64" width="876" height="240"/>
</svg>
"@
[System.IO.File]::WriteAllText("D:\Work\scopic\token-guard\_brandgen\token_guard_text_logo.svg", $wmSvg)

Write-Output "done"
