# Role settings only. Keys remain in the existing authorized dotenv/client path.
$movieLabPython = Join-Path $PSScriptRoot '..\venv\Scripts\python.exe'
$movieLabApp = Join-Path $PSScriptRoot '..\app.py'
$movieLabPreviousGeneration = $env:GMS_GENERATION_MODEL
$movieLabPreviousReview = $env:GMS_REVIEW_MODEL
try {
    $env:GMS_GENERATION_MODEL = 'gpt-4o-mini'
    $env:GMS_REVIEW_MODEL = 'gpt-5.4-mini'
    & $movieLabPython -m streamlit run $movieLabApp
    $movieLabExitCode = $LASTEXITCODE
} finally {
    $env:GMS_GENERATION_MODEL = $movieLabPreviousGeneration
    $env:GMS_REVIEW_MODEL = $movieLabPreviousReview
}
exit $movieLabExitCode
