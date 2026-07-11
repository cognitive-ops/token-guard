Add-Type -AssemblyName System.Drawing

$src = "D:\Work\scopic\token-guard\icon.jpg"
$bmp = [System.Drawing.Bitmap]::FromFile($src)

# source is 1024x559; center-crop a 559x559 square (excludes the stray sparkle near right edge)
$cropSize = 559
$cropX = [int](($bmp.Width - $cropSize) / 2)
$cropRect = New-Object System.Drawing.Rectangle($cropX, 0, $cropSize, $bmp.Height)

$cropped = New-Object System.Drawing.Bitmap($cropSize, $bmp.Height)
$g = [System.Drawing.Graphics]::FromImage($cropped)
$g.DrawImage($bmp, (New-Object System.Drawing.Rectangle(0,0,$cropSize,$bmp.Height)), $cropRect, [System.Drawing.GraphicsUnit]::Pixel)
$g.Dispose()
$bmp.Dispose()

function Resize-Square($image, $size, $outPath) {
    $out = New-Object System.Drawing.Bitmap($size, $size)
    $g = [System.Drawing.Graphics]::FromImage($out)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.DrawImage($image, 0, 0, $size, $size)
    $g.Dispose()
    $out.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $out.Dispose()
}

Resize-Square $cropped 256 "D:\Work\scopic\token-guard\_brandgen\icon-256.png"
Resize-Square $cropped 180 "D:\Work\scopic\token-guard\_brandgen\icon-180.png"
Resize-Square $cropped 32  "D:\Work\scopic\token-guard\_brandgen\icon-32.png"
Resize-Square $cropped 512 "D:\Work\scopic\token-guard\_brandgen\icon-512.png"

$cropped.Dispose()
Write-Output "done"
