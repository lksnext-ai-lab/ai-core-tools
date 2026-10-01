<#
.SYNOPSIS
    Levanta y gestiona varios Mattin aislados en la misma maquina.

.DESCRIPTION
    Un entorno = un Compose project independiente. Compose prefija
    contenedores, redes y volumenes con el project name
    (https://docs.docker.com/compose/how-tos/project-name/), asi que cada
    entorno tiene su propio Postgres, su propio Qdrant y sus propios ficheros.

    Eso es lo que permite que un cliente con version pineada conviva con
    develop: el backend arranca con `alembic upgrade head`, y dos versiones
    sobre el mismo volumen de Postgres se migran la BD la una a la otra.

    La config de cada entorno vive en envs/<entorno>.env, que se carga encima
    de envs/base.env (el ultimo --env-file gana).

.EXAMPLE
    .\mattin.ps1 ls
    .\mattin.ps1 update demo
    .\mattin.ps1 rebuild dev
    .\mattin.ps1 new pr-231 -Type feature
    .\mattin.ps1 destroy pr-231
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Command,

    [Parameter(Position = 1)]
    [string]$Environment,

    [ValidateSet('feature', 'cliente')]
    [string]$Type = 'feature',

    [int]$Port = 0,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$EnvDir = Join-Path $Root 'envs'
$TemplateDir = Join-Path $EnvDir '_templates'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Get-Environments {
    Get-ChildItem -Path $EnvDir -Filter '*.env' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.BaseName -ne 'base' -and -not $_.BaseName.StartsWith('_') } |
        ForEach-Object { $_.BaseName } |
        Sort-Object
}

function Assert-EnvName {
    param([string]$Name)

    # Ademas de cerrar el path traversal (el nombre se concatena a una ruta),
    # esto garantiza un COMPOSE_PROJECT_NAME valido: Compose solo acepta
    # minusculas, digitos, guion y guion bajo.
    if ($Name -notmatch '^[a-z0-9][a-z0-9_-]*$') {
        throw "Nombre de entorno invalido: '$Name'. Solo minusculas, digitos, '-' y '_', empezando por letra o digito."
    }
}

function Resolve-EnvName {
    param([string]$Name)

    if (-not $Name) {
        throw "Falta el entorno. Disponibles: $((Get-Environments) -join ', ')"
    }
    Assert-EnvName $Name
    if (-not (Test-Path (Join-Path $EnvDir "$Name.env"))) {
        throw "No existe envs/$Name.env. Disponibles: $((Get-Environments) -join ', ')"
    }
    return $Name
}

function Get-ComposeArgs {
    param([string]$Name)

    $base = Join-Path $EnvDir 'base.env'
    if (-not (Test-Path $base)) {
        throw "No existe envs/base.env. Copia envs/base.env.example y rellenalo."
    }
    # El orden importa: el segundo --env-file sobreescribe al primero.
    return @('--env-file', $base, '--env-file', (Join-Path $EnvDir "$Name.env"))
}

function Invoke-Compose {
    param([string]$Name, [string[]]$Arguments)

    $composeArgs = Get-ComposeArgs -Name $Name
    Push-Location $Root
    # docker escribe el progreso por stderr. En PowerShell 5.1 cada linea de
    # stderr de un ejecutable nativo se envuelve en un ErrorRecord, que con
    # ErrorActionPreference='Stop' aborta el script en mitad de un `pull`
    # perfectamente correcto (y basta con que la salida se redirija o se
    # pipee para que ocurra). El exit code es la unica senal fiable.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & docker compose @composeArgs @Arguments
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        $ErrorActionPreference = $previous
        Pop-Location
    }
}

function Get-EnvValue {
    param([string]$Name, [string]$Key)

    foreach ($file in @((Join-Path $EnvDir "$Name.env"), (Join-Path $EnvDir 'base.env'))) {
        if (-not (Test-Path $file)) { continue }
        $match = Select-String -Path $file -Pattern "^\s*$Key\s*=\s*(.*)$" | Select-Object -First 1
        if ($match) { return $match.Matches[0].Groups[1].Value.Trim() }
    }
    return $null
}

