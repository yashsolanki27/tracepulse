param()
$ErrorActionPreference = 'Stop'

$cfg = Get-Content "$env:USERPROFILE\.railway\config.json" | ConvertFrom-Json
$tok = $cfg.user.accessToken
$H = @{ Authorization = "Bearer $tok" }
$URI = 'https://backboard.railway.app/graphql/v2'

function GQL($query, $vars) {
    $body = @{ query = $query; variables = $vars } | ConvertTo-Json -Depth 8 -Compress
    $r = Invoke-RestMethod -Uri $URI -Method Post -ContentType 'application/json' -Headers $H -Body $body
    if ($r.errors) { $r.errors | ConvertTo-Json -Depth 5; throw 'GraphQL error' }
    return $r.data
}

# --- load env secrets from local .env ---
$envMap = @{}
Get-Content "$PSScriptRoot\..\.env" | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envMap[$Matches[1]] = $Matches[2].Trim() }
}

# 1. create project
$d = GQL 'mutation($n:String!){ projectCreate(input:{name:$n}){ id } }' @{ n = 'tracepulse' }
$proj = $d.projectCreate.id
Write-Host "project: $proj"

# 2. production environment id
$d = GQL "query(`$p:String!){ project(id:`$p){ environments{ edges{ node{ id name } } } } }" @{ p = $proj }
$envId = ($d.project.environments.edges | Where-Object { $_.node.name -eq 'production' })[0].node.id
Write-Host "env: $envId"

# 3. pgvector db service (same image as local compose)
$d = GQL 'mutation($p:String!,$n:String!){ serviceCreate(input:{ projectId:$p name:$n source:{ image:"pgvector/pgvector:pg16" } }){ id } }' @{ p = $proj; n = 'pgvector-db' }
$dbSvc = $d.serviceCreate.id
Write-Host "db service: $dbSvc"

$pw = [guid]::NewGuid().ToString('N')
foreach ($v in @(@('POSTGRES_USER','postgres'), @('POSTGRES_DB','tracepulse'), @('POSTGRES_PASSWORD',$pw))) {
    GQL 'mutation($e:String!,$s:String!,$k:String!,$v:String!){ variableUpsert(input:{ environmentId:$e serviceId:$s name:$k value:$v }){ id } }' @{ e = $envId; s = $dbSvc; k = $v[0]; v = $v[1] } | Out-Null
}
# persistent volume for db data
GQL 'mutation($p:String!,$s:String!){ volumeCreate(input:{ projectId:$p serviceId:$s mountPath:"/var/lib/postgresql/data" }){ id } }' @{ p = $proj; s = $dbSvc } | Out-Null
Write-Host 'db vars + volume set'

# 4. api service from repo, root dir app/
$d = GQL 'mutation($p:String!,$n:String!,$r:String!){ serviceCreate(input:{ projectId:$p name:$n source:{ repo:$r } }){ id } }' @{ p = $proj; n = 'tracepulse-api'; r = 'yashsolanki27/tracepulse' }
$apiSvc = $d.serviceCreate.id
Write-Host "api service: $apiSvc"
GQL 'mutation($e:String!,$s:String!,$rd:String){ serviceInstanceUpdate(environmentId:$e serviceId:$s rootDirectory:$rd){ id } }' @{ e = $envId; s = $apiSvc; rd = 'app' } | Out-Null

# 5. frontend service from repo, root dir frontend/
$d = GQL 'mutation($p:String!,$n:String!,$r:String!){ serviceCreate(input:{ projectId:$p name:$n source:{ repo:$r } }){ id } }' @{ p = $proj; n = 'tracepulse-frontend'; r = 'yashsolanki27/tracepulse' }
$feSvc = $d.serviceCreate.id
Write-Host "frontend service: $feSvc"
GQL 'mutation($e:String!,$s:String!,$rd:String){ serviceInstanceUpdate(environmentId:$e serviceId:$s rootDirectory:$rd){ id } }' @{ e = $envId; s = $feSvc; rd = 'frontend' } | Out-Null

# 6. api env vars (secrets read from local .env, none hardcoded)
$apiVars = @{
    DATABASE_URL         = "postgresql://postgres:`${{pgvector-db.POSTGRES_PASSWORD}}@pgvector-db.railway.internal:5432/tracepulse"
    GROQ_API_KEY         = $envMap['GROQ_API_KEY']
    TRACEPULSE_API_KEY   = $envMap['TRACEPULSE_API_KEY']
    EMBEDDING_MODEL      = $envMap['EMBEDDING_MODEL']
    SLACK_WEBHOOK_URL    = $envMap['SLACK_WEBHOOK_URL']
    EMAIL_IMAP_HOST      = $envMap['EMAIL_IMAP_HOST']
    EMAIL_IMAP_PORT      = $envMap['EMAIL_IMAP_PORT']
    EMAIL_USER           = $envMap['EMAIL_USER']
    EMAIL_PASSWORD       = $envMap['EMAIL_PASSWORD']
    EMAIL_FOLDER         = $envMap['EMAIL_FOLDER']
    EMAIL_POLL_SECONDS   = $envMap['EMAIL_POLL_SECONDS']
    CORS_ORIGINS         = 'http://localhost:5173'
}
foreach ($k in $apiVars.Keys) {
    GQL 'mutation($e:String!,$s:String!,$k:String!,$v:String!){ variableUpsert(input:{ environmentId:$e serviceId:$s name:$k value:$v }){ id } }' @{ e = $envId; s = $apiSvc; k = $k; v = $apiVars[$k] } | Out-Null
}
Write-Host 'api vars set'

# 7. public domains
$d = GQL 'mutation($e:String!,$s:String!){ domainCreate(input:{ environmentId:$e serviceId:$s }){ domain } }' @{ e = $envId; s = $apiSvc }
$apiDomain = $d.domainCreate.domain
$d = GQL 'mutation($e:String!,$s:String!){ domainCreate(input:{ environmentId:$e serviceId:$s }){ domain } }' @{ e = $envId; s = $feSvc }
$feDomain = $d.domainCreate.domain
Write-Host "api domain: https://$apiDomain"
Write-Host "frontend domain: https://$feDomain"

# 8. point CORS + frontend API URL at the real domains
GQL 'mutation($e:String!,$s:String!,$v:String!){ variableUpsert(input:{ environmentId:$e serviceId:$s name:"CORS_ORIGINS" value:$v }){ id } }' @{ e = $envId; s = $apiSvc; v = "https://$feDomain" } | Out-Null
foreach ($k in @(@('VITE_API_BASE_URL',"https://$apiDomain"), @('VITE_API_KEY',$envMap['TRACEPULSE_API_KEY']))) {
    GQL 'mutation($e:String!,$s:String!,$k:String!,$v:String!){ variableUpsert(input:{ environmentId:$e serviceId:$s name:$k value:$v }){ id } }' @{ e = $envId; s = $feSvc; k = $k[0]; v = $k[1] } | Out-Null
}
Write-Host 'DONE'
