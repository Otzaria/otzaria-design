param(
  [Parameter(Mandatory)] [string]$Out,
  [int]$QLevel = 10,      # QualityLevel 1..255 (codec options)
  [int]$Sub = 3,          # SubsamplingLevel 0..3 (3 = 4:4:4, 1 = 4:2:0)
  [int]$Overlap = 1,
  [int]$Planar = 0,       # 1 = planar alpha (separate quality via AlphaQ)
  [int]$AlphaQ = 1,       # AlphaQualityLevel (planar only)
  [int]$Premul = 0        # 1 = encode from Pbgra32 (premultiplied) instead of Bgra32
)
# Encodes the 24 book frames at 250% to JPEG XR through WIC (WPF wrapper) and decodes them back
# through WIC to raw 32bppPBGRA (.pbgra) and straight 32bppBGRA (.bgra) buffers.
Add-Type -AssemblyName PresentationCore, WindowsBase
$Src = Join-Path $PSScriptRoot 'native'
New-Item -ItemType Directory -Force $Out | Out-Null
$sizes = @{}
$fmt = if ($Premul) { [Windows.Media.PixelFormats]::Pbgra32 } else { [Windows.Media.PixelFormats]::Bgra32 }
foreach ($i in 0..23) {
  $stem = 'book_{0:D2}_250' -f $i
  $fs = [IO.File]::OpenRead((Join-Path $Src "$stem.png"))
  $dec = [Windows.Media.Imaging.BitmapDecoder]::Create($fs, 'PreservePixelFormat', 'OnLoad')
  $frame = $dec.Frames[0]; $fs.Close()
  $srcb = New-Object Windows.Media.Imaging.FormatConvertedBitmap($frame, $fmt, $null, 0)
  $enc = New-Object Windows.Media.Imaging.WmpBitmapEncoder
  $enc.UseCodecOptions = $true
  $enc.QualityLevel = $QLevel
  $enc.SubsamplingLevel = $Sub
  $enc.OverlapLevel = $Overlap
  $enc.InterleavedAlpha = ($Planar -eq 0)
  if ($Planar) { $enc.AlphaQualityLevel = $AlphaQ }
  $enc.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($srcb))
  $jxr = Join-Path $Out "$stem.jxr"
  $os = [IO.File]::Create($jxr); $enc.Save($os); $os.Close()
  $sizes[$stem] = (Get-Item $jxr).Length
  $fs = [IO.File]::OpenRead($jxr)
  $d2 = [Windows.Media.Imaging.BitmapDecoder]::Create($fs, 'PreservePixelFormat', 'OnLoad')
  $fr2 = $d2.Frames[0]; $fs.Close()
  if ($i -eq 0) { "stored format: $($fr2.Format)" }
  $b2 = New-Object Windows.Media.Imaging.FormatConvertedBitmap($fr2, [Windows.Media.PixelFormats]::Pbgra32, $null, 0)
  $w = $b2.PixelWidth; $h = $b2.PixelHeight
  $px = New-Object byte[] ($w * $h * 4)
  $b2.CopyPixels($px, $w * 4, 0)
  [IO.File]::WriteAllBytes((Join-Path $Out "$stem.pbgra"), $px)
  $b3 = New-Object Windows.Media.Imaging.FormatConvertedBitmap($fr2, [Windows.Media.PixelFormats]::Bgra32, $null, 0)
  $b3.CopyPixels($px, $w * 4, 0)
  [IO.File]::WriteAllBytes((Join-Path $Out "$stem.bgra"), $px)
}
$sizes | ConvertTo-Json | Set-Content -Encoding ascii (Join-Path $Out 'sizes.json')
$t = 0; $sizes.Values | ForEach-Object { $t += $_ }
"total=$t"
