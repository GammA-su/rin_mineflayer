param(
  [string]$BridgeUrl = $(if ($env:MINEFLAYER_BRIDGE_URL) { $env:MINEFLAYER_BRIDGE_URL } else { "http://localhost:3001" }),
  [int]$TimeoutSec = 20
)

$ErrorActionPreference = "Stop"

function Invoke-Action {
  param([string]$Action, [hashtable]$Args = @{})
  $body = @{ action = $Action; args = $Args } | ConvertTo-Json -Depth 20 -Compress
  try {
    $raw = Invoke-WebRequest -Uri "$BridgeUrl/action" -Method Post -ContentType "application/json" -Body $body -TimeoutSec $TimeoutSec
    return $raw.Content | ConvertFrom-Json
  } catch {
    if ($_.Exception.Response) {
      $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
      $content = $reader.ReadToEnd()
      if ($content) { return $content | ConvertFrom-Json }
    }
    throw
  }
}

function Assert-NoUnsupportedArgs {
  param([object]$Response, [string]$Case)
  if ($Response.error -and $Response.error -like "*unsupported args*") {
    throw "$Case failed with unsupported args: $($Response.error)"
  }
}

function Assert-Rejected {
  param([object]$Response, [string]$Expected, [string]$Case)
  $text = "$($Response.error) $($Response.result | ConvertTo-Json -Depth 6 -Compress)"
  if ($Response.ok -or $text -notlike "*$Expected*") {
    throw "$Case did not reject with '$Expected'. Response: $text"
  }
}

$cases = @(
  @{ name = "craft_furnace_empty"; action = "craft_furnace"; args = @{}; noUnsupported = $true },
  @{ name = "craft_furnace_count"; action = "craft_furnace"; args = @{ count = 1 }; noUnsupported = $true },
  @{ name = "craft_stone_pickaxe_count"; action = "craft_stone_pickaxe"; args = @{ count = 1 }; noUnsupported = $true },
  @{ name = "mine_stone_clamp"; action = "mine_stone"; args = @{ count = 999 }; noUnsupported = $true },
  @{ name = "collect_wood_junk"; action = "collect_wood"; args = @{ count = 4; junk = $true }; reject = "unsupported args" },
  @{ name = "say_slash"; action = "say"; args = @{ message = "/kill @e" }; reject = "cannot start with /" },
  @{ name = "acquire_invalid_target"; action = "acquire_blocks"; args = @{ targets = @("diamond_block") }; reject = "target is not allowed" },
  @{ name = "place_invalid_item"; action = "place_block"; args = @{ item = "diamond_block" }; reject = "not allowed" }
)

foreach ($case in $cases) {
  $response = Invoke-Action -Action $case.action -Args $case.args
  if ($case.noUnsupported) {
    Assert-NoUnsupportedArgs -Response $response -Case $case.name
  }
  if ($case.reject) {
    Assert-Rejected -Response $response -Expected $case.reject -Case $case.name
  }
  Write-Host ("{0}: ok={1} action={2} error={3}" -f $case.name, $response.ok, $response.action, $response.error)
}

Write-Host "manual_node_arg_normalizer_tests passed"