function Get-RunningCount {
    param([string]$Project)

    if (-not $Project) { return 0 }
    $ids = & docker ps -q --filter "label=com.docker.compose.project=$Project"
    if (-not $ids) { return 0 }
    return @($ids).Count
}

function Test-PortListening {
    param([int]$PortNumber)
    return $null -ne (Get-NetTCPConnection -LocalPort $PortNumber -State Listen -ErrorAction SilentlyContinue)
}

function Assert-PortAvailable {
    param([string]$Name)

    $portValue = Get-EnvValue -Name $Name -Key 'HTTP_PORT'
    if (-not $portValue) { return }
    $portNumber = [int]$portValue
    if (-not (Test-PortListening $portNumber)) { return }

    # El puerto esta ocupado. Si lo ocupa este mismo entorno es un re-up
    # normal; si lo ocupa otro, abortar antes de que Compose falle a medias.
    $project = Get-EnvValue -Name $Name -Key 'COMPOSE_PROJECT_NAME'
    $own = & docker ps -q --filter "label=com.docker.compose.project=$project" --filter "publish=$portNumber"
    if ($own) { return }

    $culprit = 'otro proceso'
    foreach ($other in Get-Environments) {
        if ($other -eq $Name) { continue }
        if ((Get-EnvValue -Name $other -Key 'HTTP_PORT') -eq $portValue) {
            $culprit = "el entorno '$other'"
            break
        }
    }
    throw "El puerto $portNumber ya esta ocupado por $culprit. Para ese entorno o cambia HTTP_PORT en envs/$Name.env."
}

function Get-FreePort {
    param([int]$Start)

    $taken = @{}
    foreach ($name in Get-Environments) {
        $value = Get-EnvValue -Name $name -Key 'HTTP_PORT'
        if ($value) { $taken[[int]$value] = $name }
    }
    for ($candidate = $Start; $candidate -lt ($Start + 100); $candidate++) {
        if ($taken.ContainsKey($candidate)) { continue }
        if (Test-PortListening $candidate) { continue }
        return $candidate
    }
    throw "No se ha encontrado un puerto libre a partir de $Start."
}

function Get-FreeTestPort {
    $taken = @{}
    foreach ($name in Get-Environments) {
        $value = Get-EnvValue -Name $name -Key 'TEST_DB_PORT'
        if ($value) { $taken[[int]$value] = $name }
    }
    for ($candidate = 5440; $candidate -lt 5500; $candidate++) {
        if (-not $taken.ContainsKey($candidate)) { return $candidate }
    }
    throw "No se ha encontrado un TEST_DB_PORT libre."
}

