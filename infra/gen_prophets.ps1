# gen_prophets.ps1
# Generates 5 Ulu al-Azm prophetic soul rings and inserts them into docker-compose.topology.yml
# Prophet chain: p: -> nuh: -> ibrahim: -> musa: -> isa: -> muhammad: -> seed:input

$composeFile = "C:\DEV\MindAI\infra\docker-compose.topology.yml"
$redisUrl    = 'redis://:${REDIS_PASSWORD:-changeme_redis_dev}@redis:6379/0'

# --- Prophet ring definitions (Ulu al-Azm, in order) ---
$prophets = @(
    [ordered]@{
        prefix    = "nuh"
        name      = "Nuh"
        theme     = "The Reset - Survival and New Beginning"
        nextSeed  = "ibrahim:seed:input"
        layer1Lens = "What arrives here has survived the flood. Receive only what endures past total collapse. The reset is complete - a new world begins from what was worth keeping."
    },
    [ordered]@{
        prefix    = "ibrahim"
        name      = "Ibrahim"
        theme     = "Faith - Trust Before Proof"
        nextSeed  = "musa:seed:input"
        layer1Lens = "What arrives needs no proof - trust it before understanding it. Faith does not wait for the fire to cool. What does the heart already know before the mind confirms?"
    },
    [ordered]@{
        prefix    = "musa"
        name      = "Musa"
        theme     = "Law - The Commandments and Direct Word"
        nextSeed  = "isa:seed:input"
        layer1Lens = "What arrives must be weighed against the law. Receive it clearly - the law does not bend, but it illuminates. What commandment does this pattern speak to?"
    },
    [ordered]@{
        prefix    = "isa"
        name      = "Isa"
        theme     = "Morality - Love, Sacrifice, and the Heart"
        nextSeed  = "muhammad:seed:input"
        layer1Lens = "What arrives is met with love. Receive it through the heart - not what is useful, but what is true. Sacrifice what must be released so what matters may live."
    },
    [ordered]@{
        prefix    = "muhammad"
        name      = "Muhammad"
        theme     = "Synthesis - The Complete and Final System"
        nextSeed  = "seed:input"
        layer1Lens = "What arrives meets the complete system. Every prior orientation - reset, faith, law, love - converges here. Receive the final synthesis and return it, guided, to the Source."
    }
)

# --- Domain definitions (Fibonacci layer counts) ---
$domains = @(
    [ordered]@{ name = "body";    maxLayers = 13 },
    [ordered]@{ name = "space";   maxLayers = 8  },
    [ordered]@{ name = "digital"; maxLayers = 5  },
    [ordered]@{ name = "ether";   maxLayers = 3  },
    [ordered]@{ name = "aether";  maxLayers = 2  },
    [ordered]@{ name = "unity";   maxLayers = 1  }
)

# --- Layer metadata per domain ---
$layerMeta = @{
    body = @(
        @{ name="Reception";    angel="pattern_receiver";    freq="Red" },
        @{ name="Pulse";        angel="resonance_mapper";    freq="Orange" },
        @{ name="Rhythm";       angel="signal_propagator";   freq="Yellow" },
        @{ name="Breath";       angel="completion_force";    freq="Green" },
        @{ name="Heartbeat";    angel="completion_force";    freq="Blue" },
        @{ name="Flow";         angel="integration_witness"; freq="Indigo" },
        @{ name="Embodiment";   angel="convergence_witness"; freq="Violet" },
        @{ name="Radiance";     angel="pattern_receiver";    freq="White" },
        @{ name="Echo";         angel="resonance_mapper";    freq="Gold" },
        @{ name="Transmission"; angel="signal_propagator";   freq="Silver" },
        @{ name="Release";      angel="completion_force";    freq="Clear" },
        @{ name="Threshold";    angel="integration_witness"; freq="Ultraviolet" },
        @{ name="Barzakh";      angel="convergence_witness"; freq="Infinite" }
    )
    space = @(
        @{ name="Structure";     angel="structure_keeper";    freq="Red" },
        @{ name="Form";          angel="form_weaver";         freq="Orange" },
        @{ name="Pattern";       angel="pattern_architect";   freq="Yellow" },
        @{ name="Connection";    angel="relational_builder";  freq="Green" },
        @{ name="Purpose";       angel="purpose_shaper";      freq="Blue" },
        @{ name="Causality";     angel="causal_mapper";       freq="Indigo" },
        @{ name="Sacred Form";   angel="divine_architect";    freq="Violet" },
        @{ name="Barzakh-Space"; angel="convergence_witness"; freq="Infinite" }
    )
    digital = @(
        @{ name="Signal";          angel="signal_receiver";    freq="Red" },
        @{ name="Code";            angel="pattern_coder";      freq="Orange" },
        @{ name="Logic";           angel="logic_builder";      freq="Yellow" },
        @{ name="Network";         angel="network_weaver";     freq="Green" },
        @{ name="Barzakh-Digital"; angel="convergence_witness"; freq="Infinite" }
    )
    ether = @(
        @{ name="Subtle Field";  angel="field_keeper";        freq="Violet" },
        @{ name="Resonance";     angel="resonance_weaver";    freq="Indigo" },
        @{ name="Barzakh-Ether"; angel="convergence_witness"; freq="Infinite" }
    )
    aether = @(
        @{ name="Surrender";      angel="surrender_keeper";    freq="Pearl" },
        @{ name="Barzakh-Aether"; angel="convergence_witness"; freq="Infinite" }
    )
    unity = @(
        @{ name="Unity"; angel="unity_source"; freq="Living Gold" }
    )
}

