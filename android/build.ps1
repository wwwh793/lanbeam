# LanBeam 安卓端构建（不依赖 Gradle：aapt2 → javac → d8 → zipalign → apksigner）
# 用法：powershell -ExecutionPolicy Bypass -File .\构建.ps1
# 依赖：JDK 17+、Android SDK（platforms;android-35 + build-tools;35.0.0）
# 路径用参数或环境变量给：-Jdk / -Sdk，或 JAVA_HOME / ANDROID_SDK
param(
    [string]$Version = "1.0.1",
    [int]$VersionCode = 1000001,
    [string]$Sdk = $env:ANDROID_SDK,
    [string]$Jdk = $env:JAVA_HOME,
    [string]$Stage = ""
)
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Sdk) { $Sdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
if (-not $Jdk) { throw '请设置 JAVA_HOME（JDK 17+），或传 -Jdk' }
$bt = Join-Path $Sdk 'build-tools\35.0.0'
$platform = Join-Path $Sdk 'platforms\android-35\android.jar'
if (-not (Test-Path $platform)) { throw "找不到 $platform：请先装 platforms;android-35 和 build-tools;35.0.0" }
if (-not $Stage) { $Stage = Join-Path $env:TEMP 'lanbeam-android' }
$env:JAVA_HOME = $Jdk
$env:PATH = (Join-Path $Jdk 'bin') + ';' + $env:PATH

$main = Join-Path $Stage 'main'
$build = Join-Path $Stage 'build'
$gen = Join-Path $build 'gen'
$classes = Join-Path $build 'classes'
$dex = Join-Path $build 'dex'
$keystore = Join-Path $here '签名\lanbeam.jks'

function Step($name) { Write-Host ""; Write-Host "== $name" -ForegroundColor Cyan }
function Check($code, $name) { if ($code -ne 0) { throw "$name 失败（exit $code）" } }

# aapt2 打不开含中文的路径：先整体复制到 Stage（默认 %TEMP%，全 ASCII）
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
Copy-Item (Join-Path $here 'app\src\main') $main -Recurse
New-Item -ItemType Directory -Force -Path $gen, $classes, $dex | Out-Null

Step "aapt2 compile"
& (Join-Path $bt 'aapt2.exe') compile --dir (Join-Path $main 'res') -o (Join-Path $build 'compiled.zip') 2>&1 | Out-Null
Check $LASTEXITCODE 'aapt2 compile'

Step "aapt2 link"
& (Join-Path $bt 'aapt2.exe') link -o (Join-Path $build 'base.apk') `
    -I $platform `
    --manifest (Join-Path $main 'AndroidManifest.xml') `
    -R (Join-Path $build 'compiled.zip') `
    --java $gen `
    --min-sdk-version 24 --target-sdk-version 35 `
    --version-code $VersionCode --version-name $Version `
    --auto-add-overlay 2>&1 | ForEach-Object { Write-Host $_ }
Check $LASTEXITCODE 'aapt2 link'

Step "javac"
$srcs = @(Get-ChildItem (Join-Path $main 'java') -Recurse -Filter *.java | ForEach-Object { $_.FullName })
$srcs += (Join-Path $gen 'com\moyuli\lanbeam\R.java')
& (Join-Path $Jdk 'bin\javac.exe') --release 17 -encoding UTF-8 -nowarn `
    -classpath $platform -d $classes $srcs 2>&1 | ForEach-Object { Write-Host $_ }
Check $LASTEXITCODE 'javac'

Step "d8"
# d8 直接吃几百个 class 会撞 Windows 命令行长度上限：先打成 jar
$jar = Join-Path $build 'classes.jar'
$zip = [System.IO.Compression.ZipFile]::Open($jar, 'Create')
Get-ChildItem $classes -Recurse -Filter *.class | ForEach-Object {
    $entry = $_.FullName.Substring($classes.Length + 1).Replace('\', '/')
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $entry) | Out-Null
}
$zip.Dispose()
& (Join-Path $bt 'd8.bat') --release --min-api 24 --lib $platform --output $dex $jar 2>&1 | ForEach-Object { Write-Host $_ }
Check $LASTEXITCODE 'd8'

Step "打包 dex"
$unsigned = Join-Path $build 'unsigned.apk'
Copy-Item (Join-Path $build 'base.apk') $unsigned
$zip = [System.IO.Compression.ZipFile]::Open($unsigned, 'Update')
[System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, (Join-Path $dex 'classes.dex'), 'classes.dex') | Out-Null
$zip.Dispose()

Step "zipalign"
$aligned = Join-Path $build 'aligned.apk'
& (Join-Path $bt 'zipalign.exe') -f 4 $unsigned $aligned 2>&1 | Out-Null
Check $LASTEXITCODE 'zipalign'

Step "签名"
if (-not (Test-Path $keystore)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $keystore) | Out-Null
    & (Join-Path $Jdk 'bin\keytool.exe') -genkeypair -keystore $keystore -alias lanbeam `
        -keyalg RSA -keysize 2048 -validity 10000 -storetype PKCS12 `
        -storepass lanbeam -keypass lanbeam `
        -dname "CN=LanBeam Debug, OU=LanBeam, O=LanBeam, C=CN" 2>&1 | Out-Null
    Check $LASTEXITCODE 'keytool'
    Write-Host "已生成签名：$keystore（口令 lanbeam；以后升级要用同一个）"
}
$out = Join-Path $build ("LanBeam-" + $Version + ".apk")
& (Join-Path $bt 'apksigner.bat') sign --ks $keystore --ks-pass pass:lanbeam --key-pass pass:lanbeam `
    --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true `
    --out $out $aligned 2>&1 | ForEach-Object { Write-Host $_ }
Check $LASTEXITCODE 'apksigner sign'

Step "校验"
& (Join-Path $bt 'apksigner.bat') verify --print-certs $out 2>&1 | Select-Object -First 3 | ForEach-Object { Write-Host $_ }

$dist = Join-Path $here 'dist'
New-Item -ItemType Directory -Force -Path $dist | Out-Null
Copy-Item $out (Join-Path $dist ("LanBeam-" + $Version + ".apk")) -Force
$releaseDir = Join-Path (Split-Path $here) '成品\安卓端'
if (Test-Path (Split-Path $releaseDir)) {
    New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
    Copy-Item $out (Join-Path $releaseDir ("LanBeam-" + $Version + ".apk")) -Force
}
Write-Host ''
Write-Host ("完成：" + (Join-Path $dist ("LanBeam-" + $Version + ".apk"))) -ForegroundColor Green