function Show-Url {
    param([string]$Name)
    Write-Host ""
    Write-Host "  $Name -> $(Get-EnvValue -Name $Name -Key 'FRONTEND_URL')" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

switch ($Command.ToLower()) {

    'ls' {
        $rows = foreach ($name in Get-Environments) {
            $project = Get-EnvValue -Name $name -Key 'COMPOSE_PROJECT_NAME'
            $running = Get-RunningCount -Project $project
            $estado = 'parado'
            if ($running -gt 0) { $estado = "activo ($running)" }
            [pscustomobject]@{
                Entorno = $name
                Tag     = Get-EnvValue -Name $name -Key 'IMAGE_TAG'
                URL     = Get-EnvValue -Name $name -Key 'FRONTEND_URL'
                Estado  = $estado
                Project = $project
            }
        }
        $rows | Format-Table -AutoSize
    }

    'up' {
        $name = Resolve-EnvName $Environment
        Assert-PortAvailable $name
        Invoke-Compose $name (@('up', '-d', '--remove-orphans') + $Rest)
        Show-Url $name
    }

    'rebuild' {
        # Build desde el working tree actual. Para entornos dev/feature.
        $name = Resolve-EnvName $Environment
        $tag = Get-EnvValue -Name $name -Key 'IMAGE_TAG'
        if ($tag -eq 'develop' -or $tag -like 'sha-*' -or $tag -like 'v*') {
            throw "'$name' usa IMAGE_TAG=$tag, que es una imagen publicada; un --build la sobreescribiria en local. Usa 'update $name', o dale a este entorno un IMAGE_TAG propio."
        }
        Assert-PortAvailable $name
        Invoke-Compose $name (@('up', '-d', '--build', '--remove-orphans') + $Rest)
        Show-Url $name
    }

    'update' {
        # Trae la imagen publicada y recrea. Para demo y clientes.
        $name = Resolve-EnvName $Environment
        Assert-PortAvailable $name
        Invoke-Compose $name @('pull')
        Invoke-Compose $name (@('up', '-d', '--remove-orphans') + $Rest)
        Show-Url $name
    }

    'stop'    { Invoke-Compose (Resolve-EnvName $Environment) (@('stop') + $Rest) }
    'start'   { Invoke-Compose (Resolve-EnvName $Environment) (@('start') + $Rest) }
    'restart' { Invoke-Compose (Resolve-EnvName $Environment) (@('restart') + $Rest) }
    'down'    { Invoke-Compose (Resolve-EnvName $Environment) (@('down') + $Rest) }
    'pull'    { Invoke-Compose (Resolve-EnvName $Environment) (@('pull') + $Rest) }
    'ps'      { Invoke-Compose (Resolve-EnvName $Environment) (@('ps') + $Rest) }
    'logs'    { Invoke-Compose (Resolve-EnvName $Environment) (@('logs') + $Rest) }
    'exec'    { Invoke-Compose (Resolve-EnvName $Environment) (@('exec') + $Rest) }

    'open' {
        $name = Resolve-EnvName $Environment
        Start-Process (Get-EnvValue -Name $name -Key 'FRONTEND_URL')
    }

    'psql' {
        $name = Resolve-EnvName $Environment
        $user = Get-EnvValue -Name $name -Key 'DATABASE_USER'
        $db = Get-EnvValue -Name $name -Key 'DATABASE_NAME'
        if (-not $user) { $user = 'mattin' }
        if (-not $db) { $db = 'mattin_ai' }
        Invoke-Compose $name (@('exec', 'postgres', 'psql', '-U', $user, '-d', $db) + $Rest)
    }

    'invite' {
        # En AICT_LOGIN=LOCAL el backend provisiona los AICT_OMNIADMINS en el
        # primer arranque y publica el enlace de alta de password como WARNING
        # en el log (services/auth/omniadmin_bootstrap.py). Es de un solo uso.
        $name = Resolve-EnvName $Environment
        $composeArgs = Get-ComposeArgs -Name $name
        Push-Location $Root
        # Sin 2>&1: en PS 5.1 redirigir el stderr de un nativo convierte cada
        # linea en ErrorRecord. Los logs que buscamos van por stdout.
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $lines = & docker compose @composeArgs logs backend |
                Select-String -Pattern 'set-password' |
                Select-Object -Last 5
        }
        finally {
            $ErrorActionPreference = $previous
            Pop-Location
        }

        if (-not $lines) {
            Write-Host "No hay enlace de alta en el log de '$name'." -ForegroundColor Yellow
            Write-Host "Si la cuenta ya existe, define su password con:"
            Write-Host "  .\mattin.ps1 setpass $name <email> <password>"
            return
        }
        $lines | ForEach-Object { Write-Host $_.Line }
    }

    'setpass' {
        # Ruta de recuperacion soportada por el propio backend
        # (backend/utils/seed_dev_users.py). Funciona tambien sobre imagenes
        # descargadas del registry, no solo sobre builds locales.
        $name = Resolve-EnvName $Environment
        if ($Rest.Count -lt 2) {
            throw "Uso: .\mattin.ps1 setpass $name <email> <password>"
        }
        $seed = "$($Rest[0])::$($Rest[1])"
        Invoke-Compose $name @(
            'exec', '-e', "AICT_DEV_SEED_USERS=$seed",
            'backend', 'python', '-m', 'utils.seed_dev_users', '--yes'
        )
    }

    'new' {
        if (-not $Environment) { throw "Uso: .\mattin.ps1 new <nombre> [-Type feature|cliente] [-Port N]" }
        Assert-EnvName $Environment

        $target = Join-Path $EnvDir "$Environment.env"
        if (Test-Path $target) { throw "Ya existe envs/$Environment.env." }

        $template = Join-Path $TemplateDir "$Type.env.tmpl"
        if (-not (Test-Path $template)) { throw "No existe la plantilla $template." }

        if ($Port -gt 0) {
            $chosen = $Port
        }
        else {
            # Clientes en el rango 8090+, entornos de trabajo en 8083+, para
            # que 'ls' se lea de un vistazo.
            $start = 8083
            if ($Type -eq 'cliente') { $start = 8090 }
            $chosen = Get-FreePort -Start $start
        }

        $content = (Get-Content $template -Raw).
            Replace('__NAME__', $Environment).
            Replace('__PORT__', "$chosen").
            Replace('__TESTPORT__', "$(Get-FreeTestPort)")
        Set-Content -Path $target -Value $content -Encoding utf8 -NoNewline

        Write-Host "Creado envs/$Environment.env (puerto $chosen, tipo $Type)." -ForegroundColor Green
        if ($Type -eq 'cliente') {
            Write-Host "Pon en IMAGE_TAG el tag que corre en el cliente, y luego: .\mattin.ps1 up $Environment"
        }
        else {
            Write-Host "Cambia a la rama que quieras probar y: .\mattin.ps1 rebuild $Environment"
        }
    }

    'destroy' {
        $name = Resolve-EnvName $Environment
        $project = Get-EnvValue -Name $name -Key 'COMPOSE_PROJECT_NAME'
        Write-Host "Esto BORRA los volumenes de '$name' (project: $project):" -ForegroundColor Yellow
        Write-Host "  Postgres, Qdrant y los ficheros de repositorios. Irreversible." -ForegroundColor Yellow
        $answer = Read-Host "Escribe el nombre del entorno para confirmar"
        if ($answer -ne $name) {
            Write-Host 'Cancelado.'
            return
        }
        Invoke-Compose $name @('down', '-v', '--remove-orphans')
    }

    'rm' {
        # destroy + borrar la definicion del entorno.
        $name = Resolve-EnvName $Environment
        $project = Get-EnvValue -Name $name -Key 'COMPOSE_PROJECT_NAME'
        Write-Host "Esto borra los volumenes de '$name' (project: $project) Y su envs/$name.env." -ForegroundColor Yellow
        $answer = Read-Host "Escribe el nombre del entorno para confirmar"
        if ($answer -ne $name) {
            Write-Host 'Cancelado.'
            return
        }
        Invoke-Compose $name @('down', '-v', '--remove-orphans')
        Remove-Item (Join-Path $EnvDir "$name.env") -Force
        Write-Host "Entorno '$name' eliminado." -ForegroundColor Green
    }

    default {
        Write-Host "Comando desconocido: $Command"
        Write-Host ""
        Write-Host "Ciclo de vida:  up  rebuild  update  stop  start  restart  down  destroy"
        Write-Host "Entornos:       ls  new  rm"
        Write-Host "Operacion:      ps  logs  exec  psql  open  pull  invite  setpass"
        Write-Host ""
        Write-Host "Entornos actuales: $((Get-Environments) -join ', ')"
        exit 1
    }
}