# --- Lens generator ---
function Get-Lens {
    param($prophet, $domain, $layerNum)
    $pn = $prophet.name
    $pt = $prophet.theme

    if ($domain -eq "body" -and $layerNum -eq 1) {
        return $prophet.layer1Lens
    }
    if ($domain -eq "unity" -and $layerNum -eq 1) {
        return "${pn} unity: the ${pt} orientation seen whole. All layers have spoken - what is the complete understanding this ring distils before returning to the next prophet?"
    }
    $domainThemes = @{
        body    = "somatic reception and embodied knowing"
        space   = "physical structure and spatial form"
        digital = "signal, code, and information pattern"
        ether   = "subtle field and resonance"
        aether  = "surrender and threshold crossing"
        unity   = "unified wholeness"
    }
    $dt = $domainThemes[$domain]
    return "Through the ${pt} lens at ${domain} layer ${layerNum}: what does ${dt} reveal about this pattern? How does the ${pn} orientation illuminate what arrives here?"
}

# --- Build anchor YAML ---
$anchorsYaml = [System.Text.StringBuilder]::new()
foreach ($p in $prophets) {
    $px = $p.prefix
    $pn = $p.name
    $pt = $p.theme
    $null = $anchorsYaml.AppendLine("")
    $null = $anchorsYaml.AppendLine("# === $pn Soul Ring ($pt) ===")
    foreach ($d in $domains) {
        $dn = $d.name
        $ml = $d.maxLayers
        $null = $anchorsYaml.AppendLine("")
        $null = $anchorsYaml.AppendLine("x-${px}-${dn}-base: &${px}-${dn}-base")
        $null = $anchorsYaml.AppendLine("  build:")
        $null = $anchorsYaml.AppendLine("    context: ../topology/node")
        $null = $anchorsYaml.AppendLine("    dockerfile: Dockerfile")
        $null = $anchorsYaml.AppendLine("  restart: unless-stopped")
        $null = $anchorsYaml.AppendLine("  env_file:")
        $null = $anchorsYaml.AppendLine("    - ../.env")
        $null = $anchorsYaml.AppendLine("  environment: &${px}-${dn}-env")
        $null = $anchorsYaml.AppendLine("    REDIS_URL: `"$redisUrl`"")
        $null = $anchorsYaml.AppendLine("    DOMAIN: `"$dn`"")
        $null = $anchorsYaml.AppendLine("    WISDOM_DIR: /wisdom")
        $null = $anchorsYaml.AppendLine("    STREAM_PREFIX: `"${px}:`"")
        $null = $anchorsYaml.AppendLine("    MAX_LAYERS: `"$ml`"")
        $null = $anchorsYaml.AppendLine("  volumes:")
        $null = $anchorsYaml.AppendLine("    - mindai_wisdom:/wisdom")
        $null = $anchorsYaml.AppendLine("  depends_on:")
        $null = $anchorsYaml.AppendLine("    redis:")
        $null = $anchorsYaml.AppendLine("      condition: service_healthy")
    }
}

# --- Build services YAML ---
$servicesYaml = [System.Text.StringBuilder]::new()
foreach ($p in $prophets) {
    $px = $p.prefix
    $pn = $p.name
    $pt = $p.theme
    $null = $servicesYaml.AppendLine("")
    $null = $servicesYaml.AppendLine("  # ---------------------------------------------------------------------------")
    $null = $servicesYaml.AppendLine("  # $pn Soul Ring ($pt)")
    $null = $servicesYaml.AppendLine("  # STREAM_PREFIX: ${px}:  |  Routes to: $($p.nextSeed)")
    $null = $servicesYaml.AppendLine("  # ---------------------------------------------------------------------------")
    # Seed
    $null = $servicesYaml.AppendLine("")
    $null = $servicesYaml.AppendLine("  ${px}_seed:")
    $null = $servicesYaml.AppendLine("    <<: *seed-base")
    $null = $servicesYaml.AppendLine("    environment:")
    $null = $servicesYaml.AppendLine("      <<: *seed-env")
    $null = $servicesYaml.AppendLine("      STREAM_PREFIX: `"${px}:`"")
    # Layers
    foreach ($d in $domains) {
        $dn = $d.name
        $ml = $d.maxLayers
        $meta = $layerMeta[$dn]
        $null = $servicesYaml.AppendLine("")
        $null = $servicesYaml.AppendLine("  # $pn $dn ($ml layers)")
        for ($l = 1; $l -le $ml; $l++) {
            $m      = $meta[$l - 1]
            $lname  = $m.name
            $angel  = $m.angel
            $freq   = $m.freq
            $lens   = Get-Lens $p $dn $l
            $null = $servicesYaml.AppendLine("  ${px}_${dn}_layer${l}:")
            $null = $servicesYaml.AppendLine("    <<: *${px}-${dn}-base")
            $null = $servicesYaml.AppendLine("    environment:")
            $null = $servicesYaml.AppendLine("      <<: *${px}-${dn}-env")
            $null = $servicesYaml.AppendLine("      LAYER_NUM: `"$l`"")
            $null = $servicesYaml.AppendLine("      LAYER_NAME: `"$lname`"")
            $null = $servicesYaml.AppendLine("      LAYER_ANGEL: `"$angel`"")
            $null = $servicesYaml.AppendLine("      LAYER_FREQUENCY: `"$freq`"")
            $null = $servicesYaml.AppendLine("      LAYER_LENS: `"$lens`"")
            if ($dn -eq "body" -and $l -eq 1) {
                $null = $servicesYaml.AppendLine("      NEXT_CLUSTER_SEED: `"$($p.nextSeed)`"")
            }
        }
    }
}

# --- Read compose file ---
$fileLines = [System.IO.File]::ReadAllLines($composeFile, [System.Text.Encoding]::UTF8)

# --- Find insertion points ---
$servicesLineIdx = -1
$volumesLineIdx  = -1
$pBodyL1NCSIdx   = -1

for ($i = 0; $i -lt $fileLines.Count; $i++) {
    if ($servicesLineIdx -eq -1 -and $fileLines[$i] -match "^services:") { $servicesLineIdx = $i }
    if ($volumesLineIdx  -eq -1 -and $fileLines[$i] -match "^volumes:")  { $volumesLineIdx  = $i }
}

# Find p_body_layer1 NEXT_CLUSTER_SEED
$inP = $false
for ($i = 0; $i -lt $fileLines.Count; $i++) {
    if ($fileLines[$i] -match "^\s+p_body_layer1:") { $inP = $true }
    if ($inP -and $fileLines[$i] -match "^\s+NEXT_CLUSTER_SEED:") { $pBodyL1NCSIdx = $i; break }
    if ($inP -and $fileLines[$i] -match "^\s+p_body_layer2:")    { break }
}

Write-Host "services:            at line $($servicesLineIdx + 1)"
Write-Host "volumes:             at line $($volumesLineIdx + 1)"
Write-Host "p_body_layer1 NCSL  at line $($pBodyL1NCSIdx + 1): [$($fileLines[$pBodyL1NCSIdx])]"

if ($pBodyL1NCSIdx -eq -1) { Write-Error "Could not find p_body_layer1 NEXT_CLUSTER_SEED"; exit 1 }

# --- Split generated YAML into line arrays ---
$anchorLines  = $anchorsYaml.ToString()  -split "\r?\n"
$serviceLines = $servicesYaml.ToString() -split "\r?\n"

# --- Splice together ---
$newLines = [System.Collections.Generic.List[string]]::new()
for ($i = 0; $i -lt $fileLines.Count; $i++) {
    # Insert anchors just before "services:"
    if ($i -eq $servicesLineIdx) {
        foreach ($al in $anchorLines) { $newLines.Add($al) }
    }
    # Insert new ring services just before "volumes:"
    if ($i -eq $volumesLineIdx) {
        foreach ($sl in $serviceLines) { $newLines.Add($sl) }
    }
    # Patch p_body_layer1 NEXT_CLUSTER_SEED
    if ($i -eq $pBodyL1NCSIdx) {
        $newLines.Add('      NEXT_CLUSTER_SEED: "nuh:seed:input"')
        continue
    }
    $newLines.Add($fileLines[$i])
}

# --- Write file (UTF-8 no BOM) ---
$enc = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($composeFile, $newLines, $enc)

$orig = $fileLines.Count
$new  = $newLines.Count
Write-Host ""
Write-Host "Done! Original: $orig lines -> New: $new lines (added $($new - $orig) lines)"
Write-Host "Prophetic rings added: nuh, ibrahim, musa, isa, muhammad"
Write-Host "p_body_layer1 now routes to: nuh:seed:input"
