# start_totum_local.ps1
# Lance 3 fenêtres :
# 1) Webhook Flask (port 4242)
# 2) Stripe CLI listen -> forward vers /webhook
# 3) API auth_api (port 5001)

$projectRoot = "C:\Users\Alexa\TOTUM-auth.api"
$authApiDir  = Join-Path $projectRoot "auth_api"
$venvAct     = Join-Path $authApiDir ".venv\Scripts\Activate.ps1"

# Fenêtre 1 : webhook_server.py
Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "cd `"$authApiDir`"; Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; . `"$venvAct`"; python webhook_server.py"
) -WindowStyle Normal

Start-Sleep -Seconds 2

# Fenêtre 2 : Stripe listen (adapter le chemin si stripe.exe n'est pas dans le PATH)
# Si besoin, remplace 'stripe' par 'C:\stripe\stripe.exe'
Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "cd C:\Users\Alexa; stripe listen --forward-to localhost:4242/webhook"
) -WindowStyle Normal

Start-Sleep -Seconds 2

# Fenêtre 3 : API principale
Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "cd `"$authApiDir`"; Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; . `"$venvAct`"; python auth_api.py"
) -WindowStyle Normal

Write-Host "`n✅ Trois fenêtres lancées : Webhook (4242), Stripe listen, API (5001)." -ForegroundColor Green
Write-Host "Copiez/collez ensuite cette commande pour créer une session :" -ForegroundColor Yellow
$cmd = @'
Invoke-RestMethod -Uri "http://localhost:5001/create-checkout-session" -Method POST -Headers @{ "Content-Type"="application/json" } -Body '{"user_id":"d583cd6f-649f-41f3-8186-ba4073f2fb03"}' | Select-Object -ExpandProperty url
'@
Write-Host $cmd
