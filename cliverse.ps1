param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)
$env:PYTHONPATH = "$PSScriptRoot\src;$PSScriptRoot"
& python -m cliverse.cli @CliArgs
