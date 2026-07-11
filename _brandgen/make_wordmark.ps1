Add-Type -AssemblyName System.Drawing

$icon = [System.Drawing.Bitmap]::FromFile("D:\Work\scopic\token-guard\_brandgen\icon-512.png")

$iconSize = 200
$padding = 24
$textColor = [System.Drawing.ColorTranslator]::FromHtml("#2F8FD1")
$fontFamily = "Segoe UI"
$fontSize = [single]92.0
$font = New-Object System.Drawing.Font($fontFamily, $fontSize, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)

# measure text first on a throwaway bitmap
$measureBmp = New-Object System.Drawing.Bitmap(10,10)
$mg = [System.Drawing.Graphics]::FromImage($measureBmp)
$textSize = $mg.MeasureString("Token Guard", $font)
$mg.Dispose()
$measureBmp.Dispose()

$canvasHeight = 240
$canvasWidth = [int]($padding + $iconSize + $padding + $textSize.Width + $padding)

$canvas = New-Object System.Drawing.Bitmap($canvasWidth, $canvasHeight, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [System.Drawing.Graphics]::FromImage($canvas)
$g.Clear([System.Drawing.Color]::Transparent)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

$iconY = [int](($canvasHeight - $iconSize) / 2)
$g.DrawImage($icon, $padding, $iconY, $iconSize, $iconSize)

$textY = [int](($canvasHeight - $textSize.Height) / 2)
$brush = New-Object System.Drawing.SolidBrush($textColor)
$g.DrawString("Token Guard", $font, $brush, ($padding + $iconSize + $padding), $textY)

$g.Dispose()
$canvas.Save("D:\Work\scopic\token-guard\_brandgen\wordmark.png", [System.Drawing.Imaging.ImageFormat]::Png)
$canvas.Dispose()
$icon.Dispose()
Write-Output "done: $canvasWidth x $canvasHeight"
