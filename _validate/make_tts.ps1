Add-Type -AssemblyName System.Speech
$base = $PSScriptRoot
$txt = [System.IO.File]::ReadAllText((Join-Path $base 'tts_text.txt'), [System.Text.Encoding]::UTF8)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Huihui Desktop')
$s.Rate = 0
$out = Join-Path $base 'tts.wav'
$s.SetOutputToWaveFile($out)
$s.Speak($txt.Trim())
$s.Dispose()
Write-Output ("OK -> " + $out)
