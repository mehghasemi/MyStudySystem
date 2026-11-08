param([string]$Destination)
$ErrorActionPreference = 'Stop'
function Full([string]$path) { [IO.Path]::GetFullPath($path).TrimEnd('\') }
function Nested([string]$path,[string]$base) { $path -ieq $base -or $path.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase) }
function CheckLinks([string]$path) {
    while ($path) {
        if (Test-Path -LiteralPath $path) {
            if ((Get-Item -Force -LiteralPath $path).LinkType) {throw 'مسیر پیوندی قابل استفاده نیست.'}
        }
        $path = Split-Path -Parent $path
    }
}
try {
    $delivery = Full $PSScriptRoot
    $source = Join-Path $delivery 'app'
    $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $delivery 'BUILD_MANIFEST.json') | ConvertFrom-Json
    $prefs = Join-Path $env:LOCALAPPDATA 'MyStudySystem-Updater'
    $setting = Join-Path $prefs 'destination.txt'
    if (!$Destination -and (Test-Path -LiteralPath $setting)) { $Destination = [IO.File]::ReadAllText($setting) }
    if (!$Destination) { $Destination = Read-Host 'مسیر کامل پوشه عملیاتی را وارد کنید (پوشه مادر app و data)' }
    $Destination = $Destination.Trim().Trim('"')
    if ($Destination -notmatch '^[A-Za-z]:[\\/]') {throw 'مسیر کامل روی یک درایو را وارد کنید.'}
    $target = Full $Destination
    $app = Join-Path $target 'app'
    $project = Split-Path -Parent (Split-Path -Parent $delivery)
    if ($target.Length -le 3 -or (Nested $target $delivery) -or (Nested $delivery $target) -or
        ((Test-Path -LiteralPath (Join-Path $project 'AGENTS.md')) -and (Nested $target $project)) -or ((Split-Path -Leaf $target) -in @('app','data','runtime'))) {throw 'یک پوشه عملیاتی جدا از پروژه، app و data انتخاب کنید.'}
    CheckLinks $app
    $entries = @($manifest.files.PSObject.Properties | Where-Object Name -like 'app/*')
    if ('app/MyStudySystem.exe' -notin $entries.Name) {throw 'فهرست فایل‌های تحویل معتبر نیست.'}
    if (Test-Path -LiteralPath $app) {
        if (!(Test-Path -LiteralPath (Join-Path $app 'MyStudySystem.exe') -PathType Leaf)) {throw 'پوشه app مقصد متعلق به این برنامه نیست.'}
        # Do not remove unknown user files or follow junctions during cleanup.
        $queue = New-Object System.Collections.Queue
        $queue.Enqueue($app)
        while ($queue.Count) {
            foreach ($item in (Get-ChildItem -LiteralPath $queue.Dequeue() -Force)) {
                if ($item.LinkType) {throw 'در پوشه app مقصد یک پیوند وجود دارد.'}
                $rel = 'app/'+$item.FullName.Substring($app.Length+1).Replace('\','/')
                if ($item.PSIsContainer) {
                    if ($item.Name -ne '__pycache__' -and !($entries.Name -like ($rel+'/*'))) {throw "پوشه ناشناخته در app مقصد: $rel"}
                    $queue.Enqueue($item.FullName)
                } elseif ($rel -notin $entries.Name -and $rel -notlike '*/__pycache__/*.pyc') {throw "فایل ناشناخته در app مقصد: $rel"}
            }
        }
    } elseif ((Test-Path -LiteralPath $target) -and (Get-ChildItem -Force -LiteralPath $target | Where-Object Name -ne 'data')) {throw 'برای نصب اول یک پوشه خالی یا پوشه حاوی data انتخاب کنید.'}
    # A running backend holds the first byte of instance.lock on Windows.
    $lockFile = Join-Path $target 'data\instance.lock'
    $guard = $null
    if (Test-Path -LiteralPath $lockFile) {
        try { $guard = [IO.File]::Open($lockFile,'Open','Read','None') } catch {throw 'ابتدا در برنامه «خروج کامل» را بزنید و دوباره تلاش کنید.'}
    }
    $null = [IO.Directory]::CreateDirectory($target)
    $stage = Join-Path $target ('.study-stage-'+[guid]::NewGuid())
    $old = Join-Path $target ('.study-old-'+[guid]::NewGuid())
    try {
        foreach ($entry in $entries) {
            $relative = $entry.Name.Substring(4)
            $from = Full (Join-Path $source $relative)
            $to = Full (Join-Path $stage $relative)
            if (!(Nested $from $source) -or !(Nested $to $stage)) {throw 'مسیر فایل تحویل نامعتبر است.'}
            $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($to))
            [IO.File]::Copy($from,$to)
            if ((Get-FileHash -LiteralPath $to).Hash -ne $entry.Value) {throw "فایل تحویل ناقص است: $relative"}
        }
        if (Test-Path -LiteralPath $app) { [IO.Directory]::Move($app,$old) }
        try { [IO.Directory]::Move($stage,$app) }
        catch { if ((Test-Path -LiteralPath $old) -and !(Test-Path -LiteralPath $app)) {[IO.Directory]::Move($old,$app)}; throw }
        if ((Split-Path -Parent (Full $old)) -eq $target -and (Test-Path -LiteralPath $old)) {Remove-Item -LiteralPath $old -Recurse -Force}
    } finally {
        if ($guard) {$guard.Dispose()}
        if ((Split-Path -Parent (Full $stage)) -eq $target -and (Test-Path -LiteralPath $stage)) {Remove-Item -LiteralPath $stage -Recurse -Force}
    }
    $null=[IO.Directory]::CreateDirectory($prefs)
    [IO.File]::WriteAllText($setting,$target)
    Write-Host "نسخه $($manifest.version) آماده اجراست: $app\MyStudySystem.exe"
    exit 0
} catch {Write-Host $_.Exception.Message -ForegroundColor Red; exit 1}
